from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.topics_repo import TopicRepository
from app.core.errors import NotFoundError
from app.domain.schemas import (
    ApiResponse,
    TopicCreate,
    TopicResponse,
    PaginationMeta,
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
    
    topic_responses = [TopicResponse.from_orm(t) for t in topics]
    
    return ApiResponse(
        ok=True,
        data=topic_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).dict(),
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
        data=TopicResponse.from_orm(topic),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_topic(
    topic_data: TopicCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new topic."""
    topics_repo = TopicRepository(db)
    
    topic = await topics_repo.create(topic_data)
    
    return ApiResponse(
        ok=True,
        data=TopicResponse.from_orm(topic),
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
        data=TopicResponse.from_orm(topic),
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
        data=TopicResponse.from_orm(target_topic),
    )