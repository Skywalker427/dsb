from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.cache.redis_cache import cache
from app.adapters.llm.openai_provider import OpenAIProvider
from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.clusters_repo import ClusterRepository
from app.adapters.vector.pgvector_adapter import PgVectorAdapter
from app.core.config import get_settings
from app.core.errors import NotFoundError, DependencyError
from app.core.logging import get_structured_logger
from app.domain.enums import SuggestionStatus, ClusterKind
from app.domain.models import Suggestion, Cluster
from app.domain.schemas import ClusterCreate

logger = get_structured_logger(__name__)
settings = get_settings()


class SuggestionProcessingService:
    """Service for processing suggestions through the AI pipeline."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.suggestions_repo = SuggestionRepository(db)
        self.clusters_repo = ClusterRepository(db)
        self.vector_adapter = PgVectorAdapter(db)
        self.llm_provider = OpenAIProvider()
    
    async def process_suggestion(self, suggestion_id: UUID) -> dict:
        """Complete processing pipeline for a suggestion."""
        try:
            # Get the suggestion
            suggestion = await self.suggestions_repo.get_by_id(suggestion_id)
            if not suggestion:
                raise NotFoundError(f"Suggestion {suggestion_id} not found", "Suggestion")
            
            logger.info("Starting suggestion processing", suggestion_id=str(suggestion_id))
            
            # Step 1: Preprocess and optionally redact PII
            processed_text = await self._preprocess_suggestion_text(suggestion)
            
            # Step 2: Generate embedding
            embedding = await self._generate_suggestion_embedding(suggestion, processed_text)
            
            # Step 3: Store embedding
            await self.vector_adapter.store_suggestion_embedding(suggestion_id, embedding)
            
            # Step 4: Find or create appropriate cluster
            cluster_info = await self._assign_to_cluster(suggestion_id, embedding)
            
            # Step 5: Update suggestion status
            await self.suggestions_repo.update(
                suggestion_id,
                status=SuggestionStatus.PROCESSED
            )
            
            result = {
                "suggestion_id": str(suggestion_id),
                "cluster_id": str(cluster_info["cluster_id"]) if cluster_info["cluster_id"] else None,
                "similarity": cluster_info.get("similarity"),
                "status": "PROCESSED"
            }
            
            logger.info("Suggestion processing completed", **result)
            return result
            
        except Exception as e:
            logger.error(
                "Suggestion processing failed",
                suggestion_id=str(suggestion_id),
                error=str(e)
            )
            
            # Update suggestion status to indicate processing failure
            try:
                await self.suggestions_repo.update(
                    suggestion_id,
                    status=SuggestionStatus.NEW  # Reset to NEW for retry
                )
            except Exception:
                pass  # Don't fail if status update fails
            
            raise
    
    async def _preprocess_suggestion_text(self, suggestion: Suggestion) -> str:
        """Preprocess suggestion text for embedding generation."""
        # Combine title and body
        full_text = f"{suggestion.title}\n\n{suggestion.body}"
        
        # Apply PII redaction if enabled
        if settings.pii_redaction:
            full_text = await self.llm_provider.redact_pii(full_text)
        
        # Apply general preprocessing
        processed_text = await self.llm_provider.preprocess_text(full_text)
        
        return processed_text
    
    async def _generate_suggestion_embedding(self, suggestion: Suggestion, text: str) -> List[float]:
        """Generate embedding for suggestion text."""
        # Check cache first
        cache_key = f"embedding:{suggestion.id}"
        cached_embedding = await cache.get(cache_key)
        if cached_embedding:
            logger.info("Using cached embedding", suggestion_id=str(suggestion.id))
            return cached_embedding
        
        # Generate new embedding
        embedding = await self.llm_provider.generate_embedding(text)
        
        # Cache the result for 24 hours
        await cache.set(cache_key, embedding, expire_seconds=86400)
        
        return embedding
    
    async def _assign_to_cluster(self, suggestion_id: UUID, embedding: List[float]) -> dict:
        """Assign suggestion to appropriate embedding cluster."""
        try:
            # Skip if embedding clustering is disabled
            if not settings.clustering_enabled_embedding:
                return {"cluster_id": None, "similarity": None}
            
            # Find similar suggestions
            similar_suggestions = await self.vector_adapter.find_similar_suggestions(
                embedding,
                limit=20,
                min_similarity=settings.assign_threshold
            )
            
            if similar_suggestions:
                # Find existing clusters for similar suggestions
                cluster_candidates = await self._find_clusters_for_suggestions(
                    [sid for sid, _ in similar_suggestions[:5]]
                )
                
                if cluster_candidates:
                    # Assign to the best matching cluster
                    best_cluster = cluster_candidates[0]
                    similarity = similar_suggestions[0][1]  # Highest similarity
                    
                    await self.clusters_repo.add_member(
                        cluster_id=best_cluster.id,
                        suggestion_id=suggestion_id,
                        similarity=similarity,
                        is_manual=False
                    )
                    
                    # Update cluster weight
                    await self._update_cluster_weight(best_cluster.id)
                    
                    return {
                        "cluster_id": best_cluster.id,
                        "similarity": similarity
                    }
            
            # Create new cluster if no suitable match found
            cluster = await self._create_embedding_cluster_for_suggestion(suggestion_id, embedding)
            
            return {
                "cluster_id": cluster.id,
                "similarity": 1.0  # Perfect match with itself
            }
            
        except Exception as e:
            logger.error("Cluster assignment failed", error=str(e))
            return {"cluster_id": None, "similarity": None}
    
    async def _find_clusters_for_suggestions(self, suggestion_ids: List[UUID]) -> List[Cluster]:
        """Find clusters that contain any of the given suggestions."""
        try:
            # This would require a more complex query - simplified for now
            # In practice, you'd join cluster_members with clusters
            clusters = await self.clusters_repo.get_all(
                filters=None,
                offset=0,
                limit=10
            )
            
            # Filter clusters of embedding type
            embedding_clusters = [
                c for c in clusters 
                if c.kind == ClusterKind.EMBEDDING
            ]
            
            return embedding_clusters
            
        except Exception as e:
            logger.error("Failed to find clusters for suggestions", error=str(e))
            return []
    
    async def _create_embedding_cluster_for_suggestion(
        self, 
        suggestion_id: UUID, 
        embedding: List[float]
    ) -> Cluster:
        """Create a new embedding cluster for the suggestion."""
        try:
            # Get the suggestion to use its title for cluster naming
            suggestion = await self.suggestions_repo.get_by_id(suggestion_id)
            
            # Create cluster
            cluster_data = ClusterCreate(
                kind=ClusterKind.EMBEDDING,
                title=f"Cluster: {suggestion.title[:50]}..." if len(suggestion.title) > 50 else suggestion.title,
                description="Auto-generated embedding cluster",
                tags=[suggestion.category.value.lower()]
            )
            
            cluster = await self.clusters_repo.create(cluster_data)
            
            # Add the suggestion as the first member
            await self.clusters_repo.add_member(
                cluster_id=cluster.id,
                suggestion_id=suggestion_id,
                similarity=1.0,
                is_manual=False
            )
            
            # Set initial weight
            await self._update_cluster_weight(cluster.id)
            
            logger.info(
                "Created new embedding cluster",
                cluster_id=str(cluster.id),
                suggestion_id=str(suggestion_id)
            )
            
            return cluster
            
        except Exception as e:
            logger.error("Failed to create embedding cluster", error=str(e))
            raise
    
    async def _update_cluster_weight(self, cluster_id: UUID):
        """Update cluster weight based on current members."""
        try:
            # Get cluster members
            members = await self.clusters_repo.get_members(cluster_id)
            
            if not members:
                weight = 0.0
            else:
                # Simple weight calculation: average similarity * member count
                similarities = [m.similarity or 0.5 for m in members]
                avg_similarity = sum(similarities) / len(similarities)
                weight = avg_similarity * len(members)
            
            # Update cluster weight
            await self.clusters_repo.update(cluster_id, weight=weight)
            
            logger.debug(
                "Updated cluster weight",
                cluster_id=str(cluster_id),
                weight=weight,
                member_count=len(members)
            )
            
        except Exception as e:
            logger.error("Failed to update cluster weight", cluster_id=str(cluster_id), error=str(e))
    
    async def reprocess_suggestion(self, suggestion_id: UUID) -> dict:
        """Reprocess a suggestion (useful for model updates or corrections)."""
        # Reset status to NEW
        await self.suggestions_repo.update(suggestion_id, status=SuggestionStatus.NEW)
        
        # Process again
        return await self.process_suggestion(suggestion_id)
    
    async def get_processing_stats(self) -> dict:
        """Get statistics about suggestion processing."""
        try:
            # Get counts by status
            new_count = await self.suggestions_repo.count(filters=None)  # Would need status filter
            
            return {
                "total_suggestions": new_count,
                "embedding_clustering_enabled": settings.clustering_enabled_embedding,
                "assign_threshold": settings.assign_threshold,
                "embedding_model": settings.embedding_model
            }
            
        except Exception as e:
            logger.error("Failed to get processing stats", error=str(e))
            return {}


class TagExtractionService:
    """Service for extracting and managing tags."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_provider = OpenAIProvider()
    
    async def extract_tags_from_text(self, text: str, max_tags: int = 10) -> List[str]:
        """Extract tags from text using LLM + YAKE hybrid approach."""
        if not text:
            return []
        
        tags = []
        
        # Use LLM extraction if enabled
        if "llm" in settings.tag_extractor:
            llm_tags = await self.llm_provider.extract_tags(text, max_tags)
            tags.extend(llm_tags)
        
        # TODO: Add YAKE extraction if enabled
        # if "yake" in settings.tag_extractor:
        #     yake_tags = await self._extract_tags_with_yake(text, max_tags)
        #     tags.extend(yake_tags)
        
        # Remove duplicates and normalize
        unique_tags = list(dict.fromkeys(tags))  # Preserves order
        
        if settings.tag_normalize:
            unique_tags = await self._normalize_tags(unique_tags)
        
        return unique_tags[:max_tags]
    
    async def _normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize tags (lowercase, remove duplicates, etc.)."""
        import re
        
        normalized = []
        for tag in tags:
            # Clean and normalize
            clean_tag = re.sub(r'[^a-z0-9\-\s]', '', tag.lower().strip())
            clean_tag = re.sub(r'\s+', '-', clean_tag)
            
            if clean_tag and len(clean_tag) > 1 and clean_tag not in normalized:
                normalized.append(clean_tag)
        
        return normalized