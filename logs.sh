#!/bin/bash
################################################################################
# ScyllaDB RAG Demo - Log Viewer
# View logs for all services
################################################################################

PROJECT_DIR="/Users/tdenton/Development/scylla-rag-demo"
LOG_DIR="$PROJECT_DIR/logs"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -d "$LOG_DIR" ]; then
    echo "No logs directory found. Have you started the services?"
    exit 1
fi

# Function to show menu
show_menu() {
    echo "================================================================"
    echo "ScyllaDB RAG Demo - Log Viewer"
    echo "================================================================"
    echo ""
    echo "Available logs:"
    echo "  1) FastAPI Backend"
    echo "  2) Ollama"
    echo "  3) Schema Initialization"
    echo "  4) All logs (combined)"
    echo "  5) List all log files"
    echo "  q) Quit"
    echo ""
}

# Function to tail a log
tail_log() {
    local log_file=$1
    local name=$2
    
    if [ -f "$log_file" ]; then
        echo -e "${GREEN}Tailing $name log (Ctrl+C to stop)${NC}"
        echo "================================================================"
        tail -f "$log_file"
    else
        echo -e "${YELLOW}Log file not found: $log_file${NC}"
    fi
}

# Main menu loop
while true; do
    show_menu
    read -p "Select option: " choice
    
    case $choice in
        1)
            tail_log "$LOG_DIR/fastapi.log" "FastAPI"
            ;;
        2)
            tail_log "$LOG_DIR/ollama.log" "Ollama"
            ;;
        3)
            if [ -f "$LOG_DIR/schema-init.log" ]; then
                cat "$LOG_DIR/schema-init.log"
                echo ""
                read -p "Press Enter to continue..."
            else
                echo "Schema log not found"
            fi
            ;;
        4)
            echo -e "${GREEN}Tailing all logs (Ctrl+C to stop)${NC}"
            echo "================================================================"
            tail -f "$LOG_DIR"/*.log
            ;;
        5)
            echo "Available log files:"
            ls -lh "$LOG_DIR"
            echo ""
            read -p "Press Enter to continue..."
            ;;
        q|Q)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option"
            sleep 1
            ;;
    esac
done
