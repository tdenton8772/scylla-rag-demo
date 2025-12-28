#!/bin/bash
################################################################################
# ScyllaDB RAG Demo - Startup Script
# Starts all services with logging
################################################################################

set -e

PROJECT_DIR="/Users/tdenton/Development/scylla-rag-demo"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.pids"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR"

echo "================================================================"
echo "Starting ScyllaDB RAG Demo"
echo "================================================================"
echo ""

# Function to check if a process is running
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function to start a service
start_service() {
    local name=$1
    local pid_file="$PID_DIR/$name.pid"
    local log_file="$LOG_DIR/$name.log"
    local command=$2
    
    if is_running "$pid_file"; then
        echo -e "${YELLOW}⚠ $name is already running${NC}"
        return
    fi
    
    echo -e "${GREEN}▶ Starting $name...${NC}"
    echo "  Log: $log_file"
    
    # Start the service in background and save PID
    eval "$command" > "$log_file" 2>&1 &
    echo $! > "$pid_file"
    
    sleep 2
    
    if is_running "$pid_file"; then
        echo -e "${GREEN}✓ $name started successfully${NC}"
    else
        echo -e "${RED}✗ $name failed to start${NC}"
        echo "  Check log: $log_file"
    fi
    echo ""
}

# 1. Check Ollama
echo -e "${GREEN}▶ Checking Ollama...${NC}"
if ! pgrep -x "ollama" > /dev/null; then
    echo "  Starting Ollama service..."
    start_service "ollama" "ollama serve"
else
    echo -e "${GREEN}✓ Ollama is already running${NC}"
    echo ""
fi

# Wait for Ollama to be ready
echo "  Waiting for Ollama to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ollama is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Ollama did not start in time${NC}"
        exit 1
    fi
    sleep 1
done
echo ""

# 2. Check Ollama models
echo -e "${GREEN}▶ Checking Ollama models...${NC}"
if ! ollama list | grep -q "all-minilm:l6-v2"; then
    echo "  Pulling all-minilm:l6-v2..."
    ollama pull all-minilm:l6-v2 >> "$LOG_DIR/ollama-pull.log" 2>&1
fi

if ! ollama list | grep -q "llama2"; then
    echo "  Pulling llama2..."
    ollama pull llama2 >> "$LOG_DIR/ollama-pull.log" 2>&1
fi
echo -e "${GREEN}✓ Models ready${NC}"
echo ""

# 3. Initialize database (if needed)
echo -e "${GREEN}▶ Checking ScyllaDB schema...${NC}"
if python3 "$PROJECT_DIR/scylladb_setup/create_schema.py" >> "$LOG_DIR/schema-init.log" 2>&1; then
    echo -e "${GREEN}✓ Schema initialized${NC}"
else
    echo -e "${YELLOW}⚠ Schema initialization had warnings (may already exist)${NC}"
fi
echo ""

# 4. Start FastAPI backend
cd "$PROJECT_DIR"
start_service "fastapi" "python3 -B -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000"

# 5. Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Backend did not start in time${NC}"
        echo "Check logs: $LOG_DIR/fastapi.log"
        exit 1
    fi
    sleep 1
done
echo ""

# 6. Start Phoenix frontend
cd "$PROJECT_DIR/frontend"
start_service "phoenix" "mix phx.server"

# 7. Wait for frontend to be ready
echo "Waiting for frontend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:4000 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Frontend is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${YELLOW}⚠ Frontend did not start in time${NC}"
        echo "Check logs: $LOG_DIR/phoenix.log"
        echo "You can still access the backend API"
    fi
    sleep 1
done
echo ""

# Summary
echo "================================================================"
echo -e "${GREEN}✓ All services started successfully!${NC}"
echo "================================================================"
echo ""
echo "Services:"
echo "  • Frontend:    http://localhost:4000"
echo "  • Backend API: http://localhost:8000"
echo "  • API Docs:    http://localhost:8000/docs"
echo "  • Ollama:      http://localhost:11434"
echo ""
echo "Logs directory: $LOG_DIR"
echo "PID files:      $PID_DIR"
echo ""
echo "To view logs:"
echo "  tail -f $LOG_DIR/phoenix.log"
echo "  tail -f $LOG_DIR/fastapi.log"
echo "  tail -f $LOG_DIR/ollama.log"
echo ""
echo "To stop all services:"
echo "  ./stop.sh"
echo ""
