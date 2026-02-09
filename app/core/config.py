import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # External Services (Required)
    database_url: str
    redis_url: str | None = None
    openai_api_key: str | None = None
    # Tolerate optional OpenAI SDK envs if present
    openai_api_type: str | None = None
    openai_api_base: str | None = None
    # Azure OpenAI (Optional)
    azure_openai_enabled: bool = False
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None  # e.g., https://<resource>.openai.azure.com
    # Default API version (used if specific ones below are not set)
    azure_openai_api_version: str = "2024-10-21"
    # Specific API versions for services
    azure_openai_chat_api_version: str | None = None
    azure_openai_embeddings_api_version: str | None = None
    # Optional APIM path prefixes (e.g., 'za') to prepend before /deployments
    azure_openai_apim_chat_prefix: str | None = None
    azure_openai_apim_embeddings_prefix: str | None = None

    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    cache_enabled: bool = False

    # Embedding Configuration
    embedding_provider: str = "openai"  # options: openai, azure, local
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    local_embedding_model_path: str | None = None

    # LLM (chat/completions) Configuration
    llm_provider: str = "openai"  # options: openai, azure, local
    llm_model: str = "gpt-3.5-turbo"  # for OpenAI; for Azure this is the deployment name

    # Vector Index
    vector_index: str = "hnsw"
    hnsw_m: int = 16
    hnsw_ef_construction: int = 128
    hnsw_ef_search: int = 64

    # Clustering
    clustering_enabled_embedding: bool = True
    clustering_enabled_tag: bool = True
    clustering_enabled_topic: bool = True
    clustering_enabled_fusion: bool = True
    assign_threshold: float = 0.75
    tag_min_docs: int = 5
    topic_min_docs: int = 3
    topic_reuse_threshold: float = 0.82
    fusion_weights: str = '{"emb":0.6,"tag":0.2,"topic":0.2}'

    # Document Processing
    topic_max_per_doc: int = 5
    tag_extractor: str = "llm+yake"
    tag_normalize: bool = True
    doc_engine: str = "MD_JINJA"
    storage_mode: str = "local"
    local_storage_path: str = "./generated_docs"
    template_input_max_bytes: int = 1048576
    template_allowed_mimes: str = "text/markdown,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    markdown_engine: str = "markdown-it-py"
    pandoc_enabled: bool = False

    # API Settings
    allow_public_post: bool = True
    allow_anonymous_post: bool = False
    pii_redaction: bool = True
    rate_limit_public_post: int = 60
    max_body_chars: int = 10000

    # Workers
    uvicorn_workers: int = 2
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 9000

    # Security (optional)
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # Observability
    otel_exporter_otlp_endpoint: str | None = None

    # Computed properties
    @property
    def fusion_weights_dict(self) -> dict[str, float]:
        try:
            return json.loads(self.fusion_weights)
        except (json.JSONDecodeError, TypeError):
            return {"emb": 0.6, "tag": 0.2, "topic": 0.2}

    @property
    def template_allowed_mimes_list(self) -> list[str]:
        return [mime.strip() for mime in self.template_allowed_mimes.split(",")]

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, v: str) -> str:
        allowed = ["openai", "azure", "local"]
        if v not in allowed:
            raise ValueError(f"embedding_provider must be one of {allowed}")
        return v

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        allowed = ["openai", "azure", "local"]
        if v not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}")
        return v

    @field_validator("vector_index")
    @classmethod
    def validate_vector_index(cls, v: str) -> str:
        allowed = ["hnsw", "ivfflat"]
        if v not in allowed:
            raise ValueError(f"vector_index must be one of {allowed}")
        return v

    @field_validator("tag_extractor")
    @classmethod
    def validate_tag_extractor(cls, v: str) -> str:
        allowed = ["llm", "yake", "llm+yake"]
        if v not in allowed:
            raise ValueError(f"tag_extractor must be one of {allowed}")
        return v

    @field_validator("storage_mode")
    @classmethod
    def validate_storage_mode(cls, v: str) -> str:
        allowed = ["s3", "minio", "local"]
        if v not in allowed:
            raise ValueError(f"storage_mode must be one of {allowed}")
        return v

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
