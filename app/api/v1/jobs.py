from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.core.errors import NotFoundError
from app.domain.schemas import ApiResponse, JobResponse, PaginationMeta
from app.core.database import get_db

router = APIRouter()


@router.get("/{job_id}", response_model=ApiResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a job by ID."""
    jobs_repo = JobRepository(db)
    
    job = await jobs_repo.get_by_id(job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found", "Job")
    
    return ApiResponse(
        ok=True,
        data=JobResponse.from_orm(job),
    )


@router.get("", response_model=ApiResponse)
async def get_jobs(
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get jobs with optional filters and pagination."""
    jobs_repo = JobRepository(db)
    
    offset = (page - 1) * page_size
    
    if status:
        jobs = await jobs_repo.get_jobs_by_status(status, job_type, offset, page_size)
        total = await jobs_repo.count(status, job_type)
    else:
        # Get all jobs - you'd implement this method in JobRepository
        jobs = []
        total = 0
    
    job_responses = [JobResponse.from_orm(j) for j in jobs]
    
    return ApiResponse(
        ok=True,
        data=job_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).dict(),
    )


@router.post("/{job_id}/retry", response_model=ApiResponse)
async def retry_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed job."""
    jobs_repo = JobRepository(db)
    
    job = await jobs_repo.retry_job(job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found or cannot be retried", "Job")
    
    return ApiResponse(
        ok=True,
        data=JobResponse.from_orm(job),
    )


@router.get("/stats", response_model=ApiResponse)
async def get_job_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get job statistics."""
    jobs_repo = JobRepository(db)
    
    stats = await jobs_repo.get_job_stats()
    
    return ApiResponse(
        ok=True,
        data=stats,
    )