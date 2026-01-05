#!/usr/bin/env python3
"""
Flush all data from ScyllaDB RAG Demo tables
Truncates all tables to remove data while keeping schema intact
"""

import sys
from backend.core.scylla import get_scylla_client
from backend.core.config import config


def flush_all_tables():
    """Truncate all tables used by the RAG demo"""
    client = get_scylla_client()
    
    tables = [
        (config.table_documents, "Documents (uploaded files)"),
        (config.table_long_term_memory, "Long-term memory (conversation embeddings)"),
        (config.table_sessions, "Short-term memory (recent messages)"),
        (config.table_metadata, "Session metadata (display names)")
    ]
    
    print("=" * 70)
    print("ScyllaDB RAG Demo - Flush All Tables")
    print("=" * 70)
    print()
    print("This will DELETE ALL DATA from the following tables:")
    print()
    
    for table_name, description in tables:
        print(f"  • {table_name}: {description}")
    
    print()
    print("WARNING: This operation cannot be undone!")
    print()
    
    # Prompt for confirmation
    response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("\nOperation cancelled.")
        sys.exit(0)
    
    print()
    print("Flushing tables...")
    print()
    
    # Truncate each table
    for table_name, description in tables:
        try:
            print(f"  Truncating {table_name}...", end=" ")
            client.execute(f"TRUNCATE {table_name}")
            print("✓ Done")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print()
    print("=" * 70)
    print("All tables flushed successfully!")
    print("=" * 70)
    print()
    print("You can now:")
    print("  1. Re-upload documents via the frontend (http://localhost:4000)")
    print("  2. Or use the API: POST http://localhost:8000/ingest/upload")
    print()


if __name__ == "__main__":
    try:
        flush_all_tables()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
