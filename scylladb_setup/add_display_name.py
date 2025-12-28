#!/usr/bin/env python3
"""
Migration: Add display_name column to document_metadata table
This allows storing custom names for sessions/documents
"""

import os
import sys
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
SCYLLA_HOSTS = os.getenv('SCYLLADB_HOSTS', 'localhost').split(',')
SCYLLA_PORT = int(os.getenv('SCYLLADB_PORT', '9042'))
SCYLLA_USERNAME = os.getenv('SCYLLADB_USERNAME', 'scylla')
SCYLLA_PASSWORD = os.getenv('SCYLLADB_PASSWORD', '')
SCYLLA_KEYSPACE = os.getenv('SCYLLADB_KEYSPACE', 'rag_demo')
TABLE_METADATA = os.getenv('SCYLLADB_TABLE_METADATA', 'document_metadata')

def main():
    print("=" * 60)
    print("Migration: Add display_name to document_metadata")
    print("=" * 60)
    
    # Connect
    print(f"\nConnecting to ScyllaDB at {SCYLLA_HOSTS}...")
    auth_provider = PlainTextAuthProvider(
        username=SCYLLA_USERNAME,
        password=SCYLLA_PASSWORD
    )
    
    cluster = Cluster(
        SCYLLA_HOSTS,
        port=SCYLLA_PORT,
        auth_provider=auth_provider,
        protocol_version=4
    )
    
    try:
        session = cluster.connect(SCYLLA_KEYSPACE)
        print("✓ Connected")
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)
    
    # Add display_name column
    print(f"\nAdding display_name column to {TABLE_METADATA}...")
    alter_query = f"""
    ALTER TABLE {TABLE_METADATA}
    ADD display_name text;
    """
    
    try:
        session.execute(alter_query)
        print("✓ Column added successfully")
    except Exception as e:
        if "conflicts with" in str(e) or "already exists" in str(e):
            print("✓ Column already exists")
        else:
            print(f"✗ Failed to add column: {e}")
            sys.exit(1)
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    
    cluster.shutdown()

if __name__ == "__main__":
    main()
