"""
Chat WebSocket Endpoint
Real-time conversation with hybrid memory
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from typing import List
import logging
import json

from ..models.schemas import ChatRequest, ChatResponse, MemoryClearRequest
from ..services.memory import get_memory_service
from ..services.llm import get_llm_service
from ..core.scylla import get_scylla_client
from ..models.schemas import ConversationSessionSummary, ConversationMessagesResponse, ChatMessage
from ..core.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat
    
    Client sends: {"session_id": "...", "message": "..."}
    Server responds: {"message": "...", "context_type": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    memory_service = get_memory_service()
    llm_service = get_llm_service()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            request = json.loads(data)
            
            session_id = request.get('session_id')
            user_message = request.get('message')
            
            if not session_id or not user_message:
                await websocket.send_json({
                    "error": "Missing session_id or message"
                })
                continue
            
            logger.info(f"Received message: session={session_id}, message={user_message[:50]}...")
            
            try:
                # 1. Store user message
                memory_service.store_message(session_id, "user", user_message)
                
                # 2. Assemble hybrid context
                context, context_type = memory_service.assemble_hybrid_context(
                    user_message, session_id
                )
                
                # 3. Add current user message to context
                context.append({
                    "role": "user",
                    "content": user_message
                })
                
                # 4. Generate LLM response
                response_text = ""
                async for chunk in _async_stream_llm(llm_service, context):
                    response_text += chunk
                    # Stream chunks to client
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk
                    })
                
                # 5. Store assistant response
                memory_service.store_message(session_id, "assistant", response_text)
                
                # 6. Send completion signal
                await websocket.send_json({
                    "type": "complete",
                    "message": response_text,
                    "context_type": context_type,
                    "session_id": session_id
                })
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


async def _async_stream_llm(llm_service, messages):
    """Async wrapper for LLM streaming"""
    for chunk in llm_service.stream_response(messages):
        yield chunk


@router.get("/sessions", response_model=List[ConversationSessionSummary])
async def list_sessions(limit: int = Query(50, ge=1, le=500)):
    """List recent conversation sessions from Scylla (partition keys)."""
    client = get_scylla_client()
    summaries: List[ConversationSessionSummary] = []
    try:
        rows = client.execute(
            f"SELECT DISTINCT session_id FROM {config.table_sessions} LIMIT {limit}",
            profile="short",
        )
        for r in rows:
            sid_val = r.get("session_id") if isinstance(r, dict) else r.session_id
            sid = str(sid_val)
            last = None
            try:
                last_rows = client.execute(
                    f"SELECT message_timestamp FROM {config.table_sessions} WHERE session_id = %s",
                    (sid_val,),
                    profile="short"
                )
                first_row = list(last_rows)[:1]
                if first_row:
                    last = first_row[0].get("message_timestamp") if isinstance(first_row[0], dict) else first_row[0].message_timestamp
            except Exception:
                pass
            count = None
            try:
                cnt_rows = client.execute(
                    f"SELECT COUNT(*) as count FROM {config.table_sessions} WHERE session_id = %s",
                    (sid_val,),
                    profile="short"
                )
                cnt_row = list(cnt_rows)[0]
                if cnt_row:
                    count = cnt_row.get("count") if isinstance(cnt_row, dict) else cnt_row.count
            except Exception:
                pass
            
            # Get display name from metadata table
            display_name = None
            try:
                meta_rows = client.execute(
                    f"SELECT display_name FROM {config.table_metadata} WHERE doc_id = %s",
                    (sid_val,),
                    profile="short"
                )
                meta_row = list(meta_rows)[:1]
                if meta_row and meta_row[0].get("display_name"):
                    display_name = meta_row[0].get("display_name")
            except Exception:
                pass
            
            summaries.append(ConversationSessionSummary(
                session_id=sid, 
                last_message_at=last, 
                message_count=count,
                display_name=display_name
            ))
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
    return summaries


@router.get("/sessions/{session_id}/messages", response_model=ConversationMessagesResponse)
async def get_session_messages(session_id: str, limit: int = Query(50, ge=1, le=500)):
    """Return last N messages for a session (chronological)."""
    client = get_scylla_client()
    try:
        import uuid as _uuid
        query = f"SELECT role, content, message_timestamp FROM {config.table_sessions} WHERE session_id = %s"
        rows = client.execute(query, (_uuid.UUID(session_id),), profile="short")
        msgs = []
        count = 0
        for row in rows:
            if count >= limit:
                break
            role = row.get("role") if isinstance(row, dict) else row.role
            content = row.get("content") if isinstance(row, dict) else row.content
            ts = row.get("message_timestamp") if isinstance(row, dict) else row.message_timestamp
            msgs.append({"role": role, "content": content, "timestamp": ts})
            count += 1
        msgs.reverse()
        return ConversationMessagesResponse(session_id=session_id, messages=[ChatMessage(role=m["role"], content=m["content"]) for m in msgs])
    except Exception as e:
        logger.error(f"Failed to get session messages: {e}")
        return ConversationMessagesResponse(session_id=session_id, messages=[])


@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest, debug: bool = Query(False, description="Return context/prompt debug info")):
    """
    Non-streaming chat endpoint (alternative to WebSocket)
    """
    memory_service = get_memory_service()
    llm_service = get_llm_service()
    
    try:
        # Do NOT store the user message yet; avoid duplicating it in the prompt
        
        # Assemble hybrid context from prior messages only
        context, context_type = memory_service.assemble_hybrid_context(
            request.message, request.session_id
        )
        
        # Add current user message once (explicitly)
        final_messages = list(context) + [{"role": "user", "content": request.message}]
        
        # Generate response
        response_text = llm_service.generate_response(final_messages, stream=False)
        
        # Persist messages AFTER we have the response, in correct order
        memory_service.store_message(request.session_id, "user", request.message)
        memory_service.store_message(request.session_id, "assistant", response_text)
        
        debug_payload = None
        if debug:
            try:
                # Recompute short and long for visibility, and include final prompt
                short_dbg = memory_service.get_short_term_memory(request.session_id)
                # Get split long-term: documents and conversation memory separately
                query_embedding = memory_service.embeddings_service.generate_embedding(request.message)
                logger.info(f"[DEBUG] Calling _search_documents...")
                documents_dbg = memory_service._search_documents(query_embedding)
                logger.info(f"[DEBUG] Got {len(documents_dbg)} documents")
                logger.info(f"[DEBUG] Calling _search_long_term...")
                long_term_dbg = memory_service._search_long_term(query_embedding, request.session_id)
                logger.info(f"[DEBUG] Got {len(long_term_dbg)} long-term items")
            except Exception as e:
                logger.error(f"[DEBUG] Error getting split context: {e}")
                documents_dbg = []
                long_term_dbg = []
                short_dbg = []
            
            try:
                prompt_str = llm_service._messages_to_prompt(final_messages)
                logger.info(f"[DEBUG] Generated prompt length: {len(prompt_str)} chars")
                logger.info(f"[DEBUG] Prompt contains {prompt_str.count('[System Context]:') if prompt_str else 0} system context items")
            except Exception as e:
                logger.error(f"[DEBUG] Failed to generate prompt: {e}")
                prompt_str = "[unavailable]"
            debug_payload = {
                "short_term": short_dbg,
                "long_term": long_term_dbg,
                "documents": documents_dbg,
                "final_messages": final_messages,
                "prompt": prompt_str,
            }
            logger.info(f"[DEBUG] Debug payload: short_term={len(short_dbg)}, long_term={len(long_term_dbg)}, documents={len(documents_dbg)}, final_messages={len(final_messages)}")
        
        return ChatResponse(
            session_id=request.session_id,
            message=response_text,
            context_type=context_type,
            debug=debug_payload
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise


@router.post("/clear")
async def clear_memory(request: MemoryClearRequest):
    """
    Clear conversation history for a session
    """
    memory_service = get_memory_service()
    
    try:
        memory_service.clear_session(request.session_id)
        return {"status": "success", "message": f"Cleared session {request.session_id}"}
    except Exception as e:
        logger.error(f"Failed to clear session: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@router.post("/sessions/{session_id}/rename")
async def rename_session(session_id: str, display_name: str = Query(..., description="New display name")):
    """
    Rename a session by setting its display_name in metadata
    """
    client = get_scylla_client()
    
    try:
        import uuid as _uuid
        session_uuid = _uuid.UUID(session_id)
        
        # Upsert into metadata table
        query = f"""
        INSERT INTO {config.table_metadata} (doc_id, display_name)
        VALUES (%s, %s)
        """
        
        client.execute(query, (session_uuid, display_name))
        logger.info(f"Renamed session {session_id} to '{display_name}'")
        
        return {"status": "success", "session_id": session_id, "display_name": display_name}
    except Exception as e:
        logger.error(f"Failed to rename session: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
