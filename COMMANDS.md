# Quick Commands

## Start/Stop Services

```bash
# Start everything (Ollama + FastAPI backend)
./start.sh

# Stop everything
./stop.sh

# Check status
./status.sh

# View logs
./logs.sh
```

## Services

- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Ollama**: http://localhost:11434

## Logs

All logs are stored in `./logs/`:
- `fastapi.log` - Backend API logs
- `ollama.log` - Ollama service logs
- `schema-init.log` - Database initialization logs

```bash
# Tail all logs
tail -f logs/*.log

# Tail backend only
tail -f logs/fastapi.log
```

## Test Commands

### Health Check
```bash
curl http://localhost:8000/health
```

### Upload Document
```bash
echo "Test document content" > test.txt
curl -X POST http://localhost:8000/ingest/upload -F "file=@test.txt"
```

### Chat (Non-streaming)
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "message": "Hello! What is ScyllaDB?"
  }'
```

### Clear Session
```bash
curl -X POST http://localhost:8000/chat/clear \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123"}'
```

## Troubleshooting

### Services won't start
1. Check if ports are available: `lsof -i :8000 -i :11434`
2. View logs: `cat logs/fastapi.log`
3. Verify Ollama models: `ollama list`

### ScyllaDB connection issues
1. Check `.env` has correct credentials
2. Verify IP is whitelisted in ScyllaDB Cloud console
3. Test connection: `python scylladb_setup/create_schema.py`

### Ollama not working
1. Check if running: `pgrep ollama`
2. Start manually: `ollama serve`
3. Pull models: `ollama pull all-minilm:l6-v2 && ollama pull llama2`

## Development

### Restart just the backend
```bash
# Find and kill FastAPI process
pkill -f uvicorn

# Start backend
cd /Users/tdenton/Development/scylla-rag-demo
python3 -m uvicorn backend.api.main:app --reload --port 8000 > logs/fastapi.log 2>&1 &
```

### Update code and restart
```bash
./stop.sh
# Make your changes
./start.sh
```

## System Information

- **Project**: ScyllaDB RAG Demo with Hybrid Memory
- **Backend**: FastAPI + Python 3.12
- **Database**: ScyllaDB Cloud (3 tables: documents, conversation_sessions, document_metadata)
- **Embeddings**: Ollama all-minilm:l6-v2 (384 dimensions)
- **LLM**: Ollama llama2
- **Memory**: Hybrid (short-term: 5 messages, long-term: vector search top 4)
