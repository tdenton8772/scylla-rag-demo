#!/bin/bash
################################################################################
# ScyllaDB RAG Demo - Status Check
# Check status of all services
################################################################################

PROJECT_DIR="/Users/tdenton/Development/scylla-rag-demo"
PID_DIR="$PROJECT_DIR/.pids"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================================"
echo "ScyllaDB RAG Demo - Service Status"
echo "================================================================"
echo ""

# Function to check service status
check_service() {
    local name=$1
    local port=$2
    local pattern=$3
    local health_url=$4
    local pid_file="$PID_DIR/$name.pid"
    
    echo -n "$name: "
    
    local pid=""
    local status="STOPPED"
    
    # 1. Check PID file
    if [ -f "$pid_file" ]; then
        local file_pid=$(cat "$pid_file")
        if ps -p "$file_pid" > /dev/null 2>&1; then
            pid=$file_pid
            status="RUNNING"
        else
            rm -f "$pid_file" 2>/dev/null
        fi
    fi
    
    # 2. Check by port
    if [ -z "$pid" ] && [ -n "$port" ]; then
        local port_pid=$(lsof -ti:$port 2>/dev/null | head -1)
        if [ -n "$port_pid" ]; then
            pid=$port_pid
            status="RUNNING (no PID file)"
        fi
    fi
    
    # 3. Check by process pattern
    if [ -z "$pid" ] && [ -n "$pattern" ]; then
        local pattern_pid=$(pgrep -f "$pattern" 2>/dev/null | head -1)
        if [ -n "$pattern_pid" ]; then
            pid=$pattern_pid
            status="RUNNING (no PID file)"
        fi
    fi
    
    # Display status
    if [ -n "$pid" ]; then
        echo -ne "${GREEN}$status${NC} (PID: $pid)"
        
        # Check health endpoint if provided
        if [ -n "$health_url" ]; then
            if curl -s "$health_url" > /dev/null 2>&1; then
                echo -e " ${GREEN}[HEALTHY]${NC}"
            else
                echo -e " ${YELLOW}[NOT RESPONDING]${NC}"
            fi
        else
            echo ""
        fi
    else
        echo -e "${RED}STOPPED${NC}"
    fi
}

# Check each service
check_service "ollama" "11434" "ollama serve" "http://localhost:11434/api/tags"
check_service "fastapi" "8000" "uvicorn backend.api.main" "http://localhost:8000/health"
check_service "phoenix" "4000" "mix phx.server" "http://localhost:4000"

echo ""
echo "================================================================"

# Check if we can reach the API
echo ""
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend API is accessible${NC}"
    echo "  API: http://localhost:8000"
    echo "  Docs: http://localhost:8000/docs"
else
    echo -e "${RED}✗ Backend API is not accessible${NC}"
    echo "  Run './start.sh' to start services"
fi

echo ""
