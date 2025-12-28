"""
ScyllaDB Connection Manager
Handles connection pooling and session management
"""

from cassandra.cluster import Cluster, Session, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import dict_factory
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra import ConsistencyLevel
from typing import Optional
import logging

from .config import config

logger = logging.getLogger(__name__)


class ScyllaDBClient:
    """ScyllaDB connection manager with singleton pattern"""
    
    _instance: Optional['ScyllaDBClient'] = None
    _cluster: Optional[Cluster] = None
    _session: Optional[Session] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._cluster is None:
            self._connect()
    
    def _connect(self):
        """Establish connection to ScyllaDB"""
        logger.info(f"Connecting to ScyllaDB at {config.scylla_hosts}")
        
        auth_provider = PlainTextAuthProvider(
            username=config.scylla_username,
            password=config.scylla_password
        )
        
        short_profile = ExecutionProfile(
            load_balancing_policy=DCAwareRoundRobinPolicy(),
            consistency_level=ConsistencyLevel.LOCAL_ONE,
            request_timeout=0.5,
            row_factory=dict_factory,
        )
        default_profile = ExecutionProfile(
            load_balancing_policy=DCAwareRoundRobinPolicy(),
            consistency_level=ConsistencyLevel.LOCAL_QUORUM,
            request_timeout=5.0,
            row_factory=dict_factory,
        )

        self._cluster = Cluster(
            config.scylla_hosts,
            port=config.scylla_port,
            auth_provider=auth_provider,
            protocol_version=4,
            # Connection pooling
            executor_threads=4,
            max_schema_agreement_wait=10,
            execution_profiles={
                EXEC_PROFILE_DEFAULT: default_profile,
                "short": short_profile,
            },
        )
        
        try:
            self._session = self._cluster.connect(config.scylla_keyspace)
            logger.info(f"✓ Connected to keyspace: {config.scylla_keyspace}")
        except Exception as e:
            logger.error(f"Failed to connect to ScyllaDB: {e}")
            raise
    
    @property
    def session(self) -> Session:
        """Get the active session"""
        if self._session is None:
            self._connect()
        return self._session
    def prepare(self, query: str):
        """Prepare a CQL statement and return the PreparedStatement."""
        try:
            return self.session.prepare(query)
        except Exception as e:
            logger.error(f"Prepare failed: {e}")
            logger.error(f"Query: {query}")
            raise
    
    def close(self):
        """Close connection and cleanup"""
        if self._cluster:
            logger.info("Closing ScyllaDB connection")
            self._cluster.shutdown()
            self._cluster = None
            self._session = None
    
    def execute(self, query: str, parameters: tuple = None, profile: str = None):
        """Execute a CQL query, optionally using a named execution profile."""
        try:
            # Only pass execution_profile if profile is specified (not None)
            if profile is not None:
                if parameters is not None:
                    return self.session.execute(query, parameters=parameters, execution_profile=profile)
                return self.session.execute(query, execution_profile=profile)
            else:
                # Use default profile when None
                if parameters is not None:
                    return self.session.execute(query, parameters=parameters)
                return self.session.execute(query)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise
    
    def execute_async(self, query: str, parameters: tuple = None, profile: str = None):
        """Execute a CQL query asynchronously"""
        try:
            if parameters is not None:
                return self.session.execute_async(query, parameters=parameters, execution_profile=profile)
            return self.session.execute_async(query, execution_profile=profile)
        except Exception as e:
            logger.error(f"Async query execution failed: {e}")
            raise


# Global client instance
_client: Optional[ScyllaDBClient] = None


def get_scylla_client() -> ScyllaDBClient:
    """Get or create the global ScyllaDB client"""
    global _client
    if _client is None:
        _client = ScyllaDBClient()
    return _client


def get_session() -> Session:
    """Get the active ScyllaDB session"""
    return get_scylla_client().session
