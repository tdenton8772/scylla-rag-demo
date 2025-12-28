"""
Main FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from ..core.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ScyllaDB RAG Demo API",
    description="Hybrid memory RAG system with ScyllaDB",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting RAG API server...")
    
    # Import services (but don't force connection yet)
    from ..core.embeddings import get_embeddings_service
    
    try:
        # Test Ollama embeddings (local, should be fast)
        embeddings = get_embeddings_service()
        if embeddings.health_check():
            logger.info("✓ Ollama embeddings service available")
        else:
            logger.warning("⚠ Ollama embeddings service not available")
        
        logger.info("✓ API server started (ScyllaDB will connect on first request)")
            
    except Exception as e:
        logger.warning(f"Startup warning: {e}")
        # Don't raise - allow server to start


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down RAG API server...")
    
    from ..core.scylla import get_scylla_client
    
    try:
        client = get_scylla_client()
        client.close()
        logger.info("✓ ScyllaDB connection closed")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Import routers
from .health import router as health_router
from .ingest import router as ingest_router
from .chat import router as chat_router

# Include routers
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(ingest_router, prefix="/ingest", tags=["ingestion"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "ScyllaDB RAG Demo API",
        "version": "1.0.0",
        "docs": "/docs"
    }
