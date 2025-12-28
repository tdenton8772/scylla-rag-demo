#!/bin/bash
################################################################################
# Long-Term Memory Recall Test
# Tests that messages beyond the 5-message context window can be recalled
# via vector search from the documents table
################################################################################

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "================================================================"
echo "Long-Term Memory Recall Test"
echo "================================================================"
echo ""

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${RED}✗ Backend API is not running${NC}"
    echo "Start it with: ./start.sh"
    exit 1
fi

echo -e "${GREEN}✓ Backend API is running${NC}"
echo ""

# Generate unique test data
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
UNIQUE_NAME="Zephyr$(shuf -i 1000-9999 -n 1)"

echo -e "${BLUE}Test Configuration:${NC}"
echo "  Session ID: ${SESSION_ID:0:8}..."
echo "  Unique Name: $UNIQUE_NAME"
echo ""

echo "Step 1: Introducing with unique name..."
echo "----------------------------------------"
INTRO_RESPONSE=$(curl -s -X POST http://localhost:8000/chat/message \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"Hello, my name is $UNIQUE_NAME\"}")

if echo "$INTRO_RESPONSE" | jq -e '.message' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Introduction sent${NC}"
else
    echo -e "${RED}✗ Failed to send introduction${NC}"
    exit 1
fi

# Wait for embedding
sleep 1

echo ""
echo "Step 2: Sending 5 filler messages..."
echo "----------------------------------------"
echo "  (This pushes introduction out of 5-message context window)"

FILLER_MESSAGES=(
    "What is the weather like?"
    "Tell me about databases."
    "What are vectors?"
    "How does RAG work?"
    "What is ScyllaDB?"
)

for i in "${!FILLER_MESSAGES[@]}"; do
    MSG="${FILLER_MESSAGES[$i]}"
    echo -e "  ${YELLOW}[$((i+1))/5]${NC} $MSG"
    
    RESPONSE=$(curl -s -X POST http://localhost:8000/chat/message \
        -H "Content-Type: application/json" \
        -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"$MSG\"}")
    
    if ! echo "$RESPONSE" | jq -e '.message' > /dev/null 2>&1; then
        echo -e "${RED}✗ Failed to send message${NC}"
        exit 1
    fi
    
    sleep 0.5
done

echo -e "${GREEN}✓ All filler messages sent${NC}"

# Wait for vector indexing
echo ""
echo "Waiting 2 seconds for vector indexing..."
sleep 2

echo ""
echo "Step 3: Testing long-term memory recall..."
echo "----------------------------------------"
echo "  Query: 'What is my name?'"
echo ""

RECALL_RESPONSE=$(curl -s -X POST "http://localhost:8000/chat/message?debug=true" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"What is my name?\"}")

# Extract response message
RESPONSE_MESSAGE=$(echo "$RECALL_RESPONSE" | jq -r '.message')

echo "  Response: $RESPONSE_MESSAGE"
echo ""

# Check if name was recalled
if echo "$RESPONSE_MESSAGE" | grep -q "$UNIQUE_NAME"; then
    echo -e "${GREEN}✓ SUCCESS: Long-term memory recall working!${NC}"
    echo "  Found unique name: $UNIQUE_NAME"
    
    # Show debug info
    echo ""
    echo "Debug Information:"
    SHORT_TERM_COUNT=$(echo "$RECALL_RESPONSE" | jq '.debug.short_term | length' 2>/dev/null || echo "N/A")
    LONG_TERM_COUNT=$(echo "$RECALL_RESPONSE" | jq '.debug.long_term | length' 2>/dev/null || echo "N/A")
    echo "  Short-term messages: $SHORT_TERM_COUNT"
    echo "  Long-term matches: $LONG_TERM_COUNT"
    
    exit 0
else
    echo -e "${RED}✗ FAILED: Name not recalled from long-term memory${NC}"
    echo "  Expected: $UNIQUE_NAME"
    echo "  Got: $RESPONSE_MESSAGE"
    
    # Show debug info
    echo ""
    echo "Debug Information:"
    SHORT_TERM_COUNT=$(echo "$RECALL_RESPONSE" | jq '.debug.short_term | length' 2>/dev/null || echo "N/A")
    LONG_TERM_COUNT=$(echo "$RECALL_RESPONSE" | jq '.debug.long_term | length' 2>/dev/null || echo "N/A")
    echo "  Short-term messages: $SHORT_TERM_COUNT"
    echo "  Long-term matches: $LONG_TERM_COUNT"
    
    exit 1
fi
