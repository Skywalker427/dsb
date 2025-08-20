from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.domain.models import Job


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        job_type: str,
        payload: Optional[dict] = None,
        run_at: Optional[datetime] = None,
    ) -> Job:
        """Create a new job."""
        job = Job(
            type=job_type,
            status="QUEUED",
            payload=payload,
            run_at=run_at,
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_id: UUID) -> Optional[Job]:
        """Get job by ID."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_next_queued_job(self, job_types: Optional[List[str]] = None) -> Optional[Job]:
        """Get the next queued job to process."""
        query = select(Job).where(Job.status == "QUEUED")
        
        if job_types:
            query = query.where(Job.type.in_(job_types))
            
        # Order by run_at (nulls last) then by created_at
        query = query.order_by(Job.run_at.nullslast(), Job.created_at)
        
        # Check if job should run now
        now = datetime.utcnow()
        query = query.where((Job.run_at.is_(None)) | (Job.run_at <= now))
        
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        error: Optional[str] = None,
        increment_attempts: bool = False,
    ) -> Optional[Job]:
        """Update job status and optionally error message."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
            
        job.status = status
        if error:
            job.last_error = error
        if increment_attempts:
            job.attempts += 1
                
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_jobs_by_status(
        self,
        status: str,
        job_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Job]:
        """Get jobs by status with optional type filter."""
        query = select(Job).where(Job.status == status)
        
        if job_type:
            query = query.where(Job.type == job_type)
            
        query = query.offset(offset).limit(limit).order_by(Job.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_failed_jobs(self, max_attempts: int = 5) -> List[Job]:
        """Get jobs that have failed and exceeded max attempts."""
        result = await self.db.execute(
            select(Job)
            .where(Job.status == "FAILED")
            .where(Job.attempts >= max_attempts)
            .order_by(Job.updated_at.desc())
        )
        return result.scalars().all()

    async def retry_job(self, job_id: UUID) -> Optional[Job]:
        """Retry a failed job by resetting its status to QUEUED."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job or job.status != "FAILED":
            return None
            
        job.status = "QUEUED"
        job.last_error = None
        job.run_at = None
                
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def delete_old_jobs(self, older_than: datetime) -> int:
        """Delete completed or failed jobs older than the specified date."""
        result = await self.db.execute(
            select(Job)
            .where(Job.status.in_(["SUCCEEDED", "FAILED"]))
            .where(Job.updated_at < older_than)
        )
        jobs_to_delete = result.scalars().all()
        
        count = len(jobs_to_delete)
        for job in jobs_to_delete:
            await self.db.delete(job)
            
        await self.db.commit()
        return count

    async def get_job_stats(self) -> dict:
        """Get statistics about job statuses."""
        result = await self.db.execute(
            select(Job.status, func.count().label("count"))
            .group_by(Job.status)
        )
        
        stats = {row.status: row.count for row in result}
        return stats

    async def count(self, status: Optional[str] = None, job_type: Optional[str] = None) -> int:
        """Count jobs with optional filters."""
        query = select(func.count(Job.id))
        
        if status:
            query = query.where(Job.status == status)
        if job_type:
            query = query.where(Job.type == job_type)
        
        result = await self.db.execute(query)
        return result.scalar()