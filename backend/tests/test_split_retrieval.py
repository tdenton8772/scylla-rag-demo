"""
Split retrieval integration tests (documents vs long-term memory)

These tests assume the backend server is running at http://localhost:8000
and that upload and chat APIs are available.
"""
import os
import io
import time
import uuid
import random
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


def _wait(seconds=3):
    # Helper wait to allow vector index to update
    time.sleep(seconds)


def _post_chat(session_id: str, message: str, debug: bool = False):
    url = f"{BASE_URL}/chat/message"
    if debug:
        url += "?debug=true"
    resp = requests.post(url, json={"session_id": session_id, "message": message})
    assert resp.status_code == 200, f"chat api failed: {resp.status_code} {resp.text[:200]}"
    return resp.json()


def _upload_text_document(filename: str, content: str):
    files = {
        "file": (filename, content.encode("utf-8"), "text/plain"),
    }
    resp = requests.post(f"{BASE_URL}/ingest/upload", files=files)
    assert resp.status_code == 200, f"upload api failed: {resp.status_code} {resp.text[:200]}"
    return resp.json()


def test_documents_query_returns_uploaded_doc_context():
    """
    Upload a small text document containing a unique token and verify that
    querying for that token returns uploaded_document context in the prompt.
    """
    session_id = str(uuid.uuid4())
    doc_token = f"DOC_TOKEN_{random.randint(10000, 99999)}"
    text = f"This is a tiny test document containing the token {doc_token}."

    # Upload document
    _upload_text_document("doc_token.txt", text)

    # Poll for vector index propagation (up to ~15s)
    found_doc = False
    for _ in range(5):
        # Query for the token with debug
        data = _post_chat(session_id, f"What does {doc_token} refer to?", debug=True)

        # Expect at least one long-term item from uploaded_document source
        debug = data.get("debug") or {}
        long_term = debug.get("long_term", [])
        assert isinstance(long_term, list)

        found_doc = any(
            (item.get("source_type") == "uploaded_document" and doc_token in item.get("content", ""))
            for item in long_term
        )

        # If not present in long_term list, check final assembled messages for system context
        if not found_doc:
            final_msgs = debug.get("final_messages", [])
            found_doc = any(
                (m.get("role") == "system" and "[Context from uploaded_document]:" in m.get("content", "") and doc_token in m.get("content", ""))
                for m in final_msgs
            )

        if found_doc:
            break
        _wait(3)

    assert found_doc, "Uploaded document context was not surfaced for document token query"


def test_long_term_query_returns_conversation_context():
    """
    Store a unique token via chat (long-term memory) and verify that
    querying for that token returns long-term (non-document) context.
    """
    session_id = str(uuid.uuid4())
    long_token = f"LONG_TOKEN_{random.randint(10000, 99999)}"

    # Seed long-term by sending a message that will be embedded
    _post_chat(session_id, f"Remember this: {long_token}")

    # Poll for vector index propagation
    found_long = False
    for _ in range(5):
        data = _post_chat(session_id, f"Tell me about {long_token}", debug=True)

        debug = data.get("debug") or {}
        long_term = debug.get("long_term", [])

        found_long = any(
            (item.get("source_type") != "uploaded_document" and long_token in item.get("content", ""))
            for item in long_term
        )

        # Fallback: check final messages system context labels
        if not found_long:
            final_msgs = debug.get("final_messages", [])
            found_long = any(
                (m.get("role") == "system" and long_token in m.get("content", "") and "[Context from uploaded_document]:" not in m.get("content", ""))
                for m in final_msgs
            )

        if found_long:
            break
        _wait(3)

    assert found_long, "Long-term conversation context was not surfaced for long-term token query"


def test_unknown_entity_yields_no_context_and_no_hallucination():
    """
    Ask about an entity we haven't stored in docs or long-term; the model
    should not include context and should say it doesn't have information.
    """
    session_id = str(uuid.uuid4())
    unknown = f"UNKNOWN_{random.randint(100000, 999999)}"

    data = _post_chat(session_id, f"What can you tell me about {unknown}?", debug=True)

    debug = data.get("debug") or {}
    long_term = debug.get("long_term", [])

    # No long-term context expected
    assert len(long_term) == 0, "Expected no long-term context for unknown entity"

    # Response should indicate lack of information (based on updated prompt rules)
    msg = (data.get("message") or "").lower()
    assert ("don't have information" in msg) or ("don't have any information" in msg) or ("do not have information" in msg) or ("no information" in msg), \
        "Model should indicate it lacks information for unknown entity"
