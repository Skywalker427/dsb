from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.jobs_repo import JobRepository
from app.core.errors import NotFoundError, ValidationError
from app.domain.schemas import (
    ApiResponse,
    SuggestionCreate,
    SuggestionResponse,
    SuggestionFilters,
    JobResponse,
    PaginationMeta,
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
        data=SuggestionResponse.from_orm(suggestion),
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
    suggestion_responses = [SuggestionResponse.from_orm(s) for s in suggestions]
    
    return ApiResponse(
        ok=True,
        data=suggestion_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).dict(),
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
        data=SuggestionResponse.from_orm(suggestion),
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