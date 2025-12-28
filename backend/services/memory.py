"""
Hybrid Memory Service
Implements short-term (recent messages) and long-term (vector search) memory
"""

import logging
import re
import time
import numpy as np
from typing import List, Dict, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime

from ..core.scylla import get_scylla_client
from ..core.embeddings import get_embeddings_service
from ..core.config import config

logger = logging.getLogger(__name__)


class HybridMemoryService:
    """
    Hybrid memory implementation:
    - Short-term: Last N messages from conversation_sessions table
    - Long-term: Vector search on documents table
    """
    
    def __init__(self):
        self.scylla_client = get_scylla_client()
        self.embeddings_service = get_embeddings_service()
        
        self.short_term_limit = config.short_term_max_messages
        self.long_term_top_k = config.long_term_top_k
        self.long_term_similarity_threshold = config.long_term_similarity_threshold
        
        logger.info(f"Hybrid Memory: short-term={self.short_term_limit}, long-term top_k={self.long_term_top_k}")
    
    def store_message(self, session_id: str, role: str, content: str, context_docs: List[str] = None):
        """
        Store a message in short-term memory (conversation_sessions)
        Also store in long-term memory (documents) with embedding
        """
        # Store in short-term memory
        try:
            insert_query = f"INSERT INTO {config.table_sessions} (session_id, message_timestamp, role, content, context_docs) VALUES (%s, %s, %s, %s, %s)"
            self.scylla_client.execute(
                insert_query,
                (
                    UUID(session_id),
                    datetime.utcnow(),
                    role,
                    content,
                    context_docs or []
                ),
                profile="short"
            )
            logger.debug(f"Stored message in short-term memory: session={session_id}, role={role}")
        except Exception as e:
            logger.error(f"Failed to store in short-term memory: {e}")
            raise
        
        # Store in long-term conversation memory (separate table)
        try:
            embedding = self.embeddings_service.generate_embedding(content)
            insert_long_term = (
                f"INSERT INTO {config.table_long_term_memory} "
                f"(session_id, chunk_id, content, embedding, metadata, created_at) "
                f"VALUES (%s, %s, %s, %s, %s, %s)"
            )
            chunk_id = int(time.time() * 1000)  # millisecond ordering per session
            self.scylla_client.execute(
                insert_long_term,
                (
                    UUID(session_id),
                    chunk_id,
                    content,
                    embedding,
                    {"role": role},
                    datetime.utcnow()
                )
            )
            logger.debug(f"Stored message in long_term_memory: session={session_id}, chunk_id={chunk_id}")
        except Exception as e:
            logger.error(f"Failed to store in long_term_memory: {e}")
            # Non-fatal: short-term still stored
    
    def get_short_term_memory(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve recent messages from short-term memory
        Returns last N messages for immediate conversational context
        """
        try:
            select_query = f"SELECT role, content, message_timestamp FROM {config.table_sessions} WHERE session_id = %s"
            result = self.scylla_client.execute(select_query, (UUID(session_id),), profile="short")
            messages = []
            
            # Limit to most recent N messages (table is sorted DESC by timestamp)
            count = 0
            for row in result:
                if count >= self.short_term_limit:
                    break
                messages.append({
                    "role": row['role'],
                    "content": row['content'],
                    "timestamp": row['message_timestamp'],
                    "source": "short-term"
                })
                count += 1
            
            # Reverse to get chronological order
            messages.reverse()
            
            logger.debug(f"Retrieved {len(messages)} messages from short-term memory")
            return messages
            
        except Exception as e:
            logger.error(f"Failed to retrieve short-term memory: {e}")
            return []
    
    def _extract_persona(self, messages: List[Dict[str, Any]]) -> Dict[str, str]:
        """Heuristic extraction of short-term persona facts from recent messages."""
        persona = {"name": None, "study": None, "interests": []}
        name_patterns = [r"my name is\s+([A-Z][a-zA-Z]+)", r"i'm\s+([A-Z][a-zA-Z]+)"]
        study_patterns = [r"i am studying\s+([^\.\!\?]+)", r"i'm studying\s+([^\.\!\?]+)", r"thesis about\s+([^\.\!\?]+)"]
        interest_patterns = [r"interested in\s+([^\.\!\?]+)"]
        for m in messages:
            if m.get("role") != "user":
                continue
            text = m.get("content", "")
            low = text.lower()
            if not persona["name"]:
                for p in name_patterns:
                    mt = re.search(p, low)
                    if mt:
                        # Use original casing slice
                        span = mt.span(1)
                        persona["name"] = text[span[0]:span[1]].strip().strip('.')
                        break
            if not persona["study"]:
                for p in study_patterns:
                    mt = re.search(p, low)
                    if mt:
                        span = mt.span(1)
                        persona["study"] = text[span[0]:span[1]].strip().strip('.')
                        break
            for p in interest_patterns:
                for mt in re.finditer(p, low):
                    span = mt.span(1)
                    persona["interests"].append(text[span[0]:span[1]].strip().strip('.'))
        return persona

    def _fetch_surrounding_chunks(self, doc_id: UUID, center_chunk_id: int, window_size: int) -> List[Dict[str, Any]]:
        """Fetch surrounding chunks for a document to provide larger context."""
        if window_size == 0:
            return []
        
        try:
            # Calculate chunk range
            start_chunk = max(0, center_chunk_id - window_size)
            end_chunk = center_chunk_id + window_size
            
            # Fetch chunks in range
            query = (
                f"SELECT chunk_id, content FROM {config.table_documents} "
                "WHERE doc_id = %s AND chunk_id >= %s AND chunk_id <= %s"
            )
            result = self.scylla_client.execute(query, (doc_id, start_chunk, end_chunk))
            
            chunks = []
            for row in result:
                chunks.append({
                    "chunk_id": row.get('chunk_id') if isinstance(row, dict) else row.chunk_id,
                    "content": row.get('content') if isinstance(row, dict) else row.content
                })
            
            # Sort by chunk_id to maintain order
            chunks.sort(key=lambda x: x['chunk_id'])
            return chunks
        except Exception as e:
            logger.error(f"Failed to fetch surrounding chunks: {e}")
            return []
    
    def _search_documents(self, query_embedding) -> List[Dict[str, Any]]:
        """Search uploaded documents table with per-source threshold and top_k."""
        candidates = []
        try:
            # ANN candidate pool: configurable multiplier (default 1 = no expansion)
            search_limit = max(config.doc_top_k, config.doc_top_k * config.doc_ann_multiplier)
            query = (
                "SELECT doc_id, chunk_id, content, chunk_metadata, embedding "
                f"FROM {config.table_documents} "
                "ORDER BY embedding ANN OF %s "
                f"LIMIT {search_limit}"
            )
            result = self.scylla_client.execute(query, (query_embedding,))
            result_list = list(result)
            
            # Fallback: if ANN returns 0 results, do full table scan (for vector index issues)
            if len(result_list) == 0:
                logger.warning("ANN search returned 0 results, falling back to full table scan")
                query = f"SELECT doc_id, chunk_id, content, chunk_metadata, embedding FROM {config.table_documents}"
                result_list = list(self.scylla_client.execute(query))
            
            threshold = config.doc_similarity_threshold
            keep = []
            for row in result_list:
                emb = row.get('embedding')
                if not emb:
                    continue
                
                sim = float(np.dot(np.array(query_embedding), np.array(emb)) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb)))
                if sim >= threshold:
                    doc_id = row.get('doc_id') if isinstance(row, dict) else row.doc_id
                    chunk_id = row.get('chunk_id') if isinstance(row, dict) else row.chunk_id
                    center_content = row.get('content') if isinstance(row, dict) else row.content
                    
                    # Fetch surrounding chunks for context
                    window_size = config.doc_surrounding_chunks
                    if window_size > 0:
                        surrounding = self._fetch_surrounding_chunks(doc_id, chunk_id, window_size)
                        if surrounding:
                            # Concatenate all chunks in order with separators
                            expanded_content = "\n\n".join([c['content'] for c in surrounding])
                            logger.debug(f"Expanded chunk {chunk_id} with {len(surrounding)} surrounding chunks (window={window_size})")
                        else:
                            expanded_content = center_content
                    else:
                        expanded_content = center_content
                    
                    keep.append({
                        "content": expanded_content,
                        "source_type": 'uploaded_document',
                        "metadata": dict(row.get('chunk_metadata', {})) if row.get('chunk_metadata') else {},
                        "similarity": sim,
                    })
            keep.sort(key=lambda x: x['similarity'], reverse=True)
            return keep[:config.doc_top_k]
        except Exception as e:
            logger.error(f"Doc search failed: {e}")
            return []

    def _search_long_term(self, query_embedding, session_id: str) -> List[Dict[str, Any]]:
        """Search long_term_memory table restricted to session."""
        items = []
        try:
            # ANN candidate pool: configurable multiplier (default 1 = no expansion)
            search_limit = max(config.long_top_k, config.long_top_k * config.long_ann_multiplier)
            query = (
                f"SELECT session_id, chunk_id, content, embedding, metadata FROM {config.table_long_term_memory} "
                "ORDER BY embedding ANN OF %s "
                f"LIMIT {search_limit}"
            )
            result = self.scylla_client.execute(query, (query_embedding,))
            result_list = list(result)
            
            # Fallback: if ANN returns 0 results, do session-restricted scan
            if len(result_list) == 0:
                logger.warning("Long-term ANN search returned 0 results, falling back to session scan")
                query = f"SELECT session_id, chunk_id, content, embedding, metadata FROM {config.table_long_term_memory} WHERE session_id = %s"
                result_list = list(self.scylla_client.execute(query, (UUID(session_id),)))
            
            threshold = self.long_term_similarity_threshold
            for row in result_list:
                # Filter to current session only
                sid = str(row.get('session_id')) if isinstance(row, dict) else str(row.session_id)
                if sid != str(session_id):
                    continue
                emb = row.get('embedding') if isinstance(row, dict) else row.embedding
                if not emb:
                    continue
                sim = float(np.dot(np.array(query_embedding), np.array(emb)) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb)))
                if sim >= threshold:
                    md = row.get('metadata', {}) if isinstance(row, dict) else getattr(row, 'metadata', {})
                    items.append({
                        "content": row.get('content') if isinstance(row, dict) else row.content,
                        "source_type": 'conversation',
                        "metadata": dict(md) if md else {},
                        "similarity": sim,
                    })
            items.sort(key=lambda x: x['similarity'], reverse=True)
            return items[:config.long_top_k]
        except Exception as e:
            logger.error(f"Long-term search failed: {e}")
            return []

    def get_long_term_memory(self, query_text: str, session_id: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from long-term memory using vector search
        
        Includes:
        - ALL uploaded documents (source_type='document')
        - Conversations from CURRENT session only (prevents session bleed)
        
        Filters out conversations from other sessions to maintain session isolation.
        """
        try:
            t0 = time.time()
            # Generate embedding for query
            query_embedding = self.embeddings_service.generate_embedding(query_text)
            
            # Run split searches
            docs = self._search_documents(query_embedding)
            long_items = self._search_long_term(query_embedding, session_id) if session_id else []
            
            # Merge results (each already filtered and capped per-source)
            candidates = []
            candidates.extend(docs)
            candidates.extend(long_items)
            
            # Log what we retrieved
            logger.info(f"Split search: {len(docs)} documents, {len(long_items)} long-term items")
            
            # Count by source type for debugging
            source_type_counts = {}
            for c in candidates:
                st = c['source_type']
                source_type_counts[st] = source_type_counts.get(st, 0) + 1
            if source_type_counts:
                logger.debug(f"Candidates by type: {source_type_counts}")
            
            # Rerank by keyword overlap with STRONG boosting for exact matches
            question_terms = set([w.strip('.,!?').lower() for w in query_text.split() if len(w) > 2])
            query_low = query_text.lower()
            def score(c):
                text = c["content"]
                low = text.lower()
                
                # Start with semantic similarity as base
                base_score = c.get('similarity', 0) * 100  # Convert 0-1 to 0-100
                
                # Keyword matching boost
                keyword_boost = sum(10 for t in question_terms if t in low)  # +10 per keyword
                
                # STRONG boost if all query terms appear together (exact phrase match)
                if query_low in low:
                    keyword_boost += 100  # Exact match gets massive boost
                
                # Uploaded document type boost
                if c['source_type'] == 'uploaded_document':
                    keyword_boost += 20  # Prefer uploaded docs
                
                return base_score + keyword_boost
            
            # Log top scores before sorting
            if candidates:
                sample_scores = [(score(c), c['content'][:60]) for c in candidates[:10]]
                logger.info(f"Top 10 scores before sort: {[(s, txt) for s, txt in sample_scores[:5]]}")
            
            candidates.sort(key=score, reverse=True)
            
            # Log top after sorting
            if candidates:
                top_after = [(score(c), c['content'][:60]) for c in candidates[:3]]
                logger.info(f"Top 3 after sort: {top_after}")
            
            # Select independently per source (no overall cap)
            matches = []
            uploaded_doc_count = 0
            conversation_count = 0
            max_docs = config.doc_top_k
            max_long = config.long_top_k
            
            # Add docs up to doc_top_k, but re-check similarity threshold
            for c in candidates:
                if c['source_type'] == 'uploaded_document' and uploaded_doc_count < max_docs:
                    # Re-check similarity threshold after reranking
                    if c.get('similarity', 0) >= config.doc_similarity_threshold:
                        matches.append({
                            "content": c['content'],
                            "source_type": c['source_type'],
                            "metadata": dict(c.get('metadata', {})),
                            "source": "long-term",
                            "similarity": c.get('similarity', 0)  # Preserve for debugging
                        })
                        uploaded_doc_count += 1
            # Add long-term up to long_top_k, but re-check similarity threshold
            for c in candidates:
                if c['source_type'] == 'conversation' and conversation_count < max_long:
                    # Re-check similarity threshold after reranking
                    if c.get('similarity', 0) >= config.long_term_similarity_threshold:
                        matches.append({
                            "content": c['content'],
                            "source_type": c['source_type'],
                            "metadata": dict(c.get('metadata', {})),
                            "source": "long-term",
                            "similarity": c.get('similarity', 0)  # Preserve for debugging
                        })
                        conversation_count += 1
            
            # Log the mix for debugging
            logger.info(f"Reranked results: {uploaded_doc_count} uploaded_document, {conversation_count} conversation (per-source caps docs={max_docs}, long={max_long})")
            logger.debug(f"Long-term search: {len(candidates)} candidates, {len(matches)} selected in {(time.time()-t0)*1000:.1f}ms")
            return matches
            
        except Exception as e:
            logger.error(f"Failed to retrieve long-term memory: {e}")
            return []
    
    def assemble_hybrid_context(self, user_message: str, session_id: str) -> Tuple[List[Dict], str]:
        """
        Assemble hybrid context from short-term and long-term memory
        
        Returns:
            (context_messages, context_type)
        """
        context = []
        
        # 1. Get short-term memory (recent conversation)
        t_short = time.time()
        short_term = self.get_short_term_memory(session_id)
        # Do not inject persona/system summary; rely purely on vector search and short-term turns
        # Add last messages (chronological)
        context.extend(short_term)
        short_ms = (time.time()-t_short)*1000
        
        # 2. Get long-term memory (vector search with rerank)
        t_long = time.time()
        long_term = self.get_long_term_memory(user_message, session_id)
        long_ms = (time.time()-t_long)*1000
        
        # Add long-term context as system messages immediately before user turn
        for match in long_term:
            context.append({
                "role": "system",
                "content": f"[Context from {match['source_type']}]: {match['content']}",
                "source": "long-term"
            })
        
        # Add instructions that prevent hallucination
        if long_term:
            # We have long-term context - prioritize it
            context.append({
                "role": "system",
                "content": "Instructions: Answer using information from the conversation history and [Context] snippets above. If the context doesn't contain enough information to answer, say 'I don't have information about that.' Keep answers to 2-3 sentences."
            })
        else:
            # No long-term context, but short-term history is available
            context.append({
                "role": "system",
                "content": "Instructions: Answer using information from the conversation history above. If you cannot answer from the conversation, say 'I don't have information about that.' Keep answers to 2-3 sentences."
            })
        
        logger.debug(f"Context assembly: short={len(short_term)} ({short_ms:.1f}ms), long={len(long_term)} ({long_ms:.1f}ms)")
        
        # Determine context type
        if short_term and long_term:
            context_type = "hybrid"
        elif short_term:
            context_type = "short-term"
        elif long_term:
            context_type = "long-term"
        else:
            context_type = "none"
        
        logger.info(f"Assembled {context_type} context: {len(short_term)} short-term + {len(long_term)} long-term")
        
        return context, context_type
    
    def clear_session(self, session_id: str):
        """Clear short-term memory for a session"""
        delete_query = f"DELETE FROM {config.table_sessions} WHERE session_id = %s"
        
        try:
            self.scylla_client.execute(delete_query, (UUID(session_id),))
            logger.info(f"Cleared session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            raise


# Global memory service
_memory_service: HybridMemoryService = None


def get_memory_service() -> HybridMemoryService:
    """Get or create the global memory service"""
    global _memory_service
    if _memory_service is None:
        _memory_service = HybridMemoryService()
    return _memory_service
