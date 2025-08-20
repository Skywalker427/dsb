import asyncio
from uuid import UUID
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.core.logging import get_structured_logger
from app.services.suggestions import TagExtractionService
from app.core.database import async_session_maker

logger = get_structured_logger(__name__)


async def extract_tags_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for extracting tags from documents.
    
    This worker:
    1. Extracts tags from document text using LLM/YAKE
    2. Normalizes and stores tags
    3. Updates tag clusters if needed
    
    Args:
        job_id: The job ID for tracking
        payload: Dict containing document_id and optional text
        
    Returns:
        Dict with extraction results
    """
    document_id_str = payload.get("document_id")
    if not document_id_str:
        raise ValueError("Missing document_id in payload")
    
    document_id = UUID(document_id_str)
    text = payload.get("text", "")
    
    logger.info(
        "Starting tag extraction",
        job_id=str(job_id),
        document_id=str(document_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize tag extraction service
            tag_service = TagExtractionService(db)
            
            # Extract tags from text
            if not text:
                # TODO: Get document text from document repository
                text = payload.get("fallback_text", "")
            
            extracted_tags = await tag_service.extract_tags_from_text(text)
            
            # TODO: Store tags in document_tags table
            # This would involve:
            # 1. Creating/finding tag records
            # 2. Creating document_tag associations
            # 3. Triggering tag cluster rebuild if needed
            
            result = {
                "document_id": str(document_id),
                "tags_extracted": len(extracted_tags),
                "tags": extracted_tags
            }
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Tag extraction completed",
                job_id=str(job_id),
                document_id=str(document_id),
                tags_count=len(extracted_tags),
                tags=extracted_tags
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
                "Tag extraction failed",
                job_id=str(job_id),
                document_id=str(document_id),
                error=str(e)
            )
            
            raise


async def run_extract_tags_worker():
    """
    Continuously poll for and process EXTRACT_TAGS jobs.
    """
    logger.info("Starting extract tags worker")
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next queued job of this type
                job = await jobs_repo.get_next_queued_job(["EXTRACT_TAGS"])
                
                if job:
                    try:
                        # Process the job
                        await extract_tags_worker(job.id, job.payload or {})
                        
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
            await asyncio.sleep(10)


if __name__ == "__main__":
    # Run the worker directly for testing
    asyncio.run(run_extract_tags_worker())