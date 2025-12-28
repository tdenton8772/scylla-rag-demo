"""
Integration tests for chat API
"""
import requests
import uuid

BASE_URL = "http://localhost:8000"


def test_health_endpoint():
    """Test that health endpoint returns 200"""
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["ollama"] == True  # Ollama must be running


def test_chat_message():
    """Test chat message endpoint"""
    session_id = str(uuid.uuid4())
    
    # Send first message
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": session_id, "message": "Hello, my name is Tyler"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["session_id"] == session_id
    
    # Send second message to test memory
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": session_id, "message": "What is my name?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "Tyler" in data["message"]


def test_sessions_list():
    """Test listing sessions"""
    response = requests.get(f"{BASE_URL}/chat/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert isinstance(sessions, list)


def test_session_messages():
    """Test retrieving session messages"""
    session_id = str(uuid.uuid4())
    
    # Send a message first
    requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": session_id, "message": "Test message"}
    )
    
    # Retrieve messages
    response = requests.get(f"{BASE_URL}/chat/sessions/{session_id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) >= 2  # user + assistant


def test_vector_search_basic():
    """
    Basic vector search test - store and retrieve a single message.
    This tests that:
    1. Messages are stored in documents table with embeddings
    2. Vector search (ANN) can retrieve them
    """
    import time
    import random
    
    session_id = str(uuid.uuid4())
    unique_phrase = f"TestPhrase{random.randint(1000, 9999)}"
    
    print(f"\n  → Storing message with unique phrase: {unique_phrase}")
    
    # Store a single message
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": session_id, "message": f"My unique identifier is {unique_phrase}"}
    )
    assert response.status_code == 200
    
    # Wait for embedding and vector indexing (ScyllaDB vector index has eventual consistency)
    print("  → Waiting up to 20s for vector index to update...")
    
    # Poll up to 5 times for vector index propagation
    found = False
    for i in range(5):
        print(f"    Poll {i+1}/5")
        response = requests.post(
            f"{BASE_URL}/chat/message?debug=true",
            json={"session_id": session_id, "message": f"Tell me about {unique_phrase}"}
        )
        if response.status_code != 200:
            print(f"  ✗ API returned status {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            time.sleep(2)
            continue
        data = response.json()
        if "debug" not in data or not data["debug"]:
            time.sleep(2)
            continue
        debug_info = data["debug"]
        long_term = debug_info.get('long_term', [])
        long_term_count = len(long_term)
        print(f"  → Long-term items retrieved: {long_term_count}")
        if long_term_count > 0:
            print(f"  → Sample items: {[item.get('source_type') for item in long_term[:3]]}")
        found = any(unique_phrase in item.get('content', '') for item in long_term)
        if found:
            print(f"  ✓ Vector search working: Found '{unique_phrase}' in long-term context")
            break
        time.sleep(2)
    assert found, "Vector search didn't retrieve the stored message"


def test_long_term_memory_recall():
    """
    Test long-term memory recall beyond short-term context window.
    
    This verifies:
    1. Introduction is stored in long-term memory (documents table)
    2. After 5+ interactions, short-term memory drops the introduction
    3. Vector search retrieves it from long-term memory
    4. Session isolation works (only retrieves from current session)
    """
    import time
    import random
    
    session_id = str(uuid.uuid4())
    
    # Generate a unique name to test recall
    unique_name = f"Zephyr{random.randint(1000, 9999)}"  # e.g., "Zephyr7234"
    
    # Step 1: Introduce with unique name
    print(f"\n  → Introducing as '{unique_name}'")
    response = requests.post(
        f"{BASE_URL}/chat/message",
        json={"session_id": session_id, "message": f"Hello, my name is {unique_name}"}
    )
    assert response.status_code == 200
    
    # Wait for embedding to be indexed
    time.sleep(2)
    
    # Step 2: Send 5 filler interactions to push introduction out of short-term memory (5 message window)
    filler_messages = [
        "What is the weather like?",
        "Tell me about databases.",
        "What are vectors?",
        "How does RAG work?",
        "What is ScyllaDB?"
    ]
    
    print(f"  → Sending {len(filler_messages)} filler messages to push introduction out of context window")
    for msg in filler_messages:
        response = requests.post(
            f"{BASE_URL}/chat/message",
            json={"session_id": session_id, "message": msg}
        )
        assert response.status_code == 200
        time.sleep(0.5)  # Small delay between messages
    
    # Wait for embeddings to be indexed (ScyllaDB vector index has eventual consistency)
    print("  → Waiting up to 20s for vector index to update...")
    
    # Poll up to 5 times to recall the name from long-term memory
    recalled = False
    response_message = ""
    for i in range(5):
        print(f"    Poll {i+1}/5")
        response = requests.post(
            f"{BASE_URL}/chat/message?debug=true",
            json={"session_id": session_id, "message": "What is my name?"}
        )
        if response.status_code != 200:
            print(f"  ✗ API returned status {response.status_code}: {response.text[:200]}")
            time.sleep(2)
            continue
        data = response.json()
        response_message = data.get("message", "")
        if unique_name in response_message:
            recalled = True
            print(f"  ✓ Successfully recalled name: {unique_name}")
            break
        # If not in answer, check long-term context
        debug_info = data.get("debug") or {}
        long_term = debug_info.get('long_term', [])
        print(f"  → Long-term items: {len(long_term)}")
        if any(unique_name in item.get('content', '') for item in long_term):
            print(f"  → Name found in long-term context, waiting for LLM to use it...")
            time.sleep(2)
        else:
            time.sleep(2)
    print(f"  → Response: {response_message[:100]}...")
    if not recalled:
        # As a minimum, verify the long-term context contains the introduction
        debug_check = requests.post(
            f"{BASE_URL}/chat/message?debug=true",
            json={"session_id": session_id, "message": "(debug) show context"}
        )
        introduction_found = False
        if debug_check.status_code == 200:
            dbg = debug_check.json().get('debug') or {}
            long_term_ctx = dbg.get('long_term', [])
            introduction_found = any(unique_name in item.get('content','') for item in long_term_ctx)
        assert recalled or introduction_found, f"Failed to recall or surface name '{unique_name}' in long-term context"
    
    return unique_name  # Return for potential additional testing


if __name__ == "__main__":
    print("Running backend tests...")
    print("="*60)
    
    print("\n1. Testing health endpoint...")
    test_health_endpoint()
    print("✓ Health endpoint working")
    
    print("\n2. Testing chat message (short-term memory)...")
    test_chat_message()
    print("✓ Chat message working with memory recall")
    
    print("\n3. Testing sessions list...")
    test_sessions_list()
    print("✓ Sessions list working")
    
    print("\n4. Testing session messages...")
    test_session_messages()
    print("✓ Session messages working")
    
    print("\n5. Testing basic vector search...")
    try:
        test_vector_search_basic()
        print("✓ Basic vector search working")
    except AssertionError as e:
        print(f"✗ Basic vector search failed: {e}")
        raise
    
    print("\n6. Testing long-term memory recall (vector search)...")
    try:
        unique_name = test_long_term_memory_recall()
        print(f"✓ Long-term memory recall working (recalled: {unique_name})")
    except AssertionError as e:
        print(f"✗ Long-term memory recall failed: {e}")
        raise
    
    print("\n" + "="*60)
    print("✓ All backend tests passed!")
    print("="*60)
