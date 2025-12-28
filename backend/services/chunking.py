"""
Document Chunking Service
Implements sentence and phrase parsers with context linking per user rule
"""

import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import nltk

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

from ..core.config import config

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a document chunk"""
    content: str
    chunk_id: int
    metadata: Dict[str, Any]
    token_count: int


class ChunkingService:
    """
    Service for chunking documents
    Per user rule: Uses phrase/sentence parser with linking to following phrases for context
    """
    
    def __init__(self):
        self.strategy = config.chunk_strategy
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap
        
        logger.info(f"Chunking strategy: {self.strategy} (size: {self.chunk_size}, overlap: {self.chunk_overlap})")
    
    def chunk_document(self, text: str, doc_id: str, source_type: str = "document") -> List[Chunk]:
        """
        Chunk a document into smaller pieces
        
        Args:
            text: Document text to chunk
            doc_id: Document identifier
            source_type: Type of source (document, conversation, etc.)
            
        Returns:
            List of chunks with metadata
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for chunking (doc_id: {doc_id})")
            return []
        
        # Try semantic chunking first (best for resumes/profiles)
        if self._looks_like_resume(text):
            return self._chunk_semantic_sections(text, doc_id, source_type)
        
        if self.strategy == "sentence":
            return self._chunk_by_sentence(text, doc_id, source_type)
        elif self.strategy == "phrase":
            return self._chunk_by_phrase(text, doc_id, source_type)
        else:
            return self._chunk_fixed(text, doc_id, source_type)
    
    def _chunk_by_sentence(self, text: str, doc_id: str, source_type: str) -> List[Chunk]:
        """
        Chunk by sentences with linking to following sentences for context
        Per user rule: Link following phrases/sentences for context preservation
        """
        # Tokenize into sentences
        sentences = nltk.sent_tokenize(text)
        
        chunks = []
        chunk_id = 0
        
        # Number of sentences to link together (from config or default 2)
        link_count = config.get('chunking.sentence.link_sentences', 2)
        
        i = 0
        while i < len(sentences):
            # Get current sentence and link following sentences
            linked_sentences = sentences[i:i + link_count]
            chunk_text = " ".join(linked_sentences)  # Keep single space between sentences
            
            # Estimate token count (rough: ~1.3 words per token)
            token_count = int(len(chunk_text.split()) * 1.3)
            
            # If chunk is too large, split it
            if token_count > self.chunk_size:
                # Use single sentence
                chunk_text = sentences[i]
                token_count = int(len(chunk_text.split()) * 1.3)
            
            chunk = Chunk(
                content=chunk_text,
                chunk_id=chunk_id,
                metadata={
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "strategy": "sentence",
                    "linked_count": str(len(linked_sentences)),
                    "sentence_start": str(i),
                    "sentence_end": str(i + len(linked_sentences) - 1)
                },
                token_count=token_count
            )
            
            chunks.append(chunk)
            chunk_id += 1
            
            # Move forward with overlap
            # Overlap: reuse last sentence of current chunk in next chunk
            i += max(1, link_count - 1)
        
        logger.info(f"Chunked document {doc_id} into {len(chunks)} sentence-based chunks")
        return chunks
    
    def _chunk_by_phrase(self, text: str, doc_id: str, source_type: str) -> List[Chunk]:
        """
        Chunk by phrases with linking
        Per user rule: Link following phrases for context preservation
        """
        # Split by phrase delimiters (commas, semicolons, etc.)
        delimiter = config.get('chunking.phrase.delimiter', ',')
        phrases = [p.strip() for p in re.split(f'[{delimiter};]', text) if p.strip()]
        
        chunks = []
        chunk_id = 0
        
        # Number of phrases to link together
        link_count = config.get('chunking.phrase.link_phrases', 3)
        
        i = 0
        while i < len(phrases):
            # Link multiple phrases together
            linked_phrases = phrases[i:i + link_count]
            chunk_text = ". ".join(linked_phrases)
            
            token_count = int(len(chunk_text.split()) * 1.3)
            
            # If too large, reduce link count
            if token_count > self.chunk_size and len(linked_phrases) > 1:
                linked_phrases = phrases[i:i + 1]
                chunk_text = linked_phrases[0]
                token_count = int(len(chunk_text.split()) * 1.3)
            
            chunk = Chunk(
                content=chunk_text,
                chunk_id=chunk_id,
                metadata={
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "strategy": "phrase",
                    "linked_count": str(len(linked_phrases)),
                    "phrase_start": str(i),
                    "phrase_end": str(i + len(linked_phrases) - 1)
                },
                token_count=token_count
            )
            
            chunks.append(chunk)
            chunk_id += 1
            
            # Move forward with overlap
            i += max(1, link_count - 1)
        
        logger.info(f"Chunked document {doc_id} into {len(chunks)} phrase-based chunks")
        return chunks
    
    def _chunk_fixed(self, text: str, doc_id: str, source_type: str) -> List[Chunk]:
        """
        Chunk by fixed token size with overlap
        Fallback method if sentence/phrase parsing not preferred
        """
        words = text.split()
        chunks = []
        chunk_id = 0
        
        # Convert token size to approximate word count
        words_per_chunk = int(self.chunk_size / 1.3)
        overlap_words = int(self.chunk_overlap / 1.3)
        
        i = 0
        while i < len(words):
            chunk_words = words[i:i + words_per_chunk]
            chunk_text = " ".join(chunk_words)
            
            chunk = Chunk(
                content=chunk_text,
                chunk_id=chunk_id,
                metadata={
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "strategy": "fixed",
                    "word_start": str(i),
                    "word_end": str(i + len(chunk_words) - 1)
                },
                token_count=len(chunk_words)
            )
            
            chunks.append(chunk)
            chunk_id += 1
            
            # Move forward with overlap
            i += (words_per_chunk - overlap_words)
        
        logger.info(f"Chunked document {doc_id} into {len(chunks)} fixed-size chunks")
        return chunks
    
    def _looks_like_resume(self, text: str) -> bool:
        """Detect if text is a resume/profile based on common patterns"""
        resume_indicators = [
            'experience', 'education', 'skills', 'summary', 'contact',
            'linkedin', '@', 'university', 'college', 'degree',
            'solutions architect', 'engineer', 'developer', 'manager'
        ]
        text_lower = text.lower()
        matches = sum(1 for indicator in resume_indicators if indicator in text_lower)
        return matches >= 4  # If 4+ indicators, likely a resume
    
    def _chunk_semantic_sections(self, text: str, doc_id: str, source_type: str) -> List[Chunk]:
        """
        Chunk by semantic sections - keeps names with their descriptions.
        Perfect for resumes where name, title, and summary should stay together.
        Uses CHUNK_SIZE config as a guideline for target chunk size.
        """
        chunks = []
        chunk_id = 0
        
        # Use chunk_size as a strict character limit (with small buffer)
        max_chars = self.chunk_size
        
        # Split into paragraphs (double newline or single newline with significant spacing)
        paragraphs = re.split(r'\n\s*\n+', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        # Group paragraphs into semantic chunks, respecting character limit
        i = 0
        while i < len(paragraphs):
            # Start with current paragraph
            current_para = paragraphs[i]
            
            # If the first paragraph itself is too large, split it by sentences
            if len(current_para) > max_chars:
                # Split into sentences and chunk those
                import nltk
                sentences = nltk.sent_tokenize(current_para)
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 <= max_chars:
                        current_chunk += (" " if current_chunk else "") + sent
                    else:
                        # Save current chunk if it has content
                        if current_chunk:
                            chunks.append(Chunk(
                                content=current_chunk,
                                chunk_id=chunk_id,
                                metadata={
                                    "doc_id": doc_id,
                                    "source_type": source_type,
                                    "strategy": "semantic_section",
                                },
                                token_count=int(len(current_chunk.split()) * 1.3)
                            ))
                            chunk_id += 1
                        current_chunk = sent
                # Save final chunk from this paragraph
                if current_chunk:
                    chunks.append(Chunk(
                        content=current_chunk,
                        chunk_id=chunk_id,
                        metadata={
                            "doc_id": doc_id,
                            "source_type": source_type,
                            "strategy": "semantic_section",
                        },
                        token_count=int(len(current_chunk.split()) * 1.3)
                    ))
                    chunk_id += 1
                i += 1
                continue
            
            current_chunk = current_para
            
            # Add following paragraphs only if they fit within the limit
            j = i + 1
            while j < len(paragraphs):
                next_para = paragraphs[j]
                potential_chunk = current_chunk + "\n\n" + next_para
                
                # Check if adding this paragraph would exceed the limit
                if len(potential_chunk) > max_chars:
                    break  # Stop adding paragraphs
                
                # Add the paragraph
                current_chunk = potential_chunk
                j += 1
            
            # Create chunk
            token_count = int(len(current_chunk.split()) * 1.3)
            
            chunk = Chunk(
                content=current_chunk,
                chunk_id=chunk_id,
                metadata={
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "strategy": "semantic_section",
                    "paragraph_start": str(i),
                    "paragraph_end": str(j - 1)
                },
                token_count=token_count
            )
            
            chunks.append(chunk)
            chunk_id += 1
            i = j
        
        logger.info(f"Chunked document {doc_id} into {len(chunks)} semantic section chunks")
        return chunks


# Global chunking service
_chunking_service: ChunkingService = None


def get_chunking_service() -> ChunkingService:
    """Get or create the global chunking service"""
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    return _chunking_service
