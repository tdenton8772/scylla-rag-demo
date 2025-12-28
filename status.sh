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
    local pid_file="$PID_DIR/$name.pid"
    
    echo -n "$name: "
    
    # Check PID file
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -ne "${GREEN}RUNNING${NC} (PID: $pid)"
            
            # Check if port is accessible
            if [ -n "$port" ]; then
                if curl -s "$port" > /dev/null 2>&1; then
                    echo -e " ${GREEN}[HEALTHY]${NC}"
                else
                    echo -e " ${YELLOW}[NOT RESPONDING]${NC}"
                fi
            else
                echo ""
            fi
        else
            echo -e "${RED}STOPPED${NC} (stale PID file)"
        fi
    else
        echo -e "${RED}STOPPED${NC}"
    fi
}

# Check each service
check_service "ollama" "http://localhost:11434/api/tags"
check_service "fastapi" "http://localhost:8000/health"

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
