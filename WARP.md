# ScyllaDB RAG Demo - Warp Project Guide

A production-ready RAG (Retrieval Augmented Generation) system demonstrating **ScyllaDB as a unified data layer** that replaces both Redis (short-term memory) and traditional vector databases (long-term memory).

## Project Overview

This demo implements a hybrid memory architecture for intelligent chatbots:
- **Short-Term Memory**: Last 5 messages with 1-hour TTL (conversation_sessions table)
- **Long-Term Memory**: Vector embeddings with semantic search (documents table)
- **Unified Database**: Single ScyllaDB cluster handles both KV operations and vector search

## Architecture

### Tech Stack
- **Backend**: Python FastAPI + Cassandra Driver
- **Frontend**: Elixir Phoenix LiveView
- **Database**: ScyllaDB Cloud with vector search
- **Embeddings**: Ollama (all-minilm:l6-v2, 384 dimensions)
- **LLM**: Ollama (llama2) or OpenAI

### Data Flow
```
User Message → Store in conversation_sessions (short-term)
            ↓
         Embed → Store in documents (long-term)
            ↓
    Vector Search (top 4) + Recent Messages (last 5)
            ↓
         LLM → Response → Store again in both tables
```

## Quick Start

### Prerequisites
```bash
# Install dependencies
brew install ollama python@3.11 elixir

# Pull models
ollama pull all-minilm:l6-v2
ollama pull llama2
```

### Setup
```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with ScyllaDB Cloud credentials

# 2. Initialize database schema
python scylladb_setup/create_schema.py

# 3. Start all services
./start.sh

# Services will be available at:
# - Backend API: http://localhost:8000
# - Frontend UI: http://localhost:4000
```

### Stop Services
```bash
./stop.sh
```

## Project Structure

```
scylla-rag-demo/
├── backend/              # Python FastAPI backend
│   ├── api/             # API endpoints (main.py, chat.py, ingest.py, health.py)
│   ├── core/            # Core services (scylla.py, embeddings.py, config.py)
│   ├── services/        # Business logic (memory.py, chunking.py, llm.py)
│   ├── models/          # Data schemas (schemas.py)
│   └── tests/           # Test suite
├── frontend/            # Elixir Phoenix frontend
│   ├── lib/frontend_web/
│   │   └── live/chat_live.ex    # Main chat interface with LiveView
│   ├── assets/          # CSS/JS assets
│   └── config/          # Phoenix configuration
├── config/              # Application configuration
│   ├── config.yaml      # Main config (memory, chunking, LLM settings)
│   └── agent_rules.md   # Agent behavior rules
├── scylladb_setup/      # Database schema initialization
├── logs/                # Application logs
├── .pids/               # Process ID files
├── start.sh             # Startup script
├── stop.sh              # Shutdown script
├── test_system.sh       # End-to-end testing
└── .env                 # Environment variables (not in git)
```

## Key Components

### Backend API (`backend/api/`)

**main.py** - FastAPI application with CORS, startup/shutdown hooks
**chat.py** - Chat endpoints:
- `/chat/ws` - WebSocket for real-time streaming
- `/chat/message` - Non-streaming chat endpoint
- `/chat/sessions` - List conversation sessions
- `/chat/sessions/{id}/messages` - Get session history
- `/chat/clear` - Clear session memory

**ingest.py** - Document upload and processing
**health.py** - Health check endpoint

### Core Services (`backend/core/`)

**scylla.py** - ScyllaDB connection manager with:
- Singleton pattern for connection pooling
- Two execution profiles: "short" (LOCAL_ONE, 500ms) and default (LOCAL_QUORUM, 5s)
- Async query support

**embeddings.py** - Embedding generation service using Ollama

**config.py** - Configuration management from .env and config.yaml

### Business Logic (`backend/services/`)

**memory.py** - Hybrid memory implementation:
- `store_message()` - Stores in BOTH short-term and long-term with session_id in metadata
- `get_short_term_memory()` - Fast partition query for last N messages from current session
- `get_long_term_memory()` - Vector search with session filtering:
  - Includes ALL uploaded documents
  - Includes ONLY current session's conversations (prevents session bleed)
  - Reranks results by keyword overlap
- `assemble_hybrid_context()` - Merges both memory types + persona extraction

**chunking.py** - Document chunking with:
- Sentence parser (links 2 sentences with overlap)
- Phrase parser (links 3 phrases)
- Fixed-size fallback
- Per user rule: Uses phrase/sentence parser with linking for context

**llm.py** - LLM service for response generation

### Frontend (`frontend/lib/frontend_web/live/chat_live.ex`)

Phoenix LiveView application with:
- Real-time chat interface
- Session management sidebar
- Debug modal showing context lineage (short-term, long-term, final prompt)
- Auto-scrolling messages
- Loading states

## Database Schema

### Short-Term Memory
```cql
CREATE TABLE conversation_sessions (
    session_id uuid,
    message_timestamp timestamp,
    role text,
    content text,
    context_docs list<uuid>,
    PRIMARY KEY (session_id, message_timestamp)
) WITH CLUSTERING ORDER BY (message_timestamp DESC)
  AND default_time_to_live = 3600;
```

### Long-Term Memory
```cql
CREATE TABLE documents (
    doc_id uuid,
    chunk_id int,
    content text,
    embedding vector<float, 384>,
    chunk_metadata map<text, text>,
    source_type text,
    created_at timestamp,
    PRIMARY KEY (doc_id, chunk_id)
);

CREATE CUSTOM INDEX documents_embedding_idx 
ON documents(embedding) 
USING 'StorageAttachedIndex';
```

## Configuration

### Memory Tuning (`config/config.yaml`)
```yaml
memory:
  short_term:
    max_messages: 5        # Recent context window
    ttl_seconds: 3600      # 1 hour
  long_term:
    top_k: 2               # Vector search results
    similarity_threshold: 0.7
    enable_cross_session: true
```

### Chunking Strategy
```yaml
chunking:
  strategy: "sentence"      # or "phrase", "fixed"
  chunk_size: 512
  chunk_overlap: 50
  sentence:
    link_sentences: 2       # Link sentences for context
```

## Testing

### End-to-End Test
```bash
./test_system.sh
```
Tests: health check, sessions API, chat conversation with memory recall

### Long-Term Memory Recall Test
```bash
./test_long_term_memory.sh
```
Tests:
- Introduction stored in long-term memory (documents table)
- After 5+ messages, introduction pushed out of short-term window
- Vector search successfully recalls name from long-term memory
- Session isolation (only retrieves from current session)

**How it works:**
1. Introduces with unique name (e.g., "Zephyr7234")
2. Sends 5 filler messages to push introduction out of 5-message context window
3. Asks "What is my name?" - should recall from vector search
4. Verifies unique name appears in response

### Manual Testing Scenarios

**Short-term memory:**
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "message": "My name is Alice"}'

curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "message": "What is my name?"}'
```

**Long-term memory (cross-session):**
```bash
# Session 1
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-1", "message": "I work at MIT studying databases"}'

# Session 2 (different session, should recall via vector search)
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-2", "message": "What do you know about my work?"}'
```

**Document upload:**
```bash
echo "ScyllaDB provides vector search for RAG applications" > test.txt
curl -X POST http://localhost:8000/ingest/upload -F "file=@test.txt"
```

### Python Integration Tests
```bash
cd backend
pytest tests/
```

## Common Operations

### View Logs
```bash
tail -f logs/fastapi.log
tail -f logs/ollama.log
```

### Check Services Status
```bash
./status.sh
```

### Reset Database
```bash
python scylladb_setup/create_schema.py --drop-first
```

### Monitor ScyllaDB
```python
from backend.core.scylla import get_scylla_client

client = get_scylla_client()

# Check document count
result = client.execute("SELECT COUNT(*) as count FROM documents")
print(f"Documents: {result.one()['count']}")

# Check active sessions
result = client.execute("SELECT COUNT(*) as count FROM conversation_sessions")
print(f"Sessions: {result.one()['count']}")
```

## Development Workflow

### Adding New Features

1. **Modify backend API** in `backend/api/`
2. **Update core services** in `backend/core/` or `backend/services/`
3. **Update frontend** in `frontend/lib/frontend_web/live/chat_live.ex`
4. **Test** with `test_system.sh` or manual curl commands
5. **Update config** in `config/config.yaml` if needed

### Debugging

**Enable debug mode in chat request:**
```bash
curl -X POST http://localhost:8000/chat/message?debug=true \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "message": "Hello"}'
```

Returns:
```json
{
  "message": "...",
  "context_type": "hybrid",
  "debug": {
    "short_term": [...],
    "long_term": [...],
    "final_messages": [...],
    "prompt": "..."
  }
}
```

**Frontend debug modal:**
- Click "View Context" button after any response
- Shows short-term memory, long-term matches, and full LLM prompt

### Performance Benchmarks

With 1000 documents (384-dim embeddings):
- Short-term query: ~2ms
- Vector search: ~8ms
- Combined hybrid query: ~10ms
- Document ingestion: ~200ms per document

## Common Pitfalls

### 1. Vector Echoes
**Problem**: Bot repeats user input
**Solution**: `memory.py` filters out vector hits matching current input with reranking

### 2. Short-Term Dominance
**Problem**: Long-term context never appears
**Solution**: Limit short-term to 5 messages max in config

### 3. Session Bleed
**Problem**: Other conversations appear in context
**Solution**: ✓ Implemented - Session isolation via metadata filtering

**How it works:**
- Every message stored in `documents` table includes `session_id` in `chunk_metadata`
- `get_long_term_memory()` applies filtering during vector search:
  - **Documents** (uploaded files): Always included, no filtering
  - **Conversations**: Type-safe string comparison filters out other sessions
  - **Current session**: Messages from same session ARE included (enables long-term recall)

**Example:**
- Session A: "My name is Tyler" → stored with session_id='A'
- Session A (later): "What's my name?" → Finds and includes the introduction via vector search ✓
- Session B: "What's my name?" → Filtered out, doesn't see Session A's data ✓

### 4. Vector Index Lag
**Problem**: Newly stored messages don't appear in vector search results immediately
**Cause**: ScyllaDB's vector index has eventual consistency - there's a ~10 second delay between INSERT and ANN query availability
**Solution**: When testing, wait at least 10 seconds after storing messages before querying

```python
# Store message
store_message(session_id, "user", "My name is Alice")

# Wait for vector index to update
time.sleep(10)

# Now query will find it
results = get_long_term_memory("What is my name?", session_id)
```

**Note**: This only affects long-term memory (vector search). Short-term memory (last 5 messages) uses direct key-based lookup and has no delay.

### 5. Stale Ollama Models
**Problem**: Embeddings or LLM fail
**Solution**: 
```bash
ollama pull all-minilm:l6-v2
ollama pull llama2
```

## Environment Variables

Key variables in `.env`:
```bash
# ScyllaDB Connection
SCYLLADB_HOST=*.cloud.scylladb.com
SCYLLADB_PORT=9042
SCYLLADB_USERNAME=scylla
SCYLLADB_PASSWORD=***
SCYLLADB_KEYSPACE=rag_demo

# Memory Configuration
SHORT_TERM_MAX_MESSAGES=5
SHORT_TERM_TTL=3600
LONG_TERM_TOP_K=4
LONG_TERM_SIMILARITY_THRESHOLD=0.7

# Vector Configuration
VECTOR_DIMENSION=384
SIMILARITY_FUNCTION=COSINE

# LLM Provider
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# Embeddings
EMBEDDINGS_PROVIDER=ollama
EMBEDDINGS_MODEL=all-minilm-l6-v2
```

## Additional Resources

- **README.md** - Architecture and feature details
- **QUICKSTART.md** - 5-minute setup guide
- **TESTING.md** - Detailed testing instructions
- **BUILD_STATUS.md** - Build history and issues
- **COMMANDS.md** - Useful command reference

## Useful Commands

```bash
# Start everything
./start.sh

# Stop everything
./stop.sh

# Check status
./status.sh

# Run all tests
./test_system.sh

# Run long-term memory test only
./test_long_term_memory.sh

# View logs
./logs.sh

# Test database connection
./test_cqlsh.sh

# Backend only
cd backend && python -m uvicorn api.main:app --reload --port 8000

# Frontend only
cd frontend && iex -S mix phx.server
```

## API Documentation

Once running, visit:
- Interactive API docs: http://localhost:8000/docs
- OpenAPI spec: http://localhost:8000/openapi.json

## Deployment

### Docker (Future)
```bash
docker-compose up -d
```

### Production Checklist
- [ ] Set `APP_ENV=production` in .env
- [ ] Change Phoenix signing salt
- [ ] Enable SSL/TLS for ScyllaDB
- [ ] Configure authentication
- [ ] Set up monitoring/metrics (port 9090)
- [ ] Review security settings in config.yaml
- [ ] Configure IP whitelist in ScyllaDB Cloud

## Related Projects

- [chat_cli](https://github.com/tdenton8772/chat_cli) - Part 1: Redis-based memory
- [chat_cli_vector](https://github.com/tdenton8772/chat_cli_vector) - Part 2: FAISS + hybrid memory
- [reinvent_demo](../reinvent_demo) - ScyllaDB vector search IoT demo

## Author

Tyler Denton
- LinkedIn: https://www.linkedin.com/in/tyler-denton-86561565/
- Medium: https://medium.com/@tdenton8772
- Blog Series: Building a Chatbot with Local RAG

---

**Built with**: ScyllaDB • FastAPI • Phoenix LiveView • Ollama • Python • Elixir
