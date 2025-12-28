"""
Embeddings Service
Generates vector embeddings using Ollama
"""

import requests
import logging
from typing import List
import numpy as np

from .config import config

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """Service for generating embeddings via Ollama"""
    
    def __init__(self):
        self.base_url = config.ollama_base_url
        self.model = config.embeddings_model
        self.dimension = config.embeddings_dimension
        
        logger.info(f"Embeddings: {self.model} ({self.dimension} dims) at {self.base_url}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return [0.0] * self.dimension
        
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get('embedding', [])
            
            if len(embedding) != self.dimension:
                logger.error(
                    f"Embedding dimension mismatch: expected {self.dimension}, "
                    f"got {len(embedding)}"
                )
                return [0.0] * self.dimension
            
            return embedding
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding: {e}")
            logger.error(f"Text (first 100 chars): {text[:100]}")
            raise
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to embed text in batch: {e}")
                # Return zero vector on failure
                embeddings.append([0.0] * self.dimension)
        
        return embeddings
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score between -1 and 1
        """
        if len(vec1) != len(vec2):
            raise ValueError("Vectors must have same dimensions")
        
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        
        return float(dot_product / (norm_v1 * norm_v2))
    
    def health_check(self) -> bool:
        """
        Check if Ollama service is available
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            # Check if our model is available
            data = response.json()
            models = data.get('models', [])
            model_names = [m.get('name', '') for m in models]
            
            if self.model in model_names:
                logger.info(f"✓ Ollama health check passed: {self.model} available")
                return True
            else:
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                return False
                
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False


# Global embeddings service instance
_embeddings_service: EmbeddingsService = None


def get_embeddings_service() -> EmbeddingsService:
    """Get or create the global embeddings service"""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = EmbeddingsService()
    return _embeddings_service
