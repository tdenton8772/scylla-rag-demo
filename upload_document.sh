#!/bin/bash
# Upload a document to the RAG knowledge base
# Usage: ./upload_document.sh <file_path>

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file_path>"
    echo "Example: $0 ~/Downloads/document.pdf"
    exit 1
fi

FILE_PATH="$1"

if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File not found: $FILE_PATH"
    exit 1
fi

echo "Uploading $(basename "$FILE_PATH")..."
echo ""

RESPONSE=$(curl -s -X POST "http://localhost:8000/ingest/upload" \
  -F "file=@$FILE_PATH" \
  -w "\n%{time_total}")

TIME=$(echo "$RESPONSE" | tail -1)
JSON=$(echo "$RESPONSE" | head -n -1)

echo "$JSON" | jq '.'
echo ""
echo "⏱️  Processing time: ${TIME}s"

echo ""
echo "✓ Upload complete!"
