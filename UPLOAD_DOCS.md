# Document Upload Guide

## Current Status

The **backend API is fully functional** and successfully:
- ✅ Extracts text from PDFs (using PyPDF2)
- ✅ Chunks documents using sentence-based strategy
- ✅ Generates embeddings (all-minilm:l6-v2)
- ✅ Stores in ScyllaDB vector store
- ✅ Makes documents available for retrieval

**Frontend UI upload**: Currently has an issue with the LiveView upload callback. Documents can be uploaded via API.

## Verified Working: API Upload

### Method 1: Using the Upload Script

```bash
./upload_document.sh ~/Downloads/your-document.pdf
```

### Method 2: Direct curl Command

```bash
curl -X POST "http://localhost:8000/ingest/upload" \
  -F "file=@/path/to/document.pdf"
```

### Example Output

```json
{
  "doc_id": "da4e6961-1893-4bfd-b59e-073b6547e48e",
  "filename": "Profile.pdf",
  "total_chunks": 55,
  "status": "completed",
  "message": "Successfully processed 55 chunks"
}
```

**Processing time**: ~1-2 seconds per chunk (6 seconds for 55 chunks)

## Supported File Types

- `.pdf` - PDF documents (text extraction via PyPDF2)
- `.md` - Markdown files
- `.txt` - Plain text files

**Size limit**: 10MB per file

## What Happens During Upload

1. **Upload** - File received by backend
2. **Extract** - Text extracted (PDF parsing for PDFs, UTF-8 decode for text)
3. **Chunk** - Document split into 512-char chunks with 50-char overlap
4. **Embed** - Each chunk gets a 384-dim vector embedding
5. **Store** - Chunks and embeddings saved to ScyllaDB

## Verifying Upload Success

Check backend logs:
```bash
tail -20 logs/fastapi.log
```

Look for:
```
✓ Document filename.pdf processed: X/X chunks stored
```

## Using Uploaded Documents

Once uploaded, documents are immediately available in chat conversations through vector similarity search. The system will automatically retrieve relevant chunks when you ask questions.

## Troubleshooting

**Backend not responding?**
```bash
curl http://localhost:8000/health
```

**PDF parsing errors?**
- Ensure PDF contains extractable text (not just images)
- Try: `pip install PyPDF2==3.0.1`

**Upload taking too long?**
- Check Ollama is running: `curl http://localhost:11434`
- Large documents take proportionally longer to embed
