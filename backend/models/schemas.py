"""
Pydantic Models for API
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID


# Document Ingestion
class DocumentUploadResponse(BaseModel):
    doc_id: str
    filename: str
    total_chunks: int
    status: str
    message: str


# Chat Models
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    message: str
    sources: Optional[List[Dict[str, Any]]] = None
    context_type: Optional[str] = None  # "short-term", "long-term", "hybrid"
    debug: Optional[Dict[str, Any]] = None


class ConversationSessionSummary(BaseModel):
    session_id: str
    last_message_at: Optional[datetime] = None
    message_count: Optional[int] = None
    display_name: Optional[str] = None


class ConversationMessagesResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]


# Memory Models
class MemoryClearRequest(BaseModel):
    session_id: str


class MemoryStats(BaseModel):
    session_id: str
    short_term_count: int
    long_term_count: int
    last_message_at: Optional[datetime] = None


# Health Check
class HealthResponse(BaseModel):
    status: str
    scylladb: bool
    ollama: bool
    embeddings_model: str
    llm_model: str
