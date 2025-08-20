import asyncio
from uuid import UUID
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.core.logging import get_structured_logger
from app.services.clustering import MultiViewClusteringService
from app.core.database import async_session_maker

logger = get_structured_logger(__name__)


async def rebuild_tag_clusters_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for rebuilding TAG clusters.
    
    This worker:
    1. Analyzes all document tags
    2. Creates clusters for tags meeting support threshold
    3. Updates cluster weights and membership
    
    Args:
        job_id: The job ID for tracking
        payload: Dict with optional parameters
        
    Returns:
        Dict with rebuild results
    """
    logger.info(
        "Starting tag cluster rebuild",
        job_id=str(job_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize clustering service
            clustering_service = MultiViewClusteringService(db)
            
            # Rebuild tag clusters
            result = await clustering_service.rebuild_tag_clusters()
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Tag cluster rebuild completed",
                job_id=str(job_id),
                clusters_created=result.get("clusters_created", 0)
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
                "Tag cluster rebuild failed",
                job_id=str(job_id),
                error=str(e)
            )
            
            raise


async def rebuild_topic_clusters_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for rebuilding TOPIC clusters.
    
    This worker:
    1. Analyzes all topics
    2. Creates clusters for topics meeting support threshold  
    3. Updates cluster weights and membership
    
    Args:
        job_id: The job ID for tracking
        payload: Dict with optional parameters
        
    Returns:
        Dict with rebuild results
    """
    logger.info(
        "Starting topic cluster rebuild",
        job_id=str(job_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize clustering service
            clustering_service = MultiViewClusteringService(db)
            
            # Rebuild topic clusters
            result = await clustering_service.rebuild_topic_clusters()
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Topic cluster rebuild completed",
                job_id=str(job_id),
                clusters_created=result.get("clusters_created", 0)
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
                "Topic cluster rebuild failed",
                job_id=str(job_id),
                error=str(e)
            )
            
            raise


async def fusion_clustering_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for creating FUSION clusters.
    
    This worker:
    1. Analyzes documents with embeddings, tags, and topics
    2. Calculates hybrid similarities
    3. Creates fusion clusters using composite scoring
    
    Args:
        job_id: The job ID for tracking
        payload: Dict with optional clustering parameters
        
    Returns:
        Dict with clustering results
    """
    logger.info(
        "Starting fusion clustering",
        job_id=str(job_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Initialize clustering service
            clustering_service = MultiViewClusteringService(db)
            
            # Create fusion clusters
            result = await clustering_service.create_fusion_clusters()
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Fusion clustering completed",
                job_id=str(job_id),
                clusters_created=result.get("clusters_created", 0)
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
                "Fusion clustering failed",
                job_id=str(job_id),
                error=str(e)
            )
            
            raise


async def run_clustering_workers():
    """
    Continuously poll for and process clustering jobs.
    This handles REBUILD_TAG_CLUSTERS, REBUILD_TOPIC_CLUSTERS, and FUSION_CLUSTERING jobs.
    """
    logger.info("Starting clustering workers")
    
    job_handlers = {
        "REBUILD_TAG_CLUSTERS": rebuild_tag_clusters_worker,
        "REBUILD_TOPIC_CLUSTERS": rebuild_topic_clusters_worker,
        "FUSION_CLUSTERING": fusion_clustering_worker,
    }
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next queued job of any clustering type
                job = await jobs_repo.get_next_queued_job(list(job_handlers.keys()))
                
                if job:
                    handler = job_handlers.get(job.type)
                    if handler:
                        try:
                            # Process the job with appropriate handler
                            await handler(job.id, job.payload or {})
                            
                        except Exception as e:
                            logger.error(
                                "Clustering job processing failed",
                                job_id=str(job.id),
                                job_type=job.type,
                                error=str(e)
                            )
                    else:
                        logger.warning("Unknown job type", job_type=job.type)
                else:
                    # No jobs available, wait before polling again
                    await asyncio.sleep(10)  # Longer wait for clustering jobs
                    
        except Exception as e:
            logger.error("Clustering worker polling failed", error=str(e))
            await asyncio.sleep(15)


if __name__ == "__main__":
    # Run the worker directly for testing
    asyncio.run(run_clustering_workers())