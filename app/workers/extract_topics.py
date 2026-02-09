import asyncio
from uuid import UUID
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.jobs_repo import JobRepository
from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.topics_repo import TopicRepository
from app.adapters.llm import get_llm_provider
from app.adapters.llm.base import EmbeddingProvider, LLMProvider
from app.core.config import get_settings
from app.core.logging import get_structured_logger
from app.core.database import async_session_maker
from app.domain.schemas import TopicCreate

logger = get_structured_logger(__name__)
settings = get_settings()


async def extract_topics_worker(job_id: UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker for extracting topics from suggestions.
    
    This worker:
    1. Extracts topics from suggestion text using LLM
    2. Reuses existing topics or creates new ones based on similarity threshold
    3. Creates topic associations
    4. Triggers topic cluster creation if needed
    
    Args:
        job_id: The job ID for tracking
        payload: Dict containing suggestion_id
        
    Returns:
        Dict with extraction results
    """
    suggestion_id_str = payload.get("suggestion_id")
    if not suggestion_id_str:
        raise ValueError("Missing suggestion_id in payload")
    
    suggestion_id = UUID(suggestion_id_str)
    
    logger.info(
        "Starting topic extraction",
        job_id=str(job_id),
        suggestion_id=str(suggestion_id)
    )
    
    async with async_session_maker() as db:
        try:
            # Update job status to running
            jobs_repo = JobRepository(db)
            await jobs_repo.update_status(job_id, "RUNNING")
            
            # Get suggestion
            suggestions_repo = SuggestionRepository(db)
            suggestion = await suggestions_repo.get_by_id(suggestion_id)
            if not suggestion:
                raise ValueError(f"Suggestion {suggestion_id} not found")
            
            # Extract topics using LLM
            llm_provider = get_llm_provider()
            topics_repo = TopicRepository(db)
            
            # Combine title and body for topic extraction
            text = f"{suggestion.title}\n\n{suggestion.body}"
            
            # Extract topic labels (≤5 as per PRD)
            extracted_topics = await llm_provider.extract_topics(text, max_topics=5)
            
            created_topics = []
            reused_topics = []
            
            for topic_data in extracted_topics:
                # Extract label from the topic data dictionary
                if isinstance(topic_data, dict):
                    topic_label = topic_data.get("label", "")
                else:
                    topic_label = str(topic_data)
                
                if not topic_label:
                    continue
                    
                # Check if topic already exists or can be reused
                existing_topic = await _find_or_create_topic(
                    topics_repo, llm_provider, topic_label
                )
                
                if existing_topic.get("created"):
                    created_topics.append(existing_topic["topic"])
                else:
                    reused_topics.append(existing_topic["topic"])
                
                # Create suggestion-topic association with default confidence
                confidence = 0.8  # High confidence for LLM-extracted topics
                await topics_repo.add_suggestion_topic_association(
                    suggestion_id=suggestion_id,
                    topic_id=existing_topic["topic"].id,
                    confidence=confidence
                )
                
            result = {
                "suggestion_id": str(suggestion_id),
                "topics_extracted": len(extracted_topics),
                "topics_created": len(created_topics),
                "topics_reused": len(reused_topics),
                "topics": [{"label": t.label, "id": str(t.id)} for t in created_topics + reused_topics]
            }
            
            # Create job to rebuild topic clusters if new topics were created
            if created_topics:
                await jobs_repo.create(
                    job_type="REBUILD_TOPIC_CLUSTERS",
                    payload={"trigger": "new_topics_created"}
                )
            
            # Update job status to succeeded
            await jobs_repo.update_status(job_id, "SUCCEEDED")
            
            logger.info(
                "Topic extraction completed",
                job_id=str(job_id),
                suggestion_id=str(suggestion_id),
                topics_created=len(created_topics),
                topics_reused=len(reused_topics)
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
                "Topic extraction failed",
                job_id=str(job_id),
                suggestion_id=str(suggestion_id),
                error=str(e)
            )
            
            raise


async def _find_or_create_topic(
    topics_repo: TopicRepository, 
    llm_provider: EmbeddingProvider, 
    topic_label: str
) -> Dict[str, Any]:
    """
    Find existing topic or create new one based on similarity threshold.
    
    Args:
        topics_repo: Topic repository
        llm_provider: LLM provider for embeddings
        topic_label: The topic label to find or create
        
    Returns:
        Dict with topic and created flag
    """
    try:
        # First check for exact match
        existing_topic = await topics_repo.get_by_label(topic_label)
        if existing_topic:
            return {"topic": existing_topic, "created": False}
        
        # Generate embedding for the topic label
        topic_embedding = await llm_provider.generate_embedding(topic_label)
        
        # Find similar topics using vector similarity
        similar_topics = await topics_repo.find_similar_topics(
            embedding=topic_embedding, 
            threshold=settings.topic_reuse_threshold,
            limit=3
        )
        
        # If we found similar topics above threshold, reuse the most similar one
        if similar_topics:
            most_similar_topic, similarity = similar_topics[0]
            logger.info(
                "Reusing similar topic",
                existing_topic_id=str(most_similar_topic.id),
                existing_label=most_similar_topic.label,
                new_label=topic_label,
                similarity=similarity
            )
            return {"topic": most_similar_topic, "created": False}
        
        # Create new topic with embedding
        topic_data = TopicCreate(
            label=topic_label,
            description=f"Auto-generated topic: {topic_label}"
        )
        
        new_topic = await topics_repo.create(topic_data, embedding=topic_embedding)
        
        logger.info(
            "Created new topic with embedding",
            topic_id=str(new_topic.id),
            label=topic_label
        )
        
        return {"topic": new_topic, "created": True}
        
    except Exception as e:
        logger.error(
            "Failed to find or create topic",
            label=topic_label,
            error=str(e)
        )
        raise


async def run_extract_topics_worker():
    """
    Continuously poll for and process EXTRACT_TOPICS jobs.
    """
    logger.info("Starting extract topics worker")
    
    while True:
        try:
            async with async_session_maker() as db:
                jobs_repo = JobRepository(db)
                
                # Get next queued job of this type
                job = await jobs_repo.get_next_queued_job(["EXTRACT_TOPICS"])
                
                if job:
                    try:
                        # Process the job
                        await extract_topics_worker(job.id, job.payload or {})
                        
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
    asyncio.run(run_extract_topics_worker())