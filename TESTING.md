# Testing the Backend

## Setup

1. **Install Dependencies**
```bash
cd backend
pip install -r requirements.txt
```

2. **Initialize Database**
```bash
cd /Users/tdenton/Development/scylla-rag-demo
python scylladb_setup/create_schema.py
```

3. **Start Ollama**
```bash
ollama serve
# In another terminal:
ollama pull all-minilm:l6-v2
ollama pull llama2
```

4. **Start Backend**
```bash
cd backend
python -m uvicorn api.main:app --reload --port 8000
```

## Test Endpoints

### 1. Health Check
```bash
curl http://localhost:8000/health
```

Expected:
```json
{
  "status": "healthy",
  "scylladb": true,
  "ollama": true,
  "embeddings_model": "all-minilm:l6-v2",
  "llm_model": "llama2"
}
```

### 2. Upload Document
```bash
# Create a test file
echo "ScyllaDB is a high-performance NoSQL database. It provides vector search capabilities for RAG applications." > test_doc.txt

# Upload it
curl -X POST http://localhost:8000/ingest/upload \
  -F "file=@test_doc.txt"
```

Expected:
```json
{
  "doc_id": "...",
  "filename": "test_doc.txt",
  "total_chunks": 1,
  "status": "completed",
  "message": "Successfully processed 1 chunks"
}
```

### 3. Chat (Non-streaming)
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "message": "What is ScyllaDB?"
  }'
```

Expected:
```json
{
  "session_id": "test-session-123",
  "message": "...",
  "context_type": "hybrid"
}
```

### 4. Test Hybrid Memory

**Step 1: First message**
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "memory-test",
    "message": "My name is Tyler and I work with databases"
  }'
```

**Step 2: Follow-up (tests short-term memory)**
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "memory-test",
    "message": "What did I just tell you?"
  }'
```

**Step 3: New session (tests long-term memory)**
```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "new-session-456",
    "message": "Do you remember anything about Tyler?"
  }'
```

### 5. Clear Session
```bash
curl -X POST http://localhost:8000/chat/clear \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123"
  }'
```

## WebSocket Testing

Use a WebSocket client or this Python script:

```python
import asyncio
import websockets
import json

async def test_chat():
    uri = "ws://localhost:8000/chat/ws"
    
    async with websockets.connect(uri) as websocket:
        # Send message
        await websocket.send(json.dumps({
            "session_id": "ws-test",
            "message": "Hello! What is RAG?"
        }))
        
        # Receive streaming response
        full_response = ""
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "chunk":
                print(data["content"], end="", flush=True)
                full_response += data["content"]
            elif data.get("type") == "complete":
                print(f"\n\nContext type: {data['context_type']}")
                break
            elif data.get("type") == "error":
                print(f"Error: {data['error']}")
                break

asyncio.run(test_chat())
```

## Verify Database

```python
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
import os
from dotenv import load_dotenv

load_dotenv()

auth = PlainTextAuthProvider(
    username=os.getenv('SCYLLADB_USERNAME'),
    password=os.getenv('SCYLLADB_PASSWORD')
)
cluster = Cluster(
    os.getenv('SCYLLADB_HOSTS').split(','),
    port=int(os.getenv('SCYLLADB_PORT')),
    auth_provider=auth
)
session = cluster.connect('rag_demo')

# Check documents (long-term)
print("Documents (long-term memory):")
result = session.execute('SELECT COUNT(*) as count FROM documents')
print(f"  Total: {result.one()['count']}")

# Check sessions (short-term)
print("\nConversation sessions (short-term memory):")
result = session.execute('SELECT COUNT(*) as count FROM conversation_sessions')
print(f"  Total: {result.one()['count']}")

# Check metadata
print("\nDocument metadata:")
result = session.execute('SELECT filename, total_chunks, status FROM document_metadata')
for row in result:
    print(f"  {row['filename']}: {row['total_chunks']} chunks ({row['status']})")

cluster.shutdown()
```

## Expected Behavior

1. **Document Upload**: Chunks document, generates embeddings, stores in `documents` table
2. **Chat**: 
   - Stores user message in BOTH tables (short-term + long-term with embedding)
   - Retrieves last 5 messages from `conversation_sessions` (short-term)
   - Performs vector search on `documents` for top 4 matches (long-term)
   - Merges context and generates LLM response
   - Stores assistant response in BOTH tables
3. **Memory**:
   - Short-term: Fast, recent messages only
   - Long-term: Semantic search across all documents and past conversations
   - TTL: Sessions auto-expire after 1 hour

## Troubleshooting

See QUICKSTART.md for common issues and solutions.
