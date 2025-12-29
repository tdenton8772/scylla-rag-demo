# ScyllaDB RAG Demo: Hybrid Memory Architecture

A production-ready RAG (Retrieval Augmented Generation) system showcasing **ScyllaDB as a unified data layer** that replaces both Redis (short-term memory) and traditional vector databases (long-term memory).

## 🎯 Key Innovation: Hybrid Memory

This demo implements the hybrid memory architecture pattern described in Tyler Denton's blog series on building intelligent chatbots:

### Short-Term Memory (Recency-Based)
- **Purpose**: "What did we just talk about?"
- **Storage**: Last 5 messages in `conversation_sessions` table
- **Retrieval**: Fast, partition key-based queries
- **TTL**: 1 hour automatic expiration
- **Use Case**: Maintains conversational flow and context

### Long-Term Memory (Meaning-Based)
- **Purpose**: "What do you remember about X?"
- **Storage**: 
  - Conversation embeddings in `long_term_memory` table (session-scoped)
  - Document embeddings in `documents` table (uploaded files)
- **Retrieval**: Semantic search via ANN (COSINE similarity)
- **Persistence**: Indefinite, searchable across sessions
- **Use Case**: Semantic recall of past conversations and documents

### Hybrid Context Assembly
```
User Query
    ↓
[Recent 5 msgs] + [Top 5 long-term memory] + [Top 5 documents] + [Current input]
    ↓
LLM with full context
```

**Three-Source Retrieval:**
1. **Short-term**: Recent messages from current session
2. **Long-term**: Semantic search on conversation history (session-scoped)
3. **Documents**: Semantic search on uploaded documents (all sessions)

## 🏗️ Architecture

### ScyllaDB as Unified Data Layer
- **No Redis needed**: ScyllaDB handles KV operations with TTL
- **No separate vector DB**: Built-in vector search with SAI
- **Single database**: Simplified operations, reduced latency
- **Automatic TTL**: Short-term memory expires automatically

### Data Flow
```
Document Upload → Chunking → Embedding → ScyllaDB (documents table)

User Message → Store in conversation_sessions (short-term)
     ↓
     → Store in long_term_memory (with embedding, session-scoped)
     ↓
Query Embedding
     ↓
     ├→ Vector Search (long_term_memory) ← Past conversations
     └→ Vector Search (documents) ← Uploaded documents
     ↓
[Documents] + [Long-term Memory] + [Recent Messages] → LLM → Response
```

## 🚀 Quick Start

### Prerequisites

#### MacOS
```bash
# Install Ollama
brew install ollama

# Start Ollama service
brew services start ollama

# Verify Ollama is running
ollama --version  # Should show 0.5.x or higher, NOT 0.0.0
curl http://localhost:11434/api/tags  # Should return JSON

# Pull embedding model (required)
ollama pull nomic-embed-text  # 768-dimension embeddings

# Install Elixir
brew install elixir

# Install Python 3.11+
brew install python@3.11

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate
```

#### Linux (Fedora/RHEL)
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify Ollama is running
ollama --version  # Should show 0.5.x or higher, NOT 0.0.0
curl http://localhost:11434/api/tags  # Should return JSON

# Pull embedding model (required)
ollama pull nomic-embed-text

# Install dependencies
sudo dnf install python3.11 elixir inotify-tools

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate
```

#### Linux (Debian/Ubuntu)
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify Ollama is running
ollama --version
curl http://localhost:11434/api/tags

# Pull embedding model (required)
ollama pull nomic-embed-text

# Install dependencies
sudo apt-get update
sudo apt-get install python3.11 elixir inotify-tools

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate
```

### Setup
```bash
# Clone and navigate
git clone https://github.com/tdenton8772/scylla-rag-demo.git
cd scylla-rag-demo

# Configure environment
cp .env.example .env
# IMPORTANT: Edit .env with required credentials:
#
# ScyllaDB Cloud:
#   - SCYLLADB_HOSTS (comma-separated node list)
#   - SCYLLADB_PORT (19042 for Cloud)
#   - SCYLLADB_USERNAME
#   - SCYLLADB_PASSWORD
#
# LLM Provider (choose one):
#   Option 1 - OpenAI:
#     - LLM_PROVIDER=openai
#     - OPENAI_API_KEY=your_key
#     - OPENAI_MODEL=gpt-4o-mini
#   Option 2 - Grok (x.ai):
#     - LLM_PROVIDER=openai
#     - OPENAI_API_KEY=your_xai_key
#     - OPENAI_BASE_URL=https://api.x.ai/v1
#     - OPENAI_MODEL=grok-beta
#
# Embeddings (uses local Ollama):
#   - EMBEDDINGS_PROVIDER=ollama
#   - EMBEDDINGS_MODEL=nomic-embed-text

# Activate Python virtual environment (if created in Prerequisites)
source venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Initialize ScyllaDB schema
python scylladb_setup/create_schema.py

# Validate the backend is working
cd /path/to/scylla-rag-demo
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &

# Terminal 2 - Frontend:
cd /path/to/scylla-rag-demo/frontend
mix deps.get
mix compile
iex -S mix phx.server

# Visit http://localhost:4000

# How to start Normally
# Will need to update path in this start.sh
./start.sh  # Starts both backend and frontend
```

### Stopping Services
```bash
./stop.sh  # Stops all services
```

### First Conversation
1. Upload a document via the UI
2. Ask: "What's in the document?"
3. Chat for several turns
4. Ask: "What did I ask you earlier?" (tests short-term memory)
5. Start a new session
6. Ask: "What did I tell you about X in the last session?" (tests long-term memory)

## 📊 Database Schema

### Short-Term Memory
```sql
CREATE TABLE conversation_sessions (
    session_id uuid,
    message_timestamp timestamp,
    role text,  -- 'user' or 'assistant'
    content text,
    context_docs list<uuid>,
    PRIMARY KEY (session_id, message_timestamp)
) WITH CLUSTERING ORDER BY (message_timestamp DESC)
  AND default_time_to_live = 3600;  -- 1 hour
```

### Long-Term Conversation Memory
```sql
CREATE TABLE long_term_memory (
    session_id uuid,
    chunk_id bigint,
    content text,
    embedding vector<float, 768>,
    metadata map<text, text>,
    created_at timestamp,
    PRIMARY KEY ((session_id), chunk_id)
) WITH CLUSTERING ORDER BY (chunk_id ASC);

CREATE CUSTOM INDEX long_term_memory_embedding_idx 
ON long_term_memory(embedding) 
USING 'vector_index'
WITH OPTIONS = {'similarity_function': 'cosine'};
```

### Document Storage
```sql
CREATE TABLE documents (
    doc_id uuid,
    chunk_id int,
    content text,
    embedding vector<float, 768>,
    chunk_metadata map<text, text>,
    source_type text,
    created_at timestamp,
    PRIMARY KEY (doc_id, chunk_id)
) WITH CLUSTERING ORDER BY (chunk_id ASC);

CREATE CUSTOM INDEX documents_embedding_idx 
ON documents(embedding) 
USING 'vector_index'
WITH OPTIONS = {'similarity_function': 'cosine'};
```

### Metadata
```sql
CREATE TABLE document_metadata (
    doc_id uuid PRIMARY KEY,
    filename text,
    upload_timestamp timestamp,
    total_chunks int,
    status text
);
```

## 🔄 Triple Storage Pattern

Every conversation message is stored **twice**:
1. **Short-term**: Raw text in `conversation_sessions` (fast, recent, TTL=1hr)
2. **Long-term**: Embedded in `long_term_memory` (semantic search, session-scoped)

Uploaded documents are stored separately:
3. **Documents**: Embedded in `documents` table (semantic search, all sessions)

This enables:
- Immediate conversational continuity (short-term)
- Semantic recall of past conversations within session (long-term memory)
- Semantic search across all uploaded documents (documents)
- Clean separation between conversation history and uploaded content
- Automatic cleanup of old sessions via TTL

## 🎛️ Configuration

### Memory Tuning (`config/config.yaml`)
```yaml
memory:
  short_term:
    max_messages: 5  # Recent context window
    ttl_seconds: 3600  # 1 hour
  
  long_term:
    top_k: 4  # Vector search results
    similarity_threshold: 0.7  # Minimum relevance
    enable_cross_session: true  # Search all sessions

chunking:
  strategy: "sentence"  # or "phrase"
  chunk_size: 512
  chunk_overlap: 50
  
embeddings:
  model: "nomic-embed-text"
  dimensions: 768
```

### Agent Rules (`config/agent_rules.md`)
See [Agent Rules Documentation](config/agent_rules.md) for response boundaries, citation requirements, and behavior guidelines.

## ⚠️ Common Pitfalls

### 1. Vector Echoes
**Problem**: Bot repeats user input  
**Solution**: Filter out vector hits matching current input

### 2. Short-Term Dominance
**Problem**: Long-term context never appears  
**Solution**: Limit short-term to 5 messages max

### 3. Session Bleed
**Problem**: Other conversations appear in context  
**Solution**: Store `session_id` in chunk_metadata, post-filter results

### 4. Irrelevant Context
**Problem**: Unrelated content in context  
**Solution**: Set similarity threshold to 0.7+, limit top_k to 4

## 🧪 Testing

```bash
# Unit tests
pytest backend/tests/unit/

# Integration tests (requires ScyllaDB)
pytest backend/tests/integration/

# End-to-end tests
pytest backend/tests/e2e/

# Test memory patterns
python backend/tests/test_hybrid_memory.py
```

### Manual Test Scenarios
1. **Short-term recall**: Ask about recent messages
2. **Long-term recall**: Query past sessions
3. **Document recall**: Questions about uploaded docs
4. **Session isolation**: Verify no cross-contamination
5. **TTL expiration**: Check old sessions disappear

## 📈 Performance

### ScyllaDB Advantages
- **Sub-10ms vector queries** with ANN index
- **Linear scalability** for concurrent sessions
- **Automatic TTL** for memory management
- **Single database** reduces operational complexity

### Benchmarks (5000 documents, 384-dim embeddings)
- Short-term query: ~2ms
- Long-term vector search: ~8ms
- Combined hybrid query: ~10ms
- Document ingestion: ~500 docs/sec

## 🚢 Deployment

### Docker Compose (Local)
```bash
docker-compose up -d
```

### Production (Docker)
```bash
# Build images
docker build -t rag-backend ./backend
docker build -t rag-frontend ./frontend

# Run containers
docker run -d -p 8000:8000 rag-backend
docker run -d -p 3000:3000 rag-frontend
```

## 🔗 Related Projects

- [chat_cli](https://github.com/tdenton8772/chat_cli) - Part 1: Redis-based memory
- [chat_cli_vector](https://github.com/tdenton8772/chat_cli_vector) - Part 2: FAISS + hybrid memory
- [reinvent_demo](../reinvent_demo) - ScyllaDB vector search IoT demo

## 📚 References

- [Building a Chatbot with Local RAG (Part 1: Just Memory)](https://medium.com/@tdenton8772/building-a-chatbot-with-local-rag-part-1-just-memory-62876ad1dccc)
- [Building a Chatbot with Local RAG (Part 2: Vectors)](https://medium.com/@tdenton8772/building-a-chatbot-with-local-rag-part-2-vectors)
- [ScyllaDB Vector Search Documentation](https://cloud.docs.scylladb.com/stable/vector-search/)
- [Ollama Embeddings](https://ollama.ai/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write tests
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 👤 Author

Tyler Denton  
LinkedIn: https://www.linkedin.com/in/tyler-denton-86561565/  
Medium: https://medium.com/@tdenton8772

---

**Built with**: ScyllaDB • FastAPI • Phoenix LiveView • Ollama • Python • Elixir
