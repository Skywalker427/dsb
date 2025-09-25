from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator

from app.domain.enums import (
    AuthorType,
    Category,
    ClusterKind,
    ClusterStatus,
    DocFormat,
    DocStatus,
    SuggestionStatus,
    TemplateEngine,
)


# Base response envelope
class ApiResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    meta: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    ok: bool = False
    error: Dict[str, Any]


# Suggestion schemas
class ContactInfo(BaseModel):
    email: Optional[str] = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: Optional[str] = Field(None, pattern=r"^\+[1-9]\d{1,14}$")

    @validator("phone", "email", pre=True)
    def at_least_one_contact(cls, v, values):
        if not v and not values.get("email") and not values.get("phone"):
            raise ValueError("Either email or phone must be provided")
        return v


class SuggestionCreate(BaseModel):
    author_type: AuthorType
    category: Category
    title: str = Field(..., max_length=120)
    body: str = Field(..., max_length=10000)
    contact: ContactInfo
    attachments: Optional[List[Dict[str, Any]]] = []


class SuggestionResponse(BaseModel):
    id: UUID
    author_type: AuthorType
    category: Category
    title: str
    body: str
    contact: Optional[Dict[str, Any]]
    attachments: List[Dict[str, Any]]
    tags: List[str]
    language: Optional[str]
    embedding_model: Optional[str]
    status: SuggestionStatus
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime]

    class Config:
        from_attributes = True


# Cluster schemas
class ClusterCreate(BaseModel):
    kind: ClusterKind
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    primary_topic_id: Optional[UUID] = None
    fusion_params: Optional[Dict[str, Any]] = None


class ClusterResponse(BaseModel):
    id: UUID
    kind: ClusterKind
    title: Optional[str]
    description: Optional[str]
    tags: List[str]
    weight: float
    status: ClusterStatus
    primary_topic_id: Optional[UUID]
    fusion_params: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Topic schemas
class TopicCreate(BaseModel):
    label: str = Field(..., max_length=255)
    description: Optional[str] = None


class TopicResponse(BaseModel):
    id: UUID
    label: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Template schemas
class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=120)
    description: Optional[str] = None
    version: str = Field(..., max_length=50)
    kind: str = Field(..., max_length=100)
    engine: TemplateEngine = TemplateEngine.MD_JINJA
    content_markdown: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    kind: Optional[str] = Field(None, max_length=100)
    engine: Optional[TemplateEngine] = None
    content_markdown: Optional[str] = None
    active: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    version: str
    kind: str
    engine: TemplateEngine
    content_markdown: str
    outline: Optional[List[Dict[str, Any]]]
    placeholders: Optional[List[str]]
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Document schemas
class DocumentCreate(BaseModel):
    title: Optional[str] = None
    template_id: UUID
    cluster_ids: Optional[List[UUID]] = []
    topic_ids: Optional[List[UUID]] = []
    auto_render: bool = False
    render_format: Optional[DocFormat] = None


class DocumentGenerateFromCluster(BaseModel):
    cluster_id: UUID
    template_id: UUID
    title: Optional[str] = None


class DocumentGenerateFromTopic(BaseModel):
    topic_id: UUID
    template_id: UUID
    title: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    draft_content: Optional[Dict[str, Any]] = None
    status: Optional[DocStatus] = None
    rendered_format: Optional[DocFormat] = None
    rendered_url: Optional[str] = None


class DocumentResponse(BaseModel):
    id: UUID
    title: Optional[str]
    template_id: UUID
    status: DocStatus
    rendered_format: Optional[DocFormat]
    rendered_url: Optional[str]
    draft_content: Optional[Dict[str, Any]]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_no: int
    diff: Optional[Dict[str, Any]]
    prompt: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Job schemas
class JobResponse(BaseModel):
    id: UUID
    type: str
    status: str
    payload: Optional[Dict[str, Any]]
    attempts: int
    last_error: Optional[str]
    run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Pagination
class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


# Search/filter schemas
class SuggestionFilters(BaseModel):
    author_type: Optional[AuthorType] = None
    category: Optional[Category] = None
    status: Optional[SuggestionStatus] = None
    language: Optional[str] = None
    tag: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class ClusterFilters(BaseModel):
    kind: Optional[ClusterKind] = None
    status: Optional[ClusterStatus] = None
    min_weight: Optional[float] = None
    tag: Optional[str] = None
    topic_id: Optional[UUID] = None


# Processing results
class ProcessingResult(BaseModel):
    suggestion_id: UUID
    cluster_id: Optional[UUID] = None
    similarity: Optional[float] = None
    status: str