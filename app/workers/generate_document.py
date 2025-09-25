import asyncio
from uuid import UUID
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.core.logging import get_structured_logger
from app.services.document_generator import get_document_generator
from app.core.database import async_session_maker

logger = get_structured_logger(__name__)


async def generate_document_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for generating documents from clusters or topics using iterative LLM processing.
    
    This worker:
    1. Takes a document generation job payload
    2. Processes suggestions iteratively using LLM
    3. Creates the final document with metadata
    4. Associates the document with clusters/topics
    
    Args:
        job_id: The job ID for tracking
        payload: Dict containing document generation parameters
        
    Returns:
        Dict with generation results including document ID
    """
    logger.info(
        "Starting document generation",
        job_id=str(job_id),
        source_type=payload.get("source_type"),
        source_id=payload.get("source_id")
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize document generator service
            doc_generator = get_document_generator(db)
            
            # Process the document generation
            document = await doc_generator.process_document_generation_job(payload)
            
            # Mark job as completed with results
            result = {
                "document_id": str(document.id),
                "title": document.title,
                "status": document.status.value,
                "source_type": payload.get("source_type"),
                "source_id": payload.get("source_id"),
                "template_id": payload.get("template_id"),
                "total_suggestions_processed": payload.get("total_suggestions", 0),
            }
            
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Document generation completed successfully",
                job_id=str(job_id),
                document_id=str(document.id),
                title=document.title
            )
            
            return result
            
        except Exception as e:
            # Mark job as failed
            error_msg = f"Document generation failed: {str(e)}"
            await jobs_repo.update_status(job_id, "FAILED", error=error_msg)
            
            logger.error(
                "Document generation failed",
                job_id=str(job_id),
                error=str(e),
                source_type=payload.get("source_type"),
                source_id=payload.get("source_id")
            )
            
            raise


async def run_generate_document_worker():
    """
    Standalone document generation worker for testing or individual execution.
    """
    from app.adapters.repos.jobs_repo import JobRepository
    
    logger.info("Starting generate document worker")
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next document generation job
                job = await jobs_repo.get_next_queued_job(["GENERATE_DOCUMENT"])
                
                if job:
                    try:
                        await generate_document_worker(job.id, job.payload or {})
                    except Exception as e:
                        logger.error("Document generation job failed", job_id=str(job.id), error=str(e))
                else:
                    # No jobs available, wait
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error("Document generation worker polling failed", error=str(e))
            await asyncio.sleep(10)


if __name__ == "__main__":
    # Run the worker directly for testing
    asyncio.run(run_generate_document_worker())