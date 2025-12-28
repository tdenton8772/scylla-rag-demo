"""
Document Ingestion Endpoint
Handles file upload, chunking, embedding, and storage
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from uuid import uuid4, UUID
from datetime import datetime
import logging
import io
import fitz  # pymupdf

from ..models.schemas import DocumentUploadResponse
from ..core.scylla import get_scylla_client
from ..core.embeddings import get_embeddings_service
from ..core.config import config
from ..services.chunking import get_chunking_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and process a document
    
    1. Read file content
    2. Chunk document using configured strategy
    3. Generate embeddings for each chunk
    4. Store chunks in ScyllaDB documents table
    5. Store metadata in document_metadata table
    """
    # Validate file type
    allowed_extensions = ['.txt', '.md', '.pdf']
    file_ext = '.' + file.filename.split('.')[-1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not supported. Allowed: {allowed_extensions}"
        )
    
    try:
        # Read file content
        content = await file.read()
        
        # Extract text based on file type
        if file_ext == '.pdf':
            try:
                # Use pymupdf (fitz) for better text extraction
                pdf_document = fitz.open(stream=content, filetype="pdf")
                text = ""
                page_count = len(pdf_document)
                for page_num in range(page_count):
                    page = pdf_document[page_num]
                    text += page.get_text() + "\n"
                pdf_document.close()
                logger.info(f"Extracted text from PDF: {len(text)} chars from {page_count} pages")
            except Exception as e:
                logger.error(f"Failed to parse PDF: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
        else:
            # Text files (md, txt)
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="File encoding not supported. Please use UTF-8.")
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="Empty file or no text extracted")
        
        # Generate document ID
        doc_id = str(uuid4())
        
        logger.info(f"Processing document: {file.filename} ({len(text)} chars)")
        
        # Get services
        chunking_service = get_chunking_service()
        embeddings_service = get_embeddings_service()
        scylla_client = get_scylla_client()
        
        # Chunk the document
        chunks = chunking_service.chunk_document(
            text=text,
            doc_id=doc_id,
            source_type="uploaded_document"
        )
        
        if not chunks:
            raise HTTPException(status_code=400, detail="Failed to chunk document")
        
        logger.info(f"Created {len(chunks)} chunks")
        
        # Generate embeddings and store chunks
        stored_count = 0
        for chunk in chunks:
            try:
                # Generate embedding
                embedding = embeddings_service.generate_embedding(chunk.content)
                
                # Store in documents table
                insert_query = (
                    "INSERT INTO " + config.table_documents + " "
                    "(doc_id, chunk_id, content, embedding, chunk_metadata, source_type, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                )
                
                params = (
                    UUID(doc_id),  # Convert doc_id string to UUID
                    chunk.chunk_id,
                    chunk.content,
                    embedding,
                    chunk.metadata,
                    "uploaded_document",
                    datetime.utcnow()
                )
                logger.debug(f"Params types: {[type(p).__name__ for p in params]}")
                logger.debug(f"Metadata type: {type(chunk.metadata)}, value: {chunk.metadata}")
                scylla_client.execute(insert_query, params)
                
                stored_count += 1
                
            except Exception as e:
                logger.error(f"Failed to store chunk {chunk.chunk_id}: {e}")
                # Continue processing other chunks
        
        # Store metadata
        metadata_query = (
            "INSERT INTO " + config.table_metadata + " "
            "(doc_id, filename, upload_timestamp, total_chunks, status, file_size, mime_type) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        
        scylla_client.execute(
            metadata_query,
            (
                UUID(doc_id),
                file.filename,
                datetime.utcnow(),
                len(chunks),
                "completed",
                len(content),
                file.content_type or "text/plain"
            )
        )
        
        logger.info(f"✓ Document {file.filename} processed: {stored_count}/{len(chunks)} chunks stored")
        
        return DocumentUploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            total_chunks=stored_count,
            status="completed",
            message=f"Successfully processed {stored_count} chunks"
        )
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding not supported. Please use UTF-8.")
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
