# Quick Start Guide

Get the ScyllaDB RAG demo running in 5 minutes.

## Prerequisites

```bash
# macOS
brew install ollama python@3.11 elixir postgresql

# Pull required models
ollama pull all-minilm:l6-v2  # Embedding model (384 dims)
ollama pull llama2             # LLM (optional, can use OpenAI)
```

## Step 1: ScyllaDB Setup

If you don't have ScyllaDB Cloud account:
1. Go to https://cloud.scylladb.com
2. Create a free account
3. Create a cluster (use free tier)
4. Note your connection credentials

## Step 2: Configure Environment

```bash
cp .env.example .env
# Edit .env with your ScyllaDB credentials
```

Your `.env` should contain:
```bash
SCYLLA_HOSTS=node1.cloud.scylladb.com,node2.cloud.scylladb.com
SCYLLA_PORT=19042
SCYLLA_USERNAME=your_username
SCYLLA_PASSWORD=your_password
SCYLLA_KEYSPACE=rag_demo
```

## Step 3: Initialize Database

```bash
cd backend
pip install -r requirements.txt
python scylladb_setup/create_schema.py
```

You should see:
```
✓ Created keyspace: rag_demo
✓ Created table: conversation_sessions
✓ Created table: documents
✓ Created table: document_metadata
✓ Created vector index: documents_embedding_idx
```

## Step 4: Start Backend

```bash
# From backend/ directory
uvicorn api.main:app --reload --port 8000
```

Backend will be available at: http://localhost:8000

## Step 5: Start Frontend

```bash
# In new terminal
cd frontend
mix deps.get
iex -S mix phx.server
```

Frontend will be available at: http://localhost:4000

## Step 6: Try It Out

### Test 1: Upload a Document
1. Visit http://localhost:4000
2. Click "Upload Document"
3. Select a `.txt`, `.md`, or `.pdf` file
4. Wait for "Document processed successfully"

### Test 2: Ask About the Document
```
You: "What's this document about?"
Assistant: [Response based on document content with citations]
```

### Test 3: Short-Term Memory
```
You: "The capital of France is Paris"
Assistant: "Got it, noted that the capital of France is Paris."
You: "What did I just tell you?"
Assistant: "You mentioned that the capital of France is Paris. [From our conversation on 2025-12-26]"
```

### Test 4: Long-Term Memory
1. Start a new session (click "New Chat")
2. Ask: "What did I say about France in our last conversation?"
3. The bot should find the relevant message via vector search!

## Common Commands

### Backend API

```bash
# Health check
curl http://localhost:8000/health

# Upload document via API
curl -X POST http://localhost:8000/ingest \
  -F "file=@document.txt"

# Clear conversation
curl -X POST http://localhost:8000/memory/clear \
  -H "Content-Type: application/json" \
  -d '{"session_id": "your-session-id"}'
```

### Check ScyllaDB

```python
# Quick verification script
python -c "
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
import os
from dotenv import load_dotenv

load_dotenv()
auth = PlainTextAuthProvider(
    username=os.getenv('SCYLLA_USERNAME'),
    password=os.getenv('SCYLLA_PASSWORD')
)
cluster = Cluster(
    os.getenv('SCYLLA_HOSTS').split(','),
    port=int(os.getenv('SCYLLA_PORT')),
    auth_provider=auth
)
session = cluster.connect('rag_demo')

# Check documents
result = session.execute('SELECT COUNT(*) FROM documents')
print(f'Documents: {result.one().count}')

# Check sessions
result = session.execute('SELECT COUNT(*) FROM conversation_sessions')
print(f'Session messages: {result.one().count}')

cluster.shutdown()
"
```

## Troubleshooting

### "Connection refused" to Ollama
```bash
# Make sure Ollama is running
ollama serve

# In another terminal
ollama list  # Should show all-minilm:l6-v2 and llama2
```

### "NoHostAvailable" from ScyllaDB
1. Check `.env` credentials are correct
2. Verify cluster is running in ScyllaDB Cloud console
3. Check IP whitelist in ScyllaDB Cloud (add your IP)

### "Module not found" errors
```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
mix deps.get
```

### Port already in use
```bash
# Change ports in config.yaml
api:
  port: 8001  # Instead of 8000

phoenix:
  url:
    port: 4001  # Instead of 4000
```

## Next Steps

1. **Read the full README.md** for architecture details
2. **Review config/agent_rules.md** to understand bot behavior
3. **Tune config/config.yaml** for your use case
4. **Check config/agent_rules.md** for response guidelines

## Useful Development Commands

```bash
# Run tests
cd backend
pytest tests/

# Check logs
tail -f backend/logs/app.log

# Monitor ScyllaDB queries (development mode)
# Set logging.log_queries: true in config.yaml

# Reset everything
python scylladb_setup/create_schema.py --drop-first
```

## Demo Scenarios

### Scenario 1: Document Q&A
- Upload: technical documentation
- Ask: specific technical questions
- Observe: Citations and source attribution

### Scenario 2: Multi-Turn Conversation
- Have a 10-message conversation about a topic
- Ask: "What did I say about X earlier?"
- Observe: Short-term memory in action

### Scenario 3: Cross-Session Recall
- Session 1: Tell the bot about your project
- Session 2 (new): Ask "What do you know about my project?"
- Observe: Long-term memory via vector search

### Scenario 4: Mixed Context
- Upload a document
- Discuss the document
- Ask questions that require both document + conversation context
- Observe: Hybrid memory assembly

## Performance Expectations

With 1000 documents (384-dim embeddings):
- **Short-term query**: ~2ms
- **Vector search**: ~8ms  
- **Full hybrid query**: ~10ms
- **Document ingestion**: ~200ms per document

## Getting Help

- **Issues**: Check the troubleshooting section above
- **Config**: Review `config/config.yaml` comments
- **Architecture**: See `README.md` for detailed explanation
- **Rules**: See `config/agent_rules.md` for bot behavior

---

**Ready to build?** Check out the implementation plan or start with Phase 1!
