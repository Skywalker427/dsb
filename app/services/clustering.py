from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.clusters_repo import ClusterRepository
from app.adapters.repos.topics_repo import TopicRepository
from app.adapters.vector.pgvector_adapter import PgVectorAdapter
from app.core.config import get_settings
from app.core.logging import get_structured_logger
from app.domain.enums import ClusterKind, ClusterStatus
from app.domain.schemas import ClusterCreate

logger = get_structured_logger(__name__)
settings = get_settings()


class MultiViewClusteringService:
    """Service for orchestrating multi-view clustering strategies."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.clusters_repo = ClusterRepository(db)
        self.topics_repo = TopicRepository(db)
        self.vector_adapter = PgVectorAdapter(db)
    
    async def rebuild_tag_clusters(self) -> Dict[str, Any]:
        """Rebuild all TAG clusters based on current document tags."""
        if not settings.clustering_enabled_tag:
            return {"message": "Tag clustering disabled", "clusters_created": 0}
        
        try:
            logger.info("Starting tag cluster rebuild")
            
            # Get all tags with their document counts
            tag_supports = await self._get_tag_supports()
            
            # Filter tags that meet minimum support threshold
            eligible_tags = {
                tag: support for tag, support in tag_supports.items()
                if support >= settings.tag_min_docs
            }
            
            clusters_created = 0
            
            for tag, support in eligible_tags.items():
                try:
                    # Check if cluster already exists for this tag
                    existing_clusters = await self.clusters_repo.get_all(
                        filters=None,  # Would need tag filter
                        offset=0,
                        limit=1
                    )
                    
                    tag_cluster_exists = any(
                        c for c in existing_clusters 
                        if c.kind == ClusterKind.TAG and tag in (c.tags or [])
                    )
                    
                    if not tag_cluster_exists:
                        # Create new tag cluster
                        cluster_data = ClusterCreate(
                            kind=ClusterKind.TAG,
                            title=f"Tag: {tag}",
                            description=f"Documents tagged with '{tag}'",
                            tags=[tag]
                        )
                        
                        cluster = await self.clusters_repo.create(cluster_data)
                        
                        # Add documents with this tag as members
                        await self._add_tag_documents_to_cluster(cluster.id, tag)
                        
                        # Calculate and set cluster weight
                        weight = await self._calculate_tag_cluster_weight(cluster.id, support)
                        await self.clusters_repo.update(cluster.id, weight=weight)
                        
                        clusters_created += 1
                        
                        logger.info(
                            "Created tag cluster",
                            cluster_id=str(cluster.id),
                            tag=tag,
                            support=support
                        )
                
                except Exception as e:
                    logger.error(f"Failed to create cluster for tag '{tag}'", error=str(e))
                    continue
            
            result = {
                "clusters_created": clusters_created,
                "eligible_tags": len(eligible_tags),
                "tag_min_docs": settings.tag_min_docs
            }
            
            logger.info("Tag cluster rebuild completed", **result)
            return result
            
        except Exception as e:
            logger.error("Tag cluster rebuild failed", error=str(e))
            raise
    
    async def rebuild_topic_clusters(self) -> Dict[str, Any]:
        """Rebuild all TOPIC clusters based on current topics."""
        if not settings.clustering_enabled_topic:
            return {"message": "Topic clustering disabled", "clusters_created": 0}
        
        try:
            logger.info("Starting topic cluster rebuild")
            
            # Get all topics with their document counts
            topics = await self.topics_repo.get_all(
                min_support=settings.topic_min_docs,
                offset=0,
                limit=1000
            )
            
            clusters_created = 0
            
            for topic in topics:
                try:
                    # Check if cluster already exists for this topic
                    existing_clusters = await self.clusters_repo.get_all(
                        filters=None,  # Would need topic filter
                        offset=0,
                        limit=1
                    )
                    
                    topic_cluster_exists = any(
                        c for c in existing_clusters
                        if c.kind == ClusterKind.TOPIC and c.primary_topic_id == topic.id
                    )
                    
                    if not topic_cluster_exists:
                        # Create new topic cluster
                        cluster_data = ClusterCreate(
                            kind=ClusterKind.TOPIC,
                            title=f"Topic: {topic.label}",
                            description=topic.description or f"Documents about {topic.label}",
                            primary_topic_id=topic.id,
                            tags=[topic.label.lower().replace(' ', '-')]
                        )
                        
                        cluster = await self.clusters_repo.create(cluster_data)
                        
                        # Add documents with this topic as members
                        await self._add_topic_documents_to_cluster(cluster.id, topic.id)
                        
                        # Calculate and set cluster weight
                        support = await self.topics_repo.get_support_count(topic.id)
                        weight = await self._calculate_topic_cluster_weight(cluster.id, support)
                        await self.clusters_repo.update(cluster.id, weight=weight)
                        
                        clusters_created += 1
                        
                        logger.info(
                            "Created topic cluster",
                            cluster_id=str(cluster.id),
                            topic=topic.label,
                            support=support
                        )
                
                except Exception as e:
                    logger.error(f"Failed to create cluster for topic '{topic.label}'", error=str(e))
                    continue
            
            result = {
                "clusters_created": clusters_created,
                "eligible_topics": len(topics),
                "topic_min_docs": settings.topic_min_docs
            }
            
            logger.info("Topic cluster rebuild completed", **result)
            return result
            
        except Exception as e:
            logger.error("Topic cluster rebuild failed", error=str(e))
            raise
    
    async def create_fusion_clusters(self) -> Dict[str, Any]:
        """Create FUSION clusters using hybrid similarity."""
        if not settings.clustering_enabled_fusion:
            return {"message": "Fusion clustering disabled", "clusters_created": 0}
        
        try:
            logger.info("Starting fusion clustering")
            
            # Get all documents with embeddings, tags, and topics
            # This is a simplified version - would need complex queries
            
            # For now, create a simple fusion cluster based on co-occurrence
            fusion_weights = settings.fusion_weights_dict
            
            # TODO: Implement actual fusion clustering algorithm
            # This would involve:
            # 1. Get documents with embeddings, tags, and topics
            # 2. Calculate pairwise similarities using fusion formula
            # 3. Apply clustering algorithm (e.g., agglomerative)
            # 4. Create FUSION clusters
            
            clusters_created = 0
            
            result = {
                "clusters_created": clusters_created,
                "fusion_weights": fusion_weights,
                "message": "Fusion clustering implementation needed"
            }
            
            logger.info("Fusion clustering completed", **result)
            return result
            
        except Exception as e:
            logger.error("Fusion clustering failed", error=str(e))
            raise
    
    async def _get_tag_supports(self) -> Dict[str, int]:
        """Get support counts for all tags across documents."""
        try:
            # This would require complex query to count documents per tag
            # Simplified for now
            return {}
        except Exception as e:
            logger.error("Failed to get tag supports", error=str(e))
            return {}
    
    async def _add_tag_documents_to_cluster(self, cluster_id: UUID, tag: str):
        """Add all documents with a specific tag to the cluster."""
        try:
            # This would require querying documents by tag and adding as members
            # Implementation depends on document-tag relationship structure
            pass
        except Exception as e:
            logger.error("Failed to add tag documents to cluster", error=str(e))
    
    async def _add_topic_documents_to_cluster(self, cluster_id: UUID, topic_id: UUID):
        """Add all documents with a specific topic to the cluster."""
        try:
            # This would require querying documents by topic and adding as members
            # Implementation depends on document-topic relationship structure
            pass
        except Exception as e:
            logger.error("Failed to add topic documents to cluster", error=str(e))
    
    async def _calculate_tag_cluster_weight(self, cluster_id: UUID, support: int) -> float:
        """Calculate weight for a tag cluster."""
        # Simple weight based on support count and tag factor
        tag_weight = settings.fusion_weights_dict.get("tag", 0.2)
        return float(support) * tag_weight * settings.fusion_weights_dict.get("tag", 0.7)
    
    async def _calculate_topic_cluster_weight(self, cluster_id: UUID, support: int) -> float:
        """Calculate weight for a topic cluster."""
        # Simple weight based on support count and topic factor  
        topic_weight = settings.fusion_weights_dict.get("topic", 0.2)
        return float(support) * topic_weight * settings.fusion_weights_dict.get("topic", 0.9)
    
    async def get_cluster_insights(self, cluster_id: UUID) -> Dict[str, Any]:
        """Get insights and analytics for a cluster."""
        try:
            cluster = await self.clusters_repo.get_by_id(cluster_id)
            if not cluster:
                return {"error": "Cluster not found"}
            
            members = await self.clusters_repo.get_members(cluster_id)
            
            insights = {
                "cluster_id": str(cluster_id),
                "kind": cluster.kind.value,
                "title": cluster.title,
                "member_count": len(members),
                "weight": cluster.weight,
                "status": cluster.status.value,
                "created_at": cluster.created_at.isoformat(),
                "updated_at": cluster.updated_at.isoformat()
            }
            
            if cluster.kind == ClusterKind.EMBEDDING:
                # Add embedding-specific insights
                similarities = [m.similarity for m in members if m.similarity]
                if similarities:
                    insights["avg_similarity"] = sum(similarities) / len(similarities)
                    insights["min_similarity"] = min(similarities)
                    insights["max_similarity"] = max(similarities)
            
            elif cluster.kind == ClusterKind.TAG:
                # Add tag-specific insights
                insights["tags"] = cluster.tags
                insights["tag_coverage"] = len(cluster.tags or [])
            
            elif cluster.kind == ClusterKind.TOPIC:
                # Add topic-specific insights
                if cluster.primary_topic_id:
                    topic = await self.topics_repo.get_by_id(cluster.primary_topic_id)
                    if topic:
                        insights["primary_topic"] = {
                            "id": str(topic.id),
                            "label": topic.label,
                            "description": topic.description
                        }
            
            elif cluster.kind == ClusterKind.FUSION:
                # Add fusion-specific insights
                insights["fusion_params"] = cluster.fusion_params
            
            return insights
            
        except Exception as e:
            logger.error("Failed to get cluster insights", cluster_id=str(cluster_id), error=str(e))
            return {"error": "Failed to get insights"}
    
    async def merge_clusters(self, source_cluster_ids: List[UUID], target_cluster_id: UUID) -> Dict[str, Any]:
        """Merge multiple clusters into a target cluster."""
        try:
            logger.info(
                "Starting cluster merge",
                source_clusters=len(source_cluster_ids),
                target_cluster=str(target_cluster_id)
            )
            
            # Get target cluster
            target_cluster = await self.clusters_repo.get_by_id(target_cluster_id)
            if not target_cluster:
                raise ValueError("Target cluster not found")
            
            members_moved = 0
            
            for source_id in source_cluster_ids:
                if source_id == target_cluster_id:
                    continue  # Skip self-merge
                
                # Get source cluster members
                source_members = await self.clusters_repo.get_members(source_id)
                
                # Move members to target cluster
                for member in source_members:
                    try:
                        await self.clusters_repo.add_member(
                            cluster_id=target_cluster_id,
                            document_id=member.document_id,
                            suggestion_id=member.suggestion_id,
                            similarity=member.similarity,
                            is_manual=True  # Mark as manual merge
                        )
                        members_moved += 1
                    except Exception as e:
                        logger.warning("Failed to move cluster member", error=str(e))
                        continue
                
                # Delete source cluster
                await self.clusters_repo.delete(source_id)
            
            # Recalculate target cluster weight
            target_members = await self.clusters_repo.get_members(target_cluster_id)
            new_weight = len(target_members) * 1.5  # Simple recalculation
            await self.clusters_repo.update(target_cluster_id, weight=new_weight)
            
            result = {
                "target_cluster_id": str(target_cluster_id),
                "source_clusters_merged": len(source_cluster_ids),
                "members_moved": members_moved,
                "new_weight": new_weight
            }
            
            logger.info("Cluster merge completed", **result)
            return result
            
        except Exception as e:
            logger.error("Cluster merge failed", error=str(e))
            raise


class ClusterAnalyticsService:
    """Service for cluster analytics and insights."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.clusters_repo = ClusterRepository(db)
    
    async def get_clustering_overview(self) -> Dict[str, Any]:
        """Get overview of clustering system."""
        try:
            # Get counts by cluster kind
            all_clusters = await self.clusters_repo.get_all(offset=0, limit=10000)
            
            kind_counts = defaultdict(int)
            status_counts = defaultdict(int)
            total_weight = 0.0
            
            for cluster in all_clusters:
                kind_counts[cluster.kind.value] += 1
                status_counts[cluster.status.value] += 1
                total_weight += cluster.weight
            
            overview = {
                "total_clusters": len(all_clusters),
                "by_kind": dict(kind_counts),
                "by_status": dict(status_counts),
                "total_weight": total_weight,
                "avg_weight": total_weight / len(all_clusters) if all_clusters else 0,
                "clustering_enabled": {
                    "embedding": settings.clustering_enabled_embedding,
                    "tag": settings.clustering_enabled_tag,
                    "topic": settings.clustering_enabled_topic,
                    "fusion": settings.clustering_enabled_fusion
                },
                "thresholds": {
                    "assign_threshold": settings.assign_threshold,
                    "tag_min_docs": settings.tag_min_docs,
                    "topic_min_docs": settings.topic_min_docs
                }
            }
            
            return overview
            
        except Exception as e:
            logger.error("Failed to get clustering overview", error=str(e))
            return {"error": "Failed to get overview"}
    
    async def get_top_clusters(self, limit: int = 10, kind: Optional[ClusterKind] = None) -> List[Dict[str, Any]]:
        """Get top clusters by weight."""
        try:
            filters = None
            if kind:
                # Would need to implement kind filtering in repo
                pass
            
            clusters = await self.clusters_repo.get_all(
                filters=filters,
                offset=0,
                limit=limit
            )
            
            # Sort by weight (already done in repo, but ensure it)
            sorted_clusters = sorted(clusters, key=lambda c: c.weight, reverse=True)
            
            result = []
            for cluster in sorted_clusters:
                members = await self.clusters_repo.get_members(cluster.id)
                
                result.append({
                    "id": str(cluster.id),
                    "kind": cluster.kind.value,
                    "title": cluster.title,
                    "weight": cluster.weight,
                    "member_count": len(members),
                    "status": cluster.status.value,
                    "tags": cluster.tags,
                    "created_at": cluster.created_at.isoformat()
                })
            
            return result
            
        except Exception as e:
            logger.error("Failed to get top clusters", error=str(e))
            return []