import asyncio
import signal
import sys
from typing import Dict, Callable, Any
from uuid import UUID

from app.core.logging import get_structured_logger
from app.workers.process_suggestion import process_suggestion_worker
from app.workers.extract_tags import extract_tags_worker
from app.workers.rebuild_clusters import (
    rebuild_tag_clusters_worker,
    rebuild_topic_clusters_worker,
    fusion_clustering_worker
)

logger = get_structured_logger(__name__)


class WorkerRunner:
    """
    Centralized worker runner that manages all background job processing.
    
    This runner:
    1. Polls for jobs of different types
    2. Routes jobs to appropriate worker functions
    3. Handles graceful shutdown
    4. Provides worker health monitoring
    """
    
    def __init__(self):
        self.running = True
        self.worker_tasks = []
        
        # Map job types to their worker functions
        self.job_handlers: Dict[str, Callable[[UUID, Dict[str, Any]], Any]] = {
            "PROCESS_SUGGESTION": process_suggestion_worker,
            "EXTRACT_TAGS": extract_tags_worker,
            "REBUILD_TAG_CLUSTERS": rebuild_tag_clusters_worker,
            "REBUILD_TOPIC_CLUSTERS": rebuild_topic_clusters_worker,
            "FUSION_CLUSTERING": fusion_clustering_worker,
            # Add more job types as needed
        }
        
        # Polling intervals for different job types (in seconds)
        self.polling_intervals = {
            "PROCESS_SUGGESTION": 2,    # Fast polling for user-triggered jobs
            "EXTRACT_TAGS": 5,          # Medium polling
            "REBUILD_TAG_CLUSTERS": 30, # Slow polling for maintenance jobs
            "REBUILD_TOPIC_CLUSTERS": 30,
            "FUSION_CLUSTERING": 60,
        }
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating graceful shutdown...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def poll_and_process_jobs(self, job_types: list, polling_interval: int):
        """
        Poll for jobs of specific types and process them.
        
        Args:
            job_types: List of job types to poll for
            polling_interval: How often to poll in seconds
        """
        from app.adapters.repos.jobs_repo import JobRepository
        from app.core.database import async_session_maker
        
        logger.info(f"Starting job poller for types: {job_types}")
        
        while self.running:
            try:
                async with async_session_maker() as db:
                    jobs_repo = JobRepository(db)
                    
                    # Get next queued job of these types
                    job = await jobs_repo.get_next_queued_job(job_types)
                    
                    if job:
                        handler = self.job_handlers.get(job.type)
                        if handler:
                            try:
                                logger.info(
                                    "Processing job",
                                    job_id=str(job.id),
                                    job_type=job.type
                                )
                                
                                # Process the job
                                result = await handler(job.id, job.payload or {})
                                
                                logger.info(
                                    "Job completed successfully",
                                    job_id=str(job.id),
                                    job_type=job.type
                                )
                                
                            except Exception as e:
                                logger.error(
                                    "Job processing failed",
                                    job_id=str(job.id),
                                    job_type=job.type,
                                    error=str(e)
                                )
                        else:
                            logger.warning("No handler for job type", job_type=job.type)
                    else:
                        # No jobs available, wait before polling again
                        await asyncio.sleep(polling_interval)
                        
            except Exception as e:
                logger.error(
                    "Job polling failed",
                    job_types=job_types,
                    error=str(e)
                )
                # Wait longer on polling errors
                await asyncio.sleep(polling_interval * 2)
    
    async def start_workers(self):
        """Start all background workers as concurrent tasks."""
        logger.info("Starting all background workers")
        
        # Group job types by similar polling intervals
        fast_jobs = ["PROCESS_SUGGESTION"]
        medium_jobs = ["EXTRACT_TAGS"]
        slow_jobs = ["REBUILD_TAG_CLUSTERS", "REBUILD_TOPIC_CLUSTERS"]
        very_slow_jobs = ["FUSION_CLUSTERING"]
        
        # Create polling tasks for each group
        self.worker_tasks = [
            asyncio.create_task(
                self.poll_and_process_jobs(fast_jobs, 2),
                name="fast-job-poller"
            ),
            asyncio.create_task(
                self.poll_and_process_jobs(medium_jobs, 5),
                name="medium-job-poller"
            ),
            asyncio.create_task(
                self.poll_and_process_jobs(slow_jobs, 30),
                name="slow-job-poller"
            ),
            asyncio.create_task(
                self.poll_and_process_jobs(very_slow_jobs, 60),
                name="very-slow-job-poller"
            ),
        ]
        
        try:
            # Wait for all tasks to complete (or be cancelled)
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        except Exception as e:
            logger.error("Worker task failed", error=str(e))
        finally:
            logger.info("All worker tasks completed")
    
    async def stop_workers(self):
        """Stop all background workers gracefully."""
        logger.info("Stopping background workers")
        
        self.running = False
        
        # Cancel all worker tasks
        for task in self.worker_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to finish cancellation
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        logger.info("All background workers stopped")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of all workers."""
        health = {
            "running": self.running,
            "worker_tasks": len(self.worker_tasks),
            "tasks_status": {}
        }
        
        for task in self.worker_tasks:
            task_name = task.get_name()
            health["tasks_status"][task_name] = {
                "done": task.done(),
                "cancelled": task.cancelled(),
                "exception": str(task.exception()) if task.done() and task.exception() else None
            }
        
        return health
    
    async def run(self):
        """Main runner method."""
        logger.info("Starting DSB Worker Runner")
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        try:
            # Start all workers
            await self.start_workers()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            # Graceful shutdown
            await self.stop_workers()
            logger.info("DSB Worker Runner stopped")


async def main():
    """Main entry point for running workers."""
    runner = WorkerRunner()
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReceived interrupt, shutting down...")
        sys.exit(0)