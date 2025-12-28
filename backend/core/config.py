"""
Configuration Management
Loads from config.yaml and environment variables
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Path to .env file (project root)
ENV_PATH = Path(__file__).parent.parent.parent / ".env"

# Load environment variables (prefer .env over existing env for reproducibility)
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Path to config file
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"


class Config:
    """Central configuration manager"""
    
    def __init__(self):
        self._config = self._load_config()
        self._env = os.getenv('APP_ENV', 'development')
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not CONFIG_PATH.exists():
            print(f"Warning: Config file not found at {CONFIG_PATH}")
            return {}
        
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    
    # ScyllaDB Configuration
    @property
    def scylla_hosts(self) -> list[str]:
        return os.getenv('SCYLLADB_HOSTS', 'localhost').split(',')
    
    @property
    def scylla_port(self) -> int:
        return int(os.getenv('SCYLLADB_PORT', '9042'))
    
    @property
    def scylla_username(self) -> str:
        return os.getenv('SCYLLADB_USERNAME', 'scylla')
    
    @property
    def scylla_password(self) -> str:
        return os.getenv('SCYLLADB_PASSWORD', '')
    
    @property
    def scylla_keyspace(self) -> str:
        return os.getenv('SCYLLADB_KEYSPACE', 'rag_demo')
    
    # Table Names
    @property
    def table_documents(self) -> str:
        return os.getenv('SCYLLADB_TABLE_DOCUMENTS', 'documents')
    
    @property
    def table_sessions(self) -> str:
        return os.getenv('SCYLLADB_TABLE_SESSIONS', 'conversation_sessions')
    
    @property
    def table_metadata(self) -> str:
        return os.getenv('SCYLLADB_TABLE_METADATA', 'document_metadata')
    
    @property
    def table_long_term_memory(self) -> str:
        return os.getenv('SCYLLADB_TABLE_LONGTERM', 'long_term_memory')
    
    # Memory Configuration
    @property
    def short_term_max_messages(self) -> int:
        return int(os.getenv('SHORT_TERM_MAX_MESSAGES', '5'))
    
    @property
    def short_term_ttl(self) -> int:
        return int(os.getenv('SHORT_TERM_TTL', '3600'))
    
    @property
    def long_term_top_k(self) -> int:
        return int(os.getenv('LONG_TERM_TOP_K', '10'))
    
    @property
    def long_top_k(self) -> int:
        return int(os.getenv('LONG_TOP_K', '4'))
    
    @property
    def doc_top_k(self) -> int:
        return int(os.getenv('DOC_TOP_K', '6'))
    
    @property
    def doc_ann_multiplier(self) -> int:
        # How many ANN candidates to fetch per document result (1 = no expansion)
        return int(os.getenv('DOC_ANN_MULTIPLIER', '1'))
    
    @property
    def long_ann_multiplier(self) -> int:
        # How many ANN candidates to fetch per long-term result (1 = no expansion)
        return int(os.getenv('LONG_ANN_MULTIPLIER', '1'))
    
    @property
    def long_term_similarity_threshold(self) -> float:
        return float(os.getenv('LONG_TERM_SIMILARITY_THRESHOLD', '0.3'))
    
    @property
    def doc_similarity_threshold(self) -> float:
        return float(os.getenv('DOC_SIMILARITY_THRESHOLD', '0.0'))
    
    @property
    def doc_surrounding_chunks(self) -> int:
        # Number of chunks before and after a matching chunk to include for context (0 = disabled)
        return int(os.getenv('DOC_SURROUNDING_CHUNKS', '2'))
    
    # Embeddings Configuration
    @property
    def embeddings_provider(self) -> str:
        return os.getenv('EMBEDDINGS_PROVIDER', 'ollama')
    
    @property
    def embeddings_model(self) -> str:
        return os.getenv('EMBEDDINGS_MODEL', 'all-minilm:l6-v2')
    
    @property
    def embeddings_dimension(self) -> int:
        return int(os.getenv('VECTOR_DIMENSION', '384'))
    
    @property
    def ollama_base_url(self) -> str:
        return os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    
    @property
    def openai_base_url(self) -> str:
        # Supports OpenAI-compatible providers like x.ai (Grok)
        return os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    
    @property
    def openai_api_key(self) -> str:
        return os.getenv('OPENAI_API_KEY', '')
    
    # LLM Configuration
    @property
    def llm_provider(self) -> str:
        return os.getenv('LLM_PROVIDER', 'ollama')
    
    @property
    def llm_model(self) -> str:
        provider = os.getenv('LLM_PROVIDER', 'ollama').lower()
        if provider == 'openai':
            return os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        return os.getenv('OLLAMA_MODEL', 'llama2')
    
    @property
    def llm_temperature(self) -> float:
        cfg = self._config.get('llm', {})
        return cfg.get('temperature', 0.7)
    
    @property
    def llm_max_tokens(self) -> int:
        cfg = self._config.get('llm', {})
        return cfg.get('max_tokens', 1000)
    
    # Chunking Configuration
    @property
    def chunk_strategy(self) -> str:
        return os.getenv('CHUNK_STRATEGY', 'sentence')
    
    @property
    def chunk_size(self) -> int:
        return int(os.getenv('CHUNK_SIZE', '512'))
    
    @property
    def chunk_overlap(self) -> int:
        return int(os.getenv('CHUNK_OVERLAP', '50'))
    
    # API Configuration
    @property
    def api_host(self) -> str:
        cfg = self._config.get('api', {})
        return cfg.get('host', '0.0.0.0')
    
    @property
    def api_port(self) -> int:
        cfg = self._config.get('api', {})
        return cfg.get('port', 8000)
    
    # Logging
    @property
    def log_level(self) -> str:
        return os.getenv('LOG_LEVEL', 'INFO')
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


# Global config instance
config = Config()
