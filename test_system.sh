#!/bin/bash
set -e

echo "=================================================="
echo "ScyllaDB RAG Demo - End-to-End System Test"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="$3"
    
    echo -n "Testing $name... "
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} (HTTP $status)"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} (Expected $expected_status, got $status)"
        ((TESTS_FAILED++))
        return 1
    fi
}

test_chat_conversation() {
    echo -n "Testing chat conversation with memory... "
    
    # Generate random session ID
    SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
    
    # First message
    RESPONSE1=$(curl -s -X POST http://localhost:8000/chat/message \
        -H "Content-Type: application/json" \
        -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"Hello, my name is TestUser\"}")
    
    if echo "$RESPONSE1" | jq -e '.message' > /dev/null 2>&1; then
        # Second message to test memory
        RESPONSE2=$(curl -s -X POST http://localhost:8000/chat/message \
            -H "Content-Type: application/json" \
            -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"What is my name?\"}")
        
        if echo "$RESPONSE2" | jq -e '.message' | grep -qi "TestUser"; then
            echo -e "${GREEN}✓${NC} Memory recall working"
            ((TESTS_PASSED++))
            return 0
        else
            echo -e "${RED}✗${NC} Memory recall failed"
            ((TESTS_FAILED++))
            return 1
        fi
    else
        echo -e "${RED}✗${NC} Chat endpoint failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

test_sessions_api() {
    echo -n "Testing sessions API... "
    
    SESSIONS=$(curl -s http://localhost:8000/chat/sessions)
    
    if echo "$SESSIONS" | jq -e '. | length' > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Sessions list retrieved"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} Sessions API failed"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Check if services are running
echo "1. Checking backend API..."
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${RED}✗ Backend API is not running on port 8000${NC}"
    echo "Please start it with: ./start.sh"
    exit 1
fi
echo -e "${GREEN}✓ Backend API is running${NC}"
echo ""

echo "2. Checking frontend UI..."
if ! curl -s http://localhost:4000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Frontend UI is not running on port 4000${NC}"
    echo "Start it with: cd frontend && PORT=4000 mix phx.server"
else
    echo -e "${GREEN}✓ Frontend UI is running${NC}"
fi
echo ""

# Run backend tests
echo "3. Running Backend API Tests..."
echo "================================"
test_endpoint "Health endpoint" "http://localhost:8000/health" "200"
test_endpoint "Root endpoint" "http://localhost:8000/" "200"
test_sessions_api
test_chat_conversation
echo ""

# Run Python backend tests if available
if [ -f "backend/tests/test_chat_api.py" ]; then
    echo "4. Running Python Integration Tests..."
    echo "======================================="
    if python backend/tests/test_chat_api.py; then
        echo -e "${GREEN}✓ All Python tests passed${NC}"
        ((TESTS_PASSED+=4))
    else
        echo -e "${RED}✗ Some Python tests failed${NC}"
        ((TESTS_FAILED+=1))
    fi
    echo ""
fi

# Summary
echo "=================================================="
echo "Test Summary"
echo "=================================================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "System is ready for demo:"
    echo "  • Backend API: http://localhost:8000"
    echo "  • Frontend UI: http://localhost:4000"
    echo "  • API Docs: http://localhost:8000/docs"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
