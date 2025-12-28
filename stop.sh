#!/bin/bash
################################################################################
# ScyllaDB RAG Demo - Shutdown Script
# Stops all services gracefully
################################################################################

PROJECT_DIR="/Users/tdenton/Development/scylla-rag-demo"
PID_DIR="$PROJECT_DIR/.pids"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "================================================================"
echo "Stopping ScyllaDB RAG Demo"
echo "================================================================"
echo ""

# Function to stop a service
stop_service() {
    local name=$1
    local pid_file="$PID_DIR/$name.pid"
    
    if [ ! -f "$pid_file" ]; then
        echo -e "${YELLOW}⚠ $name PID file not found${NC}"
        return
    fi
    
    local pid=$(cat "$pid_file")
    
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN}▶ Stopping $name (PID: $pid)...${NC}"
        kill "$pid"
        
        # Wait for process to stop
        for i in {1..10}; do
            if ! ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ $name stopped${NC}"
                rm "$pid_file"
                return
            fi
            sleep 1
        done
        
        # Force kill if still running
        echo -e "${YELLOW}  Force stopping $name...${NC}"
        kill -9 "$pid" 2>/dev/null
        rm "$pid_file"
        echo -e "${GREEN}✓ $name force stopped${NC}"
    else
        echo -e "${YELLOW}⚠ $name is not running (stale PID file)${NC}"
        rm "$pid_file"
    fi
    echo ""
}

# Stop services in reverse order
stop_service "phoenix"
stop_service "fastapi"
stop_service "ollama"

# Clean up any remaining PIDs
if [ -d "$PID_DIR" ]; then
    rm -rf "$PID_DIR"
fi

echo "================================================================"
echo -e "${GREEN}✓ All services stopped${NC}"
echo "================================================================"
echo ""
