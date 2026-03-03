import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.adapters.llm.base import EmbeddingProvider, LLMProvider
from app.core.config import get_settings
from app.core.errors import DependencyError
from app.core.logging import get_structured_logger

logger = get_structured_logger(__name__)
settings = get_settings()


class OpenAIProvider(EmbeddingProvider, LLMProvider):
    """OpenAI provider for embeddings and LLM operations."""
    
    def __init__(self, api_key: str | None = None):
        # Determine provider (openai vs azure) and credentials
        provider = settings.llm_provider or "openai"
        emb_provider = settings.embedding_provider or "openai"
        # Prefer explicit api_key; otherwise choose based on provider
        if api_key:
            self.api_key = api_key
        elif provider == "azure":
            self.api_key = settings.azure_openai_api_key
        else:
            self.api_key = settings.openai_api_key
        if not self.api_key:
            raise DependencyError("OpenAI API key is required", "OpenAI")
        
        # Configure client(s)
        if provider == "azure" or emb_provider == "azure":
            base_url = settings.azure_openai_endpoint
            if not base_url:
                raise DependencyError("Azure OpenAI endpoint is required when azure provider is selected", "AzureOpenAI")

            # Determine API versions with fallbacks
            chat_api_version = settings.azure_openai_chat_api_version or settings.azure_openai_api_version
            emb_api_version = settings.azure_openai_embeddings_api_version or settings.azure_openai_api_version

            # If using Azure for LLM chat
            if provider == "azure":
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=base_url.rstrip("/"),
                    default_query={"api-version": chat_api_version},
                )
            else:
                self.client = AsyncOpenAI(api_key=self.api_key)

            # Optional separate embeddings client if embeddings use Azure but LLM does not
            self.embeddings_client = None
            if emb_provider == "azure":
                self.embeddings_client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=base_url.rstrip("/"),
                    default_query={"api-version": emb_api_version},
                )
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)
            self.embeddings_client = None

        # Models
        self.embedding_model = settings.embedding_model
        self.chat_model = settings.llm_model
        self.embedding_dims = settings.embedding_dims
    
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for given text."""
        try:
            # Preprocess text to remove noise
            clean_text = await self.preprocess_text(text)
            
            client = self.embeddings_client or self.client
            response = await client.embeddings.create(
                model=self.embedding_model,
                input=clean_text,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            logger.info(
                "Generated embedding",
                model=self.embedding_model,
                input_length=len(clean_text),
                embedding_dims=len(embedding)
            )
            
            return embedding
            
        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            raise DependencyError(f"OpenAI embedding failed: {str(e)}", "OpenAI") from e
    
    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        try:
            # Preprocess all texts
            clean_texts = [await self.preprocess_text(text) for text in texts]
            
            client = self.embeddings_client or self.client
            response = await client.embeddings.create(
                model=self.embedding_model,
                input=clean_texts,
                encoding_format="float"
            )
            
            embeddings = [data.embedding for data in response.data]
            logger.info(
                "Generated batch embeddings",
                model=self.embedding_model,
                batch_size=len(texts),
                embedding_dims=len(embeddings[0]) if embeddings else 0
            )
            
            return embeddings
            
        except Exception as e:
            logger.error("Failed to generate batch embeddings", error=str(e))
            raise DependencyError(f"OpenAI batch embedding failed: {str(e)}", "OpenAI") from e
    
    def get_embedding_dimensions(self) -> int:
        """Get the dimensions of embeddings produced by this provider."""
        return self.embedding_dims

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> str:
        """Call chat completions and return the assistant message content."""
        response = await self.client.chat.completions.create(
            model=model or self.chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    async def extract_tags(self, text: str, max_tags: int = 10) -> list[str]:
        """Extract tags/keywords from text using GPT."""
        try:
            system_prompt = f"""
            You are a keyword extraction expert. Extract the most relevant tags/keywords from the given text.
            
            Rules:
            - Return exactly {max_tags} tags maximum
            - Each tag should be 1-3 words
            - Use lowercase
            - No special characters except hyphens
            - Focus on actionable, categorizable concepts
            - Return as JSON array of strings
            """
            
            user_prompt = f"Extract tags from this text:\n\n{text}"
            
            response = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            content = response.choices[0].message.content
            tags = json.loads(content)
            
            # Normalize tags
            normalized_tags = []
            for tag in tags[:max_tags]:
                # Clean and normalize
                clean_tag = re.sub(r'[^a-z0-9\-\s]', '', tag.lower().strip())
                clean_tag = re.sub(r'\s+', '-', clean_tag)
                if clean_tag and len(clean_tag) > 1:
                    normalized_tags.append(clean_tag)
            
            logger.info(
                "Extracted tags using LLM",
                input_length=len(text),
                tags_count=len(normalized_tags),
                tags=normalized_tags
            )
            
            return normalized_tags
            
        except Exception as e:
            logger.error("Failed to extract tags", error=str(e))
            # Fallback to empty list rather than failing
            return []
    
    async def extract_topics(
        self,
        text: str,
        max_topics: int = 5,
        existing_topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract topics from text using GPT."""
        try:
            existing_context = ""
            if existing_topics:
                existing_context = f"\nExisting topics to consider reusing: {', '.join(existing_topics[:20])}"
            
            system_prompt = f"""
            You are a topic extraction expert. Extract the main topics/themes from the given text.
            
            Rules:
            - Return up to {max_topics} topics
            - Each topic should have: label (2-4 words), description (1 sentence), confidence (0.0-1.0)
            - Labels should be general enough to group similar content
            - If existing topics match well, reuse those labels
            - Return as JSON array of objects with keys: label, description, confidence
            {existing_context}
            """
            
            user_prompt = f"Extract topics from this text:\n\n{text}"
            
            response = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=400
            )
            
            content = response.choices[0].message.content
            topics = json.loads(content)
            
            # Validate and clean topics
            cleaned_topics = []
            for topic in topics[:max_topics]:
                if all(key in topic for key in ["label", "description", "confidence"]):
                    # Normalize label
                    label = topic["label"].strip().title()
                    confidence = min(max(float(topic["confidence"]), 0.0), 1.0)
                    
                    cleaned_topics.append({
                        "label": label,
                        "description": topic["description"].strip(),
                        "confidence": confidence
                    })
            
            logger.info(
                "Extracted topics using LLM",
                input_length=len(text),
                topics_count=len(cleaned_topics),
                topics=[t["label"] for t in cleaned_topics]
            )
            
            return cleaned_topics
            
        except Exception as e:
            logger.error("Failed to extract topics", error=str(e))
            # Fallback to empty list rather than failing
            return []
    
    async def preprocess_text(self, text: str) -> str:
        """Preprocess text for better embedding quality."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove email addresses but keep domain concepts
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        
        # Remove phone numbers but keep concept
        text = re.sub(r'[\+]?[1-9]?[0-9]{7,15}', '[PHONE]', text)
        
        # Remove URLs but keep domain concepts
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '[URL]', text)
        
        # Normalize quotes
        text = re.sub(r'[""''`]', '"', text)
        
        return text
    
    async def redact_pii(self, text: str) -> str:
        """Remove or redact PII from text."""
        if not text:
            return ""
        
        # Redact email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]', text)
        
        # Redact phone numbers
        text = re.sub(r'[\+]?[1-9]?[0-9]{7,15}', '[REDACTED_PHONE]', text)
        
        # Redact potential ID numbers (simple heuristic)
        text = re.sub(r'\b\d{6,}\b', '[REDACTED_ID]', text)
        
        # Redact potential credit card numbers
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[REDACTED_CARD]', text)
        
        return text