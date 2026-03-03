from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.documents_repo import DocumentRepository
from app.adapters.repos.jobs_repo import JobRepository
from app.services.document_generator import get_document_generator
from app.services.document_exporter import document_exporter
from app.core.errors import NotFoundError, ValidationError
from app.domain.schemas import (
    ApiResponse,
    DocumentCreate,
    DocumentGenerateFromCluster,
    DocumentGenerateFromTopic,
    DocumentUpdate,
    DocumentResponse,
    DocumentVersionResponse,
    PaginationMeta,
    JobResponse,
)
from app.domain.enums import DocStatus, DocFormat
from app.core.database import get_db

router = APIRouter()


@router.post("/generate/cluster", response_model=ApiResponse, status_code=202)
async def generate_document_from_cluster(
    request_data: DocumentGenerateFromCluster,
    db: AsyncSession = Depends(get_db),
):
    """Generate a document from cluster suggestions using background processing."""
    docs_repo = DocumentRepository(db)
    jobs_repo = JobRepository(db)
    
    try:
        # Generate job payload for background processing
        doc_generator = get_document_generator(db)
        job_payload = await doc_generator.generate_document_from_cluster(
            cluster_id=request_data.cluster_id,
            template_id=request_data.template_id,
            document_title=request_data.title,
            # TODO: Get created_by from authentication context
            created_by=None,
        )
        
        # Create background job
        job = await jobs_repo.create(
            job_type="GENERATE_DOCUMENT",
            payload=job_payload,
        )
        
        return ApiResponse(
            ok=True,
            data={
                "job_id": job.id,
                "status": "queued",
                "message": f"Document generation started for cluster {request_data.cluster_id}",
                "expected_suggestions": job_payload["total_suggestions"],
            },
        )
        
    except Exception as e:
        raise ValidationError(f"Failed to start document generation: {str(e)}")


@router.post("/generate/topic", response_model=ApiResponse, status_code=202)
async def generate_document_from_topic(
    request_data: DocumentGenerateFromTopic,
    db: AsyncSession = Depends(get_db),
):
    """Generate a document from topic suggestions using background processing."""
    docs_repo = DocumentRepository(db)
    jobs_repo = JobRepository(db)
    
    try:
        # Generate job payload for background processing
        doc_generator = get_document_generator(db)
        job_payload = await doc_generator.generate_document_from_topic(
            topic_id=request_data.topic_id,
            template_id=request_data.template_id,
            document_title=request_data.title,
            # TODO: Get created_by from authentication context
            created_by=None,
        )
        
        # Create background job
        job = await jobs_repo.create(
            job_type="GENERATE_DOCUMENT",
            payload=job_payload,
        )
        
        return ApiResponse(
            ok=True,
            data={
                "job_id": job.id,
                "status": "queued",
                "message": f"Document generation started for topic {request_data.topic_id}",
                "expected_suggestions": job_payload["total_suggestions"],
            },
        )
        
    except Exception as e:
        raise ValidationError(f"Failed to start document generation: {str(e)}")


@router.get("", response_model=ApiResponse)
async def get_documents(
    status: Optional[DocStatus] = Query(None, description="Filter by document status"),
    template_id: Optional[UUID] = Query(None, description="Filter by template ID"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Get all documents with optional filters and pagination."""
    docs_repo = DocumentRepository(db)
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get documents and total count
    documents = await docs_repo.get_all(
        status=status,
        template_id=template_id,
        search=search,
        offset=offset,
        limit=page_size,
    )
    total = await docs_repo.count(
        status=status,
        template_id=template_id,
        search=search,
    )
    
    # Convert to response models
    document_responses = [DocumentResponse.model_validate(d) for d in documents]
    
    return ApiResponse(
        ok=True,
        data=document_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).model_dump(),
    )


@router.get("/{document_id}", response_model=ApiResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a document by ID."""
    docs_repo = DocumentRepository(db)
    
    document = await docs_repo.get_by_id(document_id)
    if not document:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    return ApiResponse(
        ok=True,
        data=DocumentResponse.model_validate(document),
    )


@router.patch("/{document_id}", response_model=ApiResponse)
async def update_document(
    document_id: UUID,
    updates: DocumentUpdate,
    create_version: bool = Query(False, description="Create a new version"),
    db: AsyncSession = Depends(get_db),
):
    """Update a document."""
    docs_repo = DocumentRepository(db)
    
    # Check if document exists
    existing = await docs_repo.get_by_id(document_id)
    if not existing:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    try:
        # Create version if requested
        if create_version:
            version_no = await docs_repo.get_latest_version_number(document_id) + 1
            
            # Calculate diff (simplified)
            diff_data = None
            if updates.draft_content:
                diff_data = {
                    "old_content": existing.draft_content,
                    "new_content": updates.draft_content,
                    "changed_fields": [k for k, v in updates.model_dump().items() if v is not None],
                }
            
            await docs_repo.create_version(
                document_id=document_id,
                version_no=version_no,
                diff=diff_data,
                prompt="Manual update via API",
            )
        
        # Filter out None values
        update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
        
        document = await docs_repo.update(document_id, **update_data)
        
        return ApiResponse(
            ok=True,
            data=DocumentResponse.model_validate(document),
        )
        
    except Exception as e:
        raise ValidationError(f"Failed to update document: {str(e)}")


@router.delete("/{document_id}", response_model=ApiResponse)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document."""
    docs_repo = DocumentRepository(db)
    
    success = await docs_repo.delete(document_id)
    if not success:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    return ApiResponse(
        ok=True,
        data={"message": f"Document {document_id} deleted successfully"},
    )


@router.get("/{document_id}/export")
async def export_document(
    document_id: UUID,
    format: str = Query(..., description="Export format: pdf, docx, txt, or md"),
    db: AsyncSession = Depends(get_db),
):
    """Export document to specified format."""
    docs_repo = DocumentRepository(db)
    
    document = await docs_repo.get_by_id(document_id)
    if not document:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    try:
        format_lower = format.lower()
        
        if format_lower == "txt":
            content = await document_exporter.export_to_text(document)
            return Response(
                content=content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename={document.title or 'document'}_{document_id}.txt"
                }
            )
        elif format_lower == "md":
            content = await document_exporter.export_to_markdown(document)
            return Response(
                content=content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename={document.title or 'document'}_{document_id}.md"
                }
            )
        elif format_lower == "pdf":
            content_bytes = await document_exporter.export_document(document, DocFormat.PDF)
            return Response(
                content=content_bytes,
                media_type=document_exporter.get_content_type(DocFormat.PDF),
                headers={
                    "Content-Disposition": f"attachment; filename={document.title or 'document'}_{document_id}.pdf"
                }
            )
        elif format_lower == "docx":
            content_bytes = await document_exporter.export_document(document, DocFormat.DOCX)
            return Response(
                content=content_bytes,
                media_type=document_exporter.get_content_type(DocFormat.DOCX),
                headers={
                    "Content-Disposition": f"attachment; filename={document.title or 'document'}_{document_id}.docx"
                }
            )
        else:
            raise ValidationError(f"Unsupported format: {format}. Use: pdf, docx, txt, or md")
        
    except Exception as e:
        raise ValidationError(f"Failed to export document: {str(e)}")


@router.get("/{document_id}/versions", response_model=ApiResponse)
async def get_document_versions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all versions for a document."""
    docs_repo = DocumentRepository(db)
    
    # Verify document exists
    document = await docs_repo.get_by_id(document_id)
    if not document:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    versions = await docs_repo.get_document_versions(document_id)
    version_responses = [DocumentVersionResponse.model_validate(v) for v in versions]
    
    return ApiResponse(
        ok=True,
        data=version_responses,
    )


@router.get("/{document_id}/relationships", response_model=ApiResponse)
async def get_document_relationships(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get clusters, topics, and tags associated with a document."""
    docs_repo = DocumentRepository(db)
    
    # Verify document exists
    document = await docs_repo.get_by_id(document_id)
    if not document:
        raise NotFoundError(f"Document {document_id} not found", "Document")
    
    # Get relationships
    clusters = await docs_repo.get_document_clusters(document_id)
    topics = await docs_repo.get_document_topics(document_id)
    tags = await docs_repo.get_document_tags(document_id)
    
    return ApiResponse(
        ok=True,
        data={
            "clusters": [
                {
                    "id": str(rel["cluster"].id),
                    "title": rel["cluster"].title,
                    "kind": rel["cluster"].kind.value,
                    "contribution_weight": rel["contribution_weight"]
                }
                for rel in clusters
            ],
            "topics": [
                {
                    "id": str(rel["topic"].id),
                    "label": rel["topic"].label,
                    "confidence": rel["confidence"]
                }
                for rel in topics
            ],
            "tags": [
                {
                    "id": str(tag.id),
                    "name": tag.name
                }
                for tag in tags
            ]
        },
    )