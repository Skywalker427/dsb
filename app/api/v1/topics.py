from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.topics_repo import TopicRepository
from app.adapters.repos.jobs_repo import JobRepository
from app.core.errors import NotFoundError, ValidationError
from app.domain.schemas import (
    ApiResponse,
    TopicCreate,
    TopicResponse,
    PaginationMeta,
    SuggestionResponse,
)
from app.core.database import get_db

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def get_topics(
    query: Optional[str] = Query(None),
    min_support: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get topics with optional filters and pagination."""
    topics_repo = TopicRepository(db)
    
    offset = (page - 1) * page_size
    topics = await topics_repo.get_all(query, min_support, offset, page_size)
    total = await topics_repo.count(query, min_support)
    
    topic_responses = [TopicResponse.model_validate(t) for t in topics]
    
    return ApiResponse(
        ok=True,
        data=topic_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).model_dump(),
    )


@router.get("/{topic_id}", response_model=ApiResponse)
async def get_topic(
    topic_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a topic by ID."""
    topics_repo = TopicRepository(db)
    
    topic = await topics_repo.get_by_id(topic_id)
    if not topic:
        raise NotFoundError(f"Topic {topic_id} not found", "Topic")
    
    return ApiResponse(
        ok=True,
        data=TopicResponse.model_validate(topic),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_topic(
    topic_data: TopicCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new topic and generate embeddings asynchronously."""
    topics_repo = TopicRepository(db)
    jobs_repo = JobRepository(db)
    
    # Create the topic first
    topic = await topics_repo.create(topic_data)
    
    # Create a job to generate embeddings for this topic
    await jobs_repo.create(
        job_type="GENERATE_TOPIC_EMBEDDING",
        payload={"topic_id": str(topic.id)}
    )
    
    return ApiResponse(
        ok=True,
        data=TopicResponse.model_validate(topic),
    )


@router.patch("/{topic_id}", response_model=ApiResponse)
async def update_topic(
    topic_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a topic."""
    topics_repo = TopicRepository(db)
    
    topic = await topics_repo.update(topic_id, **updates)
    if not topic:
        raise NotFoundError(f"Topic {topic_id} not found", "Topic")
    
    return ApiResponse(
        ok=True,
        data=TopicResponse.model_validate(topic),
    )


@router.post("/merge", response_model=ApiResponse)
async def merge_topics(
    merge_data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Merge multiple topics into a target topic."""
    topics_repo = TopicRepository(db)
    
    source_topic_ids = [UUID(id_str) for id_str in merge_data["source_topic_ids"]]
    target_label = merge_data["target_label"]
    
    target_topic = await topics_repo.merge_topics(source_topic_ids, target_label)
    
    return ApiResponse(
        ok=True,
        data=TopicResponse.model_validate(target_topic),
    )


@router.get("/{topic_id}/suggestions", response_model=ApiResponse)
async def get_topic_suggestions(
    topic_id: UUID,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get all suggestions associated with a topic."""
    topics_repo = TopicRepository(db)
    
    # First verify the topic exists
    topic = await topics_repo.get_by_id(topic_id)
    if not topic:
        raise NotFoundError(f"Topic {topic_id} not found", "Topic")
    
    # Get suggestions with confidence scores
    suggestions_with_confidence = await topics_repo.get_suggestions_by_topic(
        topic_id=topic_id,
        min_confidence=min_confidence,
        limit=limit
    )
    
    # Format response data
    suggestions_data = [
        {
            "suggestion": SuggestionResponse.model_validate(suggestion).model_dump(),
            "confidence": confidence
        }
        for suggestion, confidence in suggestions_with_confidence
    ]
    
    return ApiResponse(
        ok=True,
        data={
            "topic": TopicResponse.model_validate(topic).model_dump(),
            "suggestions": suggestions_data,
            "total": len(suggestions_data)
        }
    )


@router.post("/{topic_id}/suggestions/{suggestion_id}", response_model=ApiResponse, status_code=201)
async def add_topic_suggestion_association(
    topic_id: UUID,
    suggestion_id: UUID,
    association_data: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """Add an association between a topic and a suggestion."""
    from app.adapters.repos.suggestions_repo import SuggestionRepository
    
    topics_repo = TopicRepository(db)
    suggestions_repo = SuggestionRepository(db)
    
    # Verify both topic and suggestion exist
    topic = await topics_repo.get_by_id(topic_id)
    if not topic:
        raise NotFoundError(f"Topic {topic_id} not found", "Topic")
        
    suggestion = await suggestions_repo.get_by_id(suggestion_id)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
    
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
            "topic_id": str(topic_id),
            "suggestion_id": str(suggestion_id),
            "confidence": confidence,
            "message": "Association created successfully"
        }
    )


@router.delete("/{topic_id}/suggestions/{suggestion_id}", response_model=ApiResponse)
async def remove_topic_suggestion_association(
    topic_id: UUID,
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove an association between a topic and a suggestion."""
    topics_repo = TopicRepository(db)
    
    # Remove the association
    success = await topics_repo.remove_suggestion_topic_association(
        suggestion_id=suggestion_id,
        topic_id=topic_id
    )
    
    if not success:
        raise NotFoundError(f"Association between topic {topic_id} and suggestion {suggestion_id} not found", "Association")
    
    return ApiResponse(
        ok=True,
        data={
            "topic_id": str(topic_id),
            "suggestion_id": str(suggestion_id),
            "message": "Association removed successfully"
        }
    )