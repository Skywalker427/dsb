import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.core.logging import get_structured_logger
from app.services.suggestions import SuggestionProcessingService
from app.core.database import async_session_maker

logger = get_structured_logger(__name__)


async def process_suggestion_worker(job_id: UUID, payload: dict) -> dict:
    """
    Worker for processing suggestions through the AI pipeline.
    
    This worker:
    1. Generates embeddings for the suggestion
    2. Assigns it to appropriate clusters
    3. Updates the suggestion status
    
    Args:
        job_id: The job ID for tracking
        payload: Dict containing suggestion_id
        
    Returns:
        Dict with processing results
    """
    suggestion_id_str = payload.get("suggestion_id")
    if not suggestion_id_str:
        raise ValueError("Missing suggestion_id in payload")
    
    suggestion_id = UUID(suggestion_id_str)
    
    logger.info(
        "Starting suggestion processing",
        job_id=str(job_id),
        suggestion_id=str(suggestion_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize processing service
            processing_service = SuggestionProcessingService(db)
            
            # Process the suggestion
            result = await processing_service.process_suggestion(suggestion_id)
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Suggestion processing completed",
                job_id=str(job_id),
                suggestion_id=str(suggestion_id),
                cluster_id=result.get("cluster_id"),
                similarity=result.get("similarity")
            )
            
            return result
            
        except Exception as e:
            # Update job status to failed
            await jobs_repo.update_status(
                job_id, 
                "FAILED", 
                error=str(e),
                increment_attempts=True
            )
            
            logger.error(
                "Suggestion processing failed",
                job_id=str(job_id),
                suggestion_id=str(suggestion_id),
                error=str(e)
            )
            
            raise


async def run_process_suggestion_worker():
    """
    Continuously poll for and process PROCESS_SUGGESTION jobs.
    This would typically run as a separate process or container.
    """
    logger.info("Starting process suggestion worker")
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next queued job of this type
                job = await jobs_repo.get_next_queued_job(["PROCESS_SUGGESTION"])
                
                if job:
                    try:
                        # Process the job
                        await process_suggestion_worker(job.id, job.payload or {})
                        
                    except Exception as e:
                        logger.error(
                            "Worker job processing failed",
                            job_id=str(job.id),
                            error=str(e)
                        )
                else:
                    # No jobs available, wait before polling again
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error("Worker polling failed", error=str(e))
            await asyncio.sleep(10)  # Wait longer on polling errors


if __name__ == "__main__":
    # Run the worker directly for testing
    asyncio.run(run_process_suggestion_worker())