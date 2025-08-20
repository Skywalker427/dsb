from enum import Enum


class AuthorType(str, Enum):
    STAFF = "STAFF"
    CUSTOMER = "CUSTOMER"


class Category(str, Enum):
    UX = "UX"
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"
    OPERATIONAL = "OPERATIONAL"
    OTHER = "OTHER"


class SuggestionStatus(str, Enum):
    NEW = "NEW"
    PROCESSED = "PROCESSED"
    ARCHIVED = "ARCHIVED"


class ClusterKind(str, Enum):
    EMBEDDING = "EMBEDDING"
    TAG = "TAG"
    TOPIC = "TOPIC"
    FUSION = "FUSION"


class ClusterStatus(str, Enum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class DocStatus(str, Enum):
    DRAFT = "DRAFT"
    RENDERING = "RENDERING"
    READY = "READY"
    FAILED = "FAILED"


class DocFormat(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"


class TemplateEngine(str, Enum):
    MD_JINJA = "MD_JINJA"