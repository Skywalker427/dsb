from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for given text."""
        pass
    
    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        pass
    
    @abstractmethod
    def get_embedding_dimensions(self) -> int:
        """Get the dimensions of embeddings produced by this provider."""
        pass


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def extract_tags(self, text: str, max_tags: int = 10) -> List[str]:
        """Extract tags/keywords from text."""
        pass
    
    @abstractmethod
    async def extract_topics(
        self, 
        text: str, 
        max_topics: int = 5,
        existing_topics: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Extract topics from text.
        
        Returns list of dicts with keys: label, description, confidence
        """
        pass
    
    @abstractmethod
    async def preprocess_text(self, text: str) -> str:
        """Preprocess text for better embedding quality."""
        pass
    
    @abstractmethod
    async def redact_pii(self, text: str) -> str:
        """Remove or redact PII from text."""
        pass