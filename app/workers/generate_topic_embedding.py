import asyncio
from uuid import UUID
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.adapters.repos.topics_repo import TopicRepository
from app.adapters.llm import get_llm_provider
from app.core.config import get_settings
from app.core.logging import get_structured_logger
from app.core.database import async_session_maker

logger = get_structured_logger(__name__)
settings = get_settings()


async def generate_topic_embedding_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for generating embeddings for manually created topics.
    
    This worker:
    1. Gets the topic by ID
    2. Generates embedding for the topic label using LLM
    3. Stores the embedding in the database
    
    Args:
        job_id: The job ID for tracking
        payload: Dict containing topic_id
        
    Returns:
        Dict with embedding generation results
    """
    topic_id_str = payload.get("topic_id")
    if not topic_id_str:
        raise ValueError("Missing topic_id in payload")
    
    topic_id = UUID(topic_id_str)
    
    logger.info(
        "Starting topic embedding generation",
        job_id=str(job_id),
        topic_id=str(topic_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Get topic
            topics_repo = TopicRepository(db)
            topic = await topics_repo.get_by_id(topic_id)
            if not topic:
                raise ValueError(f"Topic {topic_id} not found")
            
            # Generate embedding using LLM
            llm_provider = get_llm_provider()
            embedding = await llm_provider.generate_embedding(topic.label)
            
            # Store embedding
            await topics_repo.vector_adapter.store_topic_embedding(topic_id, embedding)
            
            result = {
                "topic_id": str(topic_id),
                "topic_label": topic.label,
                "embedding_model": settings.embedding_model,
                "embedding_dims": len(embedding),
                "status": "completed"
            }
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Topic embedding generation completed",
                job_id=str(job_id),
                topic_id=str(topic_id),
                topic_label=topic.label,
                embedding_dims=len(embedding)
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
                "Topic embedding generation failed",
                job_id=str(job_id),
                topic_id=str(topic_id),
                error=str(e)
            )
            
            raise


async def run_generate_topic_embedding_worker():
    """
    Continuously poll for and process GENERATE_TOPIC_EMBEDDING jobs.
    """
    logger.info("Starting generate topic embedding worker")
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next queued job of this type
                job = await jobs_repo.get_next_queued_job(["GENERATE_TOPIC_EMBEDDING"])
                
                if job:
                    try:
                        # Process the job
                        await generate_topic_embedding_worker(job.id, job.payload or {})
                        
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
    asyncio.run(run_generate_topic_embedding_worker())