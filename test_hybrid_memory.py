#!/usr/bin/env python3
"""
Comprehensive Test for Hybrid Memory Architecture
Tests both short-term (recent messages) and long-term (vector search) memory
"""

import requests
import json
import uuid
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"
SESSION_ID = str(uuid.uuid4())

def test_document_upload():
    """Test 1: Upload a document with specific knowledge"""
    print("\n" + "="*80)
    print("TEST 1: Document Upload (Long-term Memory)")
    print("="*80)
    
    # Create a test document with specific facts
    test_content = """
    The Quantum Computing Lab at MIT has three main research areas:
    1. Quantum error correction using surface codes
    2. Topological quantum computing with anyons
    3. Quantum machine learning algorithms
    
    Dr. Sarah Chen leads the quantum error correction team.
    The lab was founded in 2018 and has 15 researchers.
    Their latest paper on quantum supremacy was published in Nature 2024.
    """
    
    with open('test_knowledge.txt', 'w') as f:
        f.write(test_content)
    
    with open('test_knowledge.txt', 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/ingest/upload",
            files={'file': ('test_knowledge.txt', f, 'text/plain')}
        )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Document uploaded: {data['filename']}")
        print(f"  - Total chunks: {data['total_chunks']}")
        print(f"  - Doc ID: {data['doc_id']}")
        return True
    else:
        print(f"✗ Upload failed: {response.status_code}")
        print(f"  {response.text}")
        return False


def test_short_term_memory():
    """Test 2: Build up short-term memory with conversation context"""
    print("\n" + "="*80)
    print("TEST 2: Short-term Memory (Recent Conversation)")
    print("="*80)
    
    conversation = [
        "My name is Alice and I'm a graduate student.",
        "I'm working on my thesis about distributed databases.",
        "I'm particularly interested in ScyllaDB.",
        "Can you help me understand vector search?"
    ]
    
    print(f"Session ID: {SESSION_ID}\n")
    
    for i, msg in enumerate(conversation, 1):
        print(f"{i}. User: {msg}")
        response = requests.post(
            f"{BASE_URL}/chat/message",
            json={"session_id": SESSION_ID, "message": msg},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Assistant: {data['message'][:100]}...")
            print(f"   Context: {data.get('context_type', 'N/A')}")
        else:
            print(f"   ✗ Error: {response.status_code}")
        
        time.sleep(1)  # Brief pause between messages
    
    return True


def test_short_term_recall():
    """Test 3: Ask a question that requires short-term memory"""
    print("\n" + "="*80)
    print("TEST 3: Short-term Memory Recall")
    print("="*80)
    
    # This should recall Alice's name from recent conversation
    question = "What's my name and what am I studying?"
    print(f"User: {question}")
    
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": SESSION_ID, "message": question},
        timeout=60
    )
    
    if response.status_code == 200:
        data = response.json()
        answer = data['message']
        print(f"\nAssistant: {answer}")
        
        # Check if it recalls the information
        if "Alice" in answer or "alice" in answer:
            print("\n✓ SHORT-TERM MEMORY WORKING: Recalled name from conversation")
        else:
            print("\n✗ SHORT-TERM MEMORY ISSUE: Did not recall name")
        
        if "distributed database" in answer.lower() or "thesis" in answer.lower():
            print("✓ SHORT-TERM MEMORY WORKING: Recalled study topic")
        else:
            print("✗ SHORT-TERM MEMORY ISSUE: Did not recall study topic")
        
        return True
    else:
        print(f"✗ Error: {response.status_code}")
        return False


def test_long_term_recall():
    """Test 4: Ask a question that requires long-term memory (vector search)"""
    print("\n" + "="*80)
    print("TEST 4: Long-term Memory Recall (Vector Search)")
    print("="*80)
    
    # This should retrieve from the uploaded document via vector search
    question = "Who leads the quantum error correction team?"
    print(f"User: {question}")
    
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": SESSION_ID, "message": question},
        timeout=60
    )
    
    if response.status_code == 200:
        data = response.json()
        answer = data['message']
        print(f"\nAssistant: {answer}")
        
        # Check if it found the information from the document
        if "Sarah Chen" in answer or "Dr. Chen" in answer:
            print("\n✓ LONG-TERM MEMORY WORKING: Retrieved from uploaded document")
        else:
            print("\n✗ LONG-TERM MEMORY ISSUE: Did not retrieve from document")
            print("  (This could mean vector search isn't finding the relevant chunks)")
        
        return True
    else:
        print(f"✗ Error: {response.status_code}")
        return False


def test_hybrid_memory():
    """Test 5: Question requiring both short-term and long-term memory"""
    print("\n" + "="*80)
    print("TEST 5: Hybrid Memory (Both Short-term + Long-term)")
    print("="*80)
    
    # This requires both: Alice's context from conversation AND knowledge from document
    question = "Based on what I'm studying, what research area at the MIT Quantum Lab would be most relevant to me?"
    print(f"User: {question}")
    
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": SESSION_ID, "message": question},
        timeout=60
    )
    
    if response.status_code == 200:
        data = response.json()
        answer = data['message']
        print(f"\nAssistant: {answer}")
        
        has_short_term = any(term in answer.lower() for term in ["distributed", "database", "scylladb", "alice"])
        has_long_term = any(term in answer.lower() for term in ["quantum", "mit", "research", "error correction"])
        
        if has_short_term and has_long_term:
            print("\n✓ HYBRID MEMORY WORKING: Used both short-term and long-term context")
        elif has_short_term:
            print("\n⚠ PARTIAL: Used short-term memory but not long-term")
        elif has_long_term:
            print("\n⚠ PARTIAL: Used long-term memory but not short-term")
        else:
            print("\n✗ HYBRID MEMORY ISSUE: Not using context effectively")
        
        return True
    else:
        print(f"✗ Error: {response.status_code}")
        return False


def verify_database():
    """Verify data in ScyllaDB"""
    print("\n" + "="*80)
    print("DATABASE VERIFICATION")
    print("="*80)
    
    import os
    from dotenv import load_dotenv
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider
    from cassandra.query import dict_factory
    
    load_dotenv('.env')
    
    auth = PlainTextAuthProvider(
        username=os.getenv('SCYLLADB_USERNAME'),
        password=os.getenv('SCYLLADB_PASSWORD')
    )
    
    cluster = Cluster(
        os.getenv('SCYLLADB_HOSTS').split(','),
        port=int(os.getenv('SCYLLADB_PORT')),
        auth_provider=auth
    )
    
    session = cluster.connect(os.getenv('SCYLLADB_KEYSPACE'))
    session.row_factory = dict_factory
    
    # Count entries
    docs = list(session.execute("SELECT COUNT(*) as count FROM documents"))
    sessions = list(session.execute(f"SELECT COUNT(*) as count FROM conversation_sessions WHERE session_id = {uuid.UUID(SESSION_ID)}"))
    
    print(f"\nTotal documents/chunks in long-term memory: {docs[0]['count']}")
    print(f"Messages in short-term memory for this session: {sessions[0]['count']}")
    
    # Show recent conversation messages
    print("\nRecent conversation messages:")
    result = session.execute(
        f"SELECT role, content, message_timestamp FROM conversation_sessions WHERE session_id = {uuid.UUID(SESSION_ID)} LIMIT 10"
    )
    for i, row in enumerate(result, 1):
        print(f"  {i}. [{row['role']}] {row['content'][:80]}...")
    
    cluster.shutdown()


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("HYBRID MEMORY ARCHITECTURE TEST SUITE")
    print("ScyllaDB RAG Demo")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Test sequence
        if not test_document_upload():
            print("\n⚠ Skipping remaining tests due to upload failure")
            return
        
        time.sleep(2)  # Wait for embeddings to be generated
        
        test_short_term_memory()
        test_short_term_recall()
        test_long_term_recall()
        test_hybrid_memory()
        
        # Final verification
        verify_database()
        
        print("\n" + "="*80)
        print("TEST SUITE COMPLETE")
        print("="*80)
        print(f"Session ID: {SESSION_ID}")
        print("Check logs for detailed information")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n✗ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
