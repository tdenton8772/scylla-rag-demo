"""
Health Check Endpoint
"""

from fastapi import APIRouter
import logging

from ..models.schemas import HealthResponse
from ..core.scylla import get_scylla_client
from ..core.embeddings import get_embeddings_service
from ..core.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check health of all services
    """
    scylladb_healthy = False
    ollama_healthy = False
    
    # Check ScyllaDB
    try:
        client = get_scylla_client()
        # Try a simple query
        client.execute(f"SELECT * FROM {config.table_documents} LIMIT 1")
        scylladb_healthy = True
    except Exception as e:
        logger.error(f"ScyllaDB health check failed: {e}")
    
    # Check Ollama
    try:
        embeddings = get_embeddings_service()
        ollama_healthy = embeddings.health_check()
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
    
    status = "healthy" if (scylladb_healthy and ollama_healthy) else "degraded"
    
    return HealthResponse(
        status=status,
        scylladb=scylladb_healthy,
        ollama=ollama_healthy,
        embeddings_model=config.embeddings_model,
        llm_model=config.llm_model
    )
