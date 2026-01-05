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

# Function to stop a service by PID file
stop_service() {
    local name=$1
    local pid_file="$PID_DIR/$name.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}▶ Stopping $name (PID: $pid)...${NC}"
            kill "$pid" 2>/dev/null
            
            # Wait for process to stop
            for i in {1..10}; do
                if ! ps -p "$pid" > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ $name stopped${NC}"
                    rm "$pid_file"
                    return 0
                fi
                sleep 1
            done
            
            # Force kill if still running
            echo -e "${YELLOW}  Force stopping $name...${NC}"
            kill -9 "$pid" 2>/dev/null
            rm "$pid_file"
            echo -e "${GREEN}✓ $name force stopped${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠ $name PID file exists but process not running (stale PID)${NC}"
            rm "$pid_file"
        fi
    fi
    return 1
}

# Function to kill processes by port
kill_by_port() {
    local port=$1
    local name=$2
    
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${GREEN}▶ Stopping $name on port $port...${NC}"
        echo "$pids" | while read pid; do
            echo "  Killing PID: $pid"
            kill "$pid" 2>/dev/null
        done
        sleep 2
        
        # Force kill if still running
        pids=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}  Force stopping...${NC}"
            echo "$pids" | while read pid; do
                kill -9 "$pid" 2>/dev/null
            done
        fi
        echo -e "${GREEN}✓ Port $port cleared${NC}"
        echo ""
    fi
}

# Function to kill processes by pattern
kill_by_pattern() {
    local pattern=$1
    local name=$2
    
    local pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${GREEN}▶ Stopping $name (pattern: $pattern)...${NC}"
        echo "$pids" | while read pid; do
            echo "  Killing PID: $pid"
            kill "$pid" 2>/dev/null
        done
        sleep 2
        
        # Force kill if still running
        pids=$(pgrep -f "$pattern" 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}  Force stopping...${NC}"
            echo "$pids" | while read pid; do
                kill -9 "$pid" 2>/dev/null
            done
        fi
        echo -e "${GREEN}✓ $name stopped${NC}"
        echo ""
    fi
}

# Stop services in reverse order
echo "Stopping Phoenix frontend..."
stop_service "phoenix" || kill_by_port 4000 "Phoenix" || kill_by_pattern "mix phx.server" "Phoenix"

echo "Stopping FastAPI backend..."
stop_service "fastapi" || kill_by_port 8000 "FastAPI" || kill_by_pattern "uvicorn backend.api.main" "FastAPI"

echo "Stopping Ollama..."
stop_service "ollama" || kill_by_port 11434 "Ollama" || kill_by_pattern "ollama serve" "Ollama"

# Clean up any remaining PIDs
if [ -d "$PID_DIR" ]; then
    rm -rf "$PID_DIR"
fi

echo "================================================================"
echo -e "${GREEN}✓ All services stopped${NC}"
echo "================================================================"
echo ""
