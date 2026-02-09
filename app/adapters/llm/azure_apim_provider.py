import json
import re
from typing import Any

import httpx

from app.adapters.llm.base import EmbeddingProvider, LLMProvider
from app.core.config import get_settings
from app.core.errors import DependencyError
from app.core.logging import get_structured_logger

logger = get_structured_logger(__name__)
settings = get_settings()


class AzureAPIMProvider(EmbeddingProvider, LLMProvider):
    """Azure API Management provider for embeddings and chat completions.

    Uses APIM proxy endpoints and Ocp-Apim-Subscription-Key header.
    """

    def __init__(self) -> None:
        if not settings.azure_openai_endpoint:
            raise DependencyError("AZURE_OPENAI_ENDPOINT is required for Azure APIM", "AzureAPIM")
        if not settings.azure_openai_api_key:
            raise DependencyError("AZURE_OPENAI_API_KEY is required for Azure APIM", "AzureAPIM")

        self.base_url = settings.azure_openai_endpoint.rstrip("/")
        self.subscription_key = settings.azure_openai_api_key
        self.embedding_model = settings.embedding_model
        self.chat_model = settings.llm_model
        self.embedding_dims = settings.embedding_dims
        self.chat_prefix = (settings.azure_openai_apim_chat_prefix or "").strip("/")
        self.emb_prefix = (settings.azure_openai_apim_embeddings_prefix or "").strip("/")

        # API versions (with fallbacks)
        self.chat_api_version = settings.azure_openai_chat_api_version or settings.azure_openai_api_version
        self.emb_api_version = settings.azure_openai_embeddings_api_version or settings.azure_openai_api_version

        self._client = httpx.AsyncClient(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.subscription_key,
        }

    async def generate_embedding(self, text: str) -> list[float]:
        try:
            clean_text = await self.preprocess_text(text)
            mid = f"/{self.emb_prefix}" if self.emb_prefix else ""
            url = f"{self.base_url}{mid}/deployments/{self.embedding_model}/embeddings"
            params = {"api-version": self.emb_api_version}
            # Some APIM setups require model field; include deployment name as model
            data = {"input": clean_text, "model": self.embedding_model}

            resp = await self._client.post(url, headers=self._headers(), params=params, json=data)
            resp.raise_for_status()
            payload = resp.json()
            embedding = payload["data"][0]["embedding"]

            logger.info("Generated embedding via APIM", model=self.embedding_model, dims=len(embedding))
            return embedding
        except Exception as e:
            logger.error("APIM embedding failed", error=str(e))
            raise DependencyError(f"Azure APIM embedding failed: {str(e)}", "AzureAPIM") from e

    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            clean_texts = [await self.preprocess_text(t) for t in texts]
            mid = f"/{self.emb_prefix}" if self.emb_prefix else ""
            url = f"{self.base_url}{mid}/deployments/{self.embedding_model}/embeddings"
            params = {"api-version": self.emb_api_version}
            data = {"input": clean_texts, "model": self.embedding_model}

            resp = await self._client.post(url, headers=self._headers(), params=params, json=data)
            resp.raise_for_status()
            payload = resp.json()
            embeddings = [row["embedding"] for row in payload["data"]]

            logger.info("Generated batch embeddings via APIM", model=self.embedding_model, batch=len(texts))
            return embeddings
        except Exception as e:
            logger.error("APIM batch embedding failed", error=str(e))
            raise DependencyError(f"Azure APIM batch embedding failed: {str(e)}", "AzureAPIM") from e

    def get_embedding_dimensions(self) -> int:
        return self.embedding_dims

    async def extract_tags(self, text: str, max_tags: int = 10) -> list[str]:
        try:
            system_prompt = (
                f"You are a keyword extraction expert. Extract up to {max_tags} concise tags. "
                "Return a JSON array of strings, lowercase, 1-3 words, hyphens allowed."
            )
            user_prompt = f"Extract tags from this text:\n\n{text}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            mid = f"/{self.chat_prefix}" if self.chat_prefix else ""
            url = f"{self.base_url}{mid}/deployments/{self.chat_model}/chat/completions"
            params = {"api-version": self.chat_api_version}
            data = {"model": self.chat_model, "messages": messages, "temperature": 0.3, "max_tokens": 200}

            resp = await self._client.post(url, headers=self._headers(), params=params, json=data)
            resp.raise_for_status()
            payload = resp.json()
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            try:
                tags = json.loads(content)
            except Exception:
                # Fallback: naive keyword extraction from content
                words = re.findall(r"[a-zA-Z0-9\-]+", content.lower())
                # De-dup while preserving order
                seen = set()
                tags = []
                for w in words:
                    if w not in seen and len(w) > 2:
                        seen.add(w)
                        tags.append(w)

            normalized = []
            for tag in tags[:max_tags]:
                clean = re.sub(r"[^a-z0-9\-\s]", "", tag.lower().strip())
                clean = re.sub(r"\s+", "-", clean)
                if clean and len(clean) > 1:
                    normalized.append(clean)

            logger.info("APIM tags extracted", count=len(normalized), tags=normalized)
            return normalized
        except Exception as e:
            logger.error("APIM chat extract_tags failed", error=str(e))
            return []

    async def extract_topics(
        self,
        text: str,
        max_topics: int = 5,
        existing_topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            existing_context = ""
            if existing_topics:
                existing_context = f"\nExisting topics to consider reusing: {', '.join(existing_topics[:20])}"

            system_prompt = (
                f"You are a topic extraction expert. Return up to {max_topics} topics as JSON array of "
                "{label, description, confidence}. Labels are 2-4 words, confidence 0.0-1.0." + existing_context
            )
            user_prompt = f"Extract topics from this text:\n\n{text}"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            mid = f"/{self.chat_prefix}" if self.chat_prefix else ""
            url = f"{self.base_url}{mid}/deployments/{self.chat_model}/chat/completions"
            params = {"api-version": self.chat_api_version}
            data = {"model": self.chat_model, "messages": messages, "temperature": 0.3, "max_tokens": 400}

            resp = await self._client.post(url, headers=self._headers(), params=params, json=data)
            resp.raise_for_status()
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            
            # Try to parse JSON, fallback to extracting from markdown code blocks
            try:
                topics = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
                if json_match:
                    topics = json.loads(json_match.group(1))
                else:
                    logger.warning("Failed to parse topics JSON", content=content[:200])
                    return []

            cleaned = []
            for topic in topics[:max_topics]:
                if isinstance(topic, dict) and all(k in topic for k in ("label", "description", "confidence")):
                    label = topic["label"].strip().title()
                    conf = min(max(float(topic["confidence"]), 0.0), 1.0)
                    cleaned.append({"label": label, "description": topic["description"].strip(), "confidence": conf})

            logger.info("APIM topics extracted", count=len(cleaned), topics=[t["label"] for t in cleaned])
            return cleaned
        except Exception as e:
            logger.error("APIM extract_topics failed", error=str(e), error_type=type(e).__name__)
            return []

    async def preprocess_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text.strip())
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)
        text = re.sub(r"[\+]?[1-9]?[0-9]{7,15}", "[PHONE]", text)
        text = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "[URL]", text)
        text = re.sub(r"[""'`]", '"', text)
        return text

    async def redact_pii(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]", text)
        text = re.sub(r"[\+]?[1-9]?[0-9]{7,15}", "[REDACTED_PHONE]", text)
        text = re.sub(r"\b\d{6,}\b", "[REDACTED_ID]", text)
        text = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED_CARD]", text)
        return text
