#!/usr/bin/env python3
"""
ScyllaDB Schema Initialization for RAG Demo
Creates keyspace, tables, and vector index for hybrid memory architecture
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

# Table names
TABLE_DOCUMENTS = os.getenv('SCYLLADB_TABLE_DOCUMENTS', 'documents')
TABLE_SESSIONS = os.getenv('SCYLLADB_TABLE_SESSIONS', 'conversation_sessions')
TABLE_METADATA = os.getenv('SCYLLADB_TABLE_METADATA', 'document_metadata')
TABLE_LONGTERM = os.getenv('SCYLLADB_TABLE_LONGTERM', 'long_term_memory')

# Memory configuration
SHORT_TERM_TTL = int(os.getenv('SHORT_TERM_TTL', '3600'))  # 1 hour
VECTOR_DIMENSION = int(os.getenv('VECTOR_DIMENSION', '384'))


def create_connection():
    """Create connection to ScyllaDB"""
    print(f"Connecting to ScyllaDB at {SCYLLA_HOSTS}...")
    
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
        session = cluster.connect()
        print("✓ Connected to ScyllaDB")
        return cluster, session
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)


def create_keyspace(session):
    """Create keyspace with replication"""
    print(f"\nCreating keyspace '{SCYLLA_KEYSPACE}'...")
    
    # Note: tablets must be disabled for vector search
    create_keyspace_query = f"""
    CREATE KEYSPACE IF NOT EXISTS {SCYLLA_KEYSPACE}
    WITH replication = {{
        'class': 'NetworkTopologyStrategy',
        'replication_factor': 3
    }}
    AND tablets = {{ 'enabled': false }};
    """
    
    try:
        session.execute(create_keyspace_query)
        print(f"✓ Created keyspace: {SCYLLA_KEYSPACE}")
    except Exception as e:
        print(f"✗ Failed to create keyspace: {e}")
        sys.exit(1)
    
    # Use the keyspace
    session.set_keyspace(SCYLLA_KEYSPACE)


def create_documents_table(session):
    """Create documents table for long-term memory with vector embeddings"""
    print(f"\nCreating table '{TABLE_DOCUMENTS}' (long-term memory)...")
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_DOCUMENTS} (
        doc_id uuid,
        chunk_id int,
        content text,
        embedding vector<float, {VECTOR_DIMENSION}>,
        chunk_metadata map<text, text>,
        source_type text,
        created_at timestamp,
        PRIMARY KEY (doc_id, chunk_id)
    ) WITH CLUSTERING ORDER BY (chunk_id ASC)
      AND comment = 'Long-term memory: document chunks and conversation history with embeddings';
    """
    
    try:
        session.execute(create_table_query)
        print(f"✓ Created table: {TABLE_DOCUMENTS}")
    except Exception as e:
        print(f"✗ Failed to create documents table: {e}")
        sys.exit(1)


def create_vector_index(session):
    """Create vector index on documents.embedding for ANN search"""
    print(f"\nCreating vector index on {TABLE_DOCUMENTS}.embedding...")
    
    index_name = f"{TABLE_DOCUMENTS}_embedding_idx"
    
    # Try with SAI first (newer ScyllaDB)
    try:
        create_index_query = f"""
        CREATE CUSTOM INDEX IF NOT EXISTS {index_name}
        ON {TABLE_DOCUMENTS}(embedding)
        USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
        WITH OPTIONS = {{'similarity_function': 'cosine'}};
        """
        session.execute(create_index_query)
        print(f"✓ Created vector index: {index_name} (SAI)")
    except Exception as e:
        print(f"Warning: SAI index failed ({e}), trying legacy vector_index...")
        try:
            create_index_query = f"""
            CREATE CUSTOM INDEX IF NOT EXISTS {index_name}
            ON {TABLE_DOCUMENTS}(embedding)
            USING 'vector_index'
            WITH OPTIONS = {{'similarity_function': 'cosine'}};
            """
            session.execute(create_index_query)
            print(f"✓ Created vector index: {index_name} (legacy)")
        except Exception as e2:
            print(f"✗ Failed to create vector index: {e2}")
            sys.exit(1)


def create_sessions_table(session):
    """Create conversation_sessions table for short-term memory"""
    print(f"\nCreating table '{TABLE_SESSIONS}' (short-term memory)...")
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_SESSIONS} (
        session_id uuid,
        message_timestamp timestamp,
        role text,
        content text,
        context_docs list<uuid>,
        PRIMARY KEY (session_id, message_timestamp)
    ) WITH CLUSTERING ORDER BY (message_timestamp DESC)
      AND default_time_to_live = {SHORT_TERM_TTL}
      AND comment = 'Short-term memory: recent conversation messages with auto-expiration';
    """
    
    try:
        session.execute(create_table_query)
        print(f"✓ Created table: {TABLE_SESSIONS} (TTL: {SHORT_TERM_TTL}s)")
    except Exception as e:
        print(f"✗ Failed to create sessions table: {e}")
        sys.exit(1)


def create_metadata_table(session):
    """Create document_metadata table for tracking uploaded documents"""
    print(f"\nCreating table '{TABLE_METADATA}' (document tracking)...")
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_METADATA} (
        doc_id uuid PRIMARY KEY,
        filename text,
        upload_timestamp timestamp,
        total_chunks int,
        status text,
        file_size bigint,
        mime_type text,
        display_name text
    ) WITH comment = 'Document metadata: tracking uploaded files and chunking status';
    """
    
    try:
        session.execute(create_table_query)
        print(f"✓ Created table: {TABLE_METADATA}")
    except Exception as e:
        print(f"✗ Failed to create metadata table: {e}")
        sys.exit(1)




def create_long_term_memory_table(session):
    """Create long_term_memory table for conversation-derived embeddings"""
    print(f"\nCreating table '{TABLE_LONGTERM}' (long-term conversation memory)...")
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_LONGTERM} (
        session_id uuid,
        chunk_id bigint,
        content text,
        embedding vector<float, {VECTOR_DIMENSION}>,
        metadata map<text, text>,
        created_at timestamp,
        PRIMARY KEY ((session_id), chunk_id)
    ) WITH CLUSTERING ORDER BY (chunk_id ASC)
      AND comment = 'Long-term memory: conversation-derived chunks with embeddings';
    """
    try:
        session.execute(create_table_query)
        print(f"✓ Created table: {TABLE_LONGTERM}")
    except Exception as e:
        print(f"✗ Failed to create long_term_memory table: {e}")
        sys.exit(1)

    # Create vector index for long_term_memory.embedding
    print(f"Creating vector index on {TABLE_LONGTERM}.embedding...")
    index_name = f"{TABLE_LONGTERM}_embedding_idx"
    try:
        create_index_query = f"""
        CREATE CUSTOM INDEX IF NOT EXISTS {index_name}
        ON {TABLE_LONGTERM}(embedding)
        USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
        WITH OPTIONS = {{'similarity_function': 'cosine'}};
        """
        session.execute(create_index_query)
        print(f"✓ Created vector index: {index_name} (SAI)")
    except Exception as e:
        print(f"Warning: SAI index failed ({e}), trying legacy vector_index...")
        try:
            create_index_query = f"""
            CREATE CUSTOM INDEX IF NOT EXISTS {index_name}
            ON {TABLE_LONGTERM}(embedding)
            USING 'vector_index'
            WITH OPTIONS = {{'similarity_function': 'cosine'}};
            """
            session.execute(create_index_query)
            print(f"✓ Created vector index: {index_name} (legacy)")
        except Exception as e2:
            print(f"✗ Failed to create vector index on long_term_memory: {e2}")
            sys.exit(1)


def verify_schema(session):
    """Verify all tables and indexes were created successfully"""
    print("\nVerifying schema...")
    
    tables_query = f"""
    SELECT table_name FROM system_schema.tables
    WHERE keyspace_name = '{SCYLLA_KEYSPACE}';
    """
    
    indexes_query = f"""
    SELECT index_name FROM system_schema.indexes
    WHERE keyspace_name = '{SCYLLA_KEYSPACE}';
    """
    
    try:
        tables = session.execute(tables_query)
        table_names = [row.table_name for row in tables]
        print(f"  Tables: {', '.join(table_names)}")
        
        indexes = session.execute(indexes_query)
        index_names = [row.index_name for row in indexes]
        print(f"  Indexes: {', '.join(index_names)}")
        
        # Check expected tables exist
        expected_tables = {TABLE_DOCUMENTS, TABLE_SESSIONS, TABLE_METADATA, TABLE_LONGTERM}
        if expected_tables.issubset(set(table_names)):
            print("✓ Schema verification passed")
        else:
            missing = expected_tables - set(table_names)
            print(f"✗ Missing tables: {missing}")
            
    except Exception as e:
        print(f"✗ Verification failed: {e}")


def main():
    """Main execution"""
    print("=" * 60)
    print("ScyllaDB RAG Demo - Schema Initialization")
    print("=" * 60)
    
    # Connect
    cluster, session = create_connection()
    
    # Create schema
    create_keyspace(session)
    create_documents_table(session)
    create_vector_index(session)
    create_sessions_table(session)
    create_metadata_table(session)
    create_long_term_memory_table(session)
    
    # Verify
    verify_schema(session)
    
    print("\n" + "=" * 60)
    print("Schema initialization complete!")
    print("=" * 60)
    print(f"\nKeyspace: {SCYLLA_KEYSPACE}")
    print(f"Tables:")
    print(f"  - {TABLE_DOCUMENTS} (long-term memory w/ vector index)")
    print(f"  - {TABLE_SESSIONS} (short-term memory, TTL: {SHORT_TERM_TTL}s)")
    print(f"  - {TABLE_METADATA} (document tracking)")
    print(f"  - {TABLE_LONGTERM} (long-term conversation memory w/ vector index)")
    print(f"\nVector dimensions: {VECTOR_DIMENSION}")
    print(f"Similarity function: COSINE")
    
    # Cleanup
    cluster.shutdown()


if __name__ == "__main__":
    main()
