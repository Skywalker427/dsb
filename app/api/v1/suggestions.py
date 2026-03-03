from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.jobs_repo import JobRepository
from app.adapters.repos.topics_repo import TopicRepository
from app.core.errors import NotFoundError, ValidationError
from app.domain.schemas import (
    ApiResponse,
    SuggestionCreate,
    SuggestionResponse,
    SuggestionFilters,
    JobResponse,
    PaginationMeta,
    TopicResponse,
)
from app.core.database import get_db

router = APIRouter()


@router.post("", response_model=ApiResponse, status_code=202)
async def create_suggestion(
    suggestion_data: SuggestionCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new suggestion and queue it for processing."""
    suggestions_repo = SuggestionRepository(db)
    jobs_repo = JobRepository(db)
    
    try:
        # Create the suggestion
        suggestion = await suggestions_repo.create(suggestion_data)
        
        # Create a job to process the suggestion
        job = await jobs_repo.create(
            job_type="PROCESS_SUGGESTION",
            payload={"suggestion_id": str(suggestion.id)},
        )
        
        return ApiResponse(
            ok=True,
            data={
                "id": suggestion.id,
                "status": suggestion.status.value,
                "job_id": job.id,
            },
        )
        
    except Exception as e:
        raise ValidationError(f"Failed to create suggestion: {str(e)}")


@router.get("/{suggestion_id}", response_model=ApiResponse)
async def get_suggestion(
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a suggestion by ID."""
    suggestions_repo = SuggestionRepository(db)
    
    suggestion = await suggestions_repo.get_by_id(suggestion_id)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
    
    return ApiResponse(
        ok=True,
        data=SuggestionResponse.model_validate(suggestion),
    )


@router.get("", response_model=ApiResponse)
async def get_suggestions(
    author_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get suggestions with optional filters and pagination."""
    suggestions_repo = SuggestionRepository(db)
    
    # Build filters
    filters = SuggestionFilters(
        author_type=author_type,
        category=category,
        status=status,
        language=language,
        tag=tag,
    )
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get suggestions and total count
    suggestions = await suggestions_repo.get_all(filters, offset, page_size)
    total = await suggestions_repo.count(filters)
    
    # Convert to response models
    suggestion_responses = [SuggestionResponse.model_validate(s) for s in suggestions]
    
    return ApiResponse(
        ok=True,
        data=suggestion_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).model_dump(),
    )


@router.patch("/{suggestion_id}", response_model=ApiResponse)
async def update_suggestion(
    suggestion_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a suggestion."""
    suggestions_repo = SuggestionRepository(db)
    
    suggestion = await suggestions_repo.update(suggestion_id, **updates)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
    
    return ApiResponse(
        ok=True,
        data=SuggestionResponse.model_validate(suggestion),
    )


@router.delete("/{suggestion_id}", response_model=ApiResponse)
async def delete_suggestion(
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a suggestion."""
    suggestions_repo = SuggestionRepository(db)
    
    success = await suggestions_repo.delete(suggestion_id)
    if not success:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
    
    return ApiResponse(
        ok=True,
        data={"message": f"Suggestion {suggestion_id} deleted successfully"},
    )


@router.get("/{suggestion_id}/topics", response_model=ApiResponse)
async def get_suggestion_topics(
    suggestion_id: UUID,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Get all topics associated with a suggestion."""
    suggestions_repo = SuggestionRepository(db)
    topics_repo = TopicRepository(db)
    
    # First verify the suggestion exists
    suggestion = await suggestions_repo.get_by_id(suggestion_id)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
    
    # Get topics with confidence scores
    topics_with_confidence = await topics_repo.get_topics_by_suggestion(
        suggestion_id=suggestion_id,
        min_confidence=min_confidence
    )
    
    # Format response data
    topics_data = [
        {
            "topic": TopicResponse.model_validate(topic).model_dump(),
            "confidence": confidence
        }
        for topic, confidence in topics_with_confidence
    ]
    
    return ApiResponse(
        ok=True,
        data={
            "suggestion": SuggestionResponse.model_validate(suggestion).model_dump(),
            "topics": topics_data,
            "total": len(topics_data)
        }
    )


@router.post("/{suggestion_id}/topics/{topic_id}", response_model=ApiResponse, status_code=201)
async def add_suggestion_topic_association(
    suggestion_id: UUID,
    topic_id: UUID,
    association_data: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """Add an association between a suggestion and a topic."""
    suggestions_repo = SuggestionRepository(db)
    topics_repo = TopicRepository(db)
    
    # Verify both suggestion and topic exist
    suggestion = await suggestions_repo.get_by_id(suggestion_id)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
        
    topic = await topics_repo.get_by_id(topic_id)
    if not topic:
        raise NotFoundError(f"Topic {topic_id} not found", "Topic")
    
    # Get confidence from request data (default to 0.5)
    confidence = association_data.get("confidence", 0.5)
    if not 0.0 <= confidence <= 1.0:
        raise ValidationError("Confidence must be between 0.0 and 1.0", "confidence")
    
    # Create the association
    association = await topics_repo.add_suggestion_topic_association(
        suggestion_id=suggestion_id,
        topic_id=topic_id,
        confidence=confidence
    )
    
    return ApiResponse(
        ok=True,
        data={
            "suggestion_id": str(suggestion_id),
            "topic_id": str(topic_id),
            "confidence": confidence,
            "message": "Association created successfully"
        }
    )


@router.delete("/{suggestion_id}/topics/{topic_id}", response_model=ApiResponse)
async def remove_suggestion_topic_association(
    suggestion_id: UUID,
    topic_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove an association between a suggestion and a topic."""
    topics_repo = TopicRepository(db)
    
    # Remove the association
    success = await topics_repo.remove_suggestion_topic_association(
        suggestion_id=suggestion_id,
        topic_id=topic_id
    )
    
    if not success:
        raise NotFoundError(f"Association between suggestion {suggestion_id} and topic {topic_id} not found", "Association")
    
    return ApiResponse(
        ok=True,
        data={
            "suggestion_id": str(suggestion_id),
            "topic_id": str(topic_id),
            "message": "Association removed successfully"
        }
    )