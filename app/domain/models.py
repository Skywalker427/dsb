from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.adapters.repos.base import Base
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


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    author_type = Column(Enum(AuthorType, name="author_type"), nullable=False)
    category = Column(Enum(Category, name="category"), nullable=False)
    title = Column(String(120), nullable=False)
    body = Column(Text, nullable=False)
    contact = Column(JSONB, nullable=True)
    attachments = Column(ARRAY(JSONB), default=[])
    tags = Column(ARRAY(String), default=[])
    language = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    status = Column(
        Enum(SuggestionStatus, name="suggestion_status"),
        nullable=False,
        default=SuggestionStatus.NEW,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )
    archived_at = Column(DateTime(timezone=True), nullable=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, nullable=False)


class SuggestionTag(Base):
    __tablename__ = "suggestion_tags"

    suggestion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suggestions.id"), primary_key=True
    )
    tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    label = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )


class TopicAlias(Base):
    __tablename__ = "topic_aliases"

    topic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id"), primary_key=True
    )
    alias = Column(String, primary_key=True)


class DocumentTopic(Base):
    __tablename__ = "document_topics"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id"), primary_key=True
    )
    confidence = Column(Float, nullable=False, default=0.5)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    kind = Column(Enum(ClusterKind, name="cluster_kind"), nullable=False)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(ARRAY(String), default=[])
    weight = Column(Float, nullable=False, default=0.0)
    status = Column(
        Enum(ClusterStatus, name="cluster_status"), default=ClusterStatus.NEW
    )
    primary_topic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id"), nullable=True
    )
    fusion_params = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clusters.id"), primary_key=True
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    suggestion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suggestions.id"), nullable=True
    )
    similarity = Column(Float, nullable=True)
    is_manual = Column(Boolean, default=False)
    added_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    engine = Column(
        Enum(TemplateEngine, name="template_engine"),
        nullable=False,
        default=TemplateEngine.MD_JINJA,
    )
    content_markdown = Column(Text, nullable=False)
    outline = Column(JSONB, nullable=True)
    placeholders = Column(JSONB, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(Text, nullable=True)
    template_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id"), nullable=False
    )
    status = Column(
        Enum(DocStatus, name="doc_status"), default=DocStatus.DRAFT, nullable=False
    )
    rendered_format = Column(Enum(DocFormat, name="doc_format"), nullable=True)
    rendered_url = Column(Text, nullable=True)
    draft_content = Column(JSONB, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), index=True
    )
    version_no = Column(Integer, nullable=False)
    diff = Column(JSONB, nullable=True)
    prompt = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class DocumentCluster(Base):
    __tablename__ = "document_clusters"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clusters.id"), primary_key=True
    )
    contribution_weight = Column(Float, nullable=False, default=1.0)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    payload = Column(JSONB, nullable=True)
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )