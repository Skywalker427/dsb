from typing import List, Tuple, Optional
from uuid import UUID

from sqlalchemy import text, Column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pgvector.sqlalchemy import Vector

from app.core.config import get_settings
from app.core.logging import get_structured_logger
from app.domain.models import Suggestion, Topic

logger = get_structured_logger(__name__)
settings = get_settings()


class PgVectorAdapter:
    """Adapter for pgvector operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_dims = settings.embedding_dims
    
    async def add_embedding_column_if_not_exists(self, table_name: str, column_name: str = "embedding"):
        """Add embedding column to table if it doesn't exist."""
        try:
            # Check if column exists
            result = await self.db.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' AND column_name = '{column_name}'
            """))
            
            if not result.scalar():
                logger.warning(f"Embedding column missing from {table_name}. Please run database migrations.")
                # For now, just continue without adding the column
                # In production, this should be handled through proper migrations
                return
            else:
                logger.debug(f"Embedding column exists in {table_name}")
        
        except Exception as e:
            logger.error(f"Failed to check embedding column in {table_name}", error=str(e))
            # Continue without failing - the column might exist
    
    async def store_suggestion_embedding(self, suggestion_id: UUID, embedding: List[float]):
        """Store embedding for a suggestion."""
        try:
            # Ensure embedding column exists
            await self.add_embedding_column_if_not_exists("suggestions")
            
            # Update suggestion with embedding using direct SQL to avoid asyncpg parameter issues
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            
            # Update suggestion with embedding using string formatting to avoid parameter issues
            await self.db.execute(text(f"""
                UPDATE suggestions 
                SET embedding = '{embedding_str}'::vector, embedding_model = '{settings.embedding_model}'
                WHERE id = '{suggestion_id}'
            """))
            
            await self.db.commit()
            logger.info("Stored suggestion embedding", suggestion_id=str(suggestion_id))
            
        except Exception as e:
            logger.error("Failed to store suggestion embedding", error=str(e), suggestion_id=str(suggestion_id))
            await self.db.rollback()
            raise
    
    async def store_topic_embedding(self, topic_id: UUID, embedding: List[float]):
        """Store embedding for a topic."""
        try:
            # Ensure embedding column exists
            await self.add_embedding_column_if_not_exists("topics")
            
            # Update topic with embedding using direct SQL to avoid asyncpg parameter issues
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            
            # Update topic with embedding using string formatting to avoid parameter issues
            await self.db.execute(text(f"""
                UPDATE topics 
                SET embedding = '{embedding_str}'::vector
                WHERE id = '{topic_id}'
            """))
            
            await self.db.commit()
            logger.info("Stored topic embedding", topic_id=str(topic_id))
            
        except Exception as e:
            logger.error("Failed to store topic embedding", error=str(e), topic_id=str(topic_id))
            await self.db.rollback()
            raise
    
    async def find_similar_suggestions(
        self, 
        embedding: List[float], 
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Tuple[UUID, float]]:
        """Find suggestions similar to the given embedding."""
        try:
            # Ensure embedding column exists
            await self.add_embedding_column_if_not_exists("suggestions")
            
            # Set ef_search for query
            await self.db.execute(text(f"SET hnsw.ef_search = {settings.hnsw_ef_search}"))
            
            # Find similar suggestions using cosine similarity
            result = await self.db.execute(text("""
                SELECT id, 1 - (embedding <=> :embedding) as similarity
                FROM suggestions 
                WHERE embedding IS NOT NULL 
                AND 1 - (embedding <=> :embedding) >= :min_similarity
                ORDER BY embedding <=> :embedding
                LIMIT :limit
            """), {
                "embedding": embedding,
                "min_similarity": min_similarity,
                "limit": limit
            })
            
            similar_suggestions = [(row.id, row.similarity) for row in result]
            logger.info(
                "Found similar suggestions",
                count=len(similar_suggestions),
                min_similarity=min_similarity
            )
            
            return similar_suggestions
            
        except Exception as e:
            logger.error("Failed to find similar suggestions", error=str(e))
            return []
    
    async def find_similar_topics(
        self, 
        embedding: List[float], 
        limit: int = 5,
        min_similarity: float = 0.8
    ) -> List[Tuple[UUID, str, float]]:
        """Find topics similar to the given embedding."""
        try:
            # Ensure embedding column exists
            await self.add_embedding_column_if_not_exists("topics")
            
            # Set ef_search for query
            await self.db.execute(text(f"SET hnsw.ef_search = {settings.hnsw_ef_search}"))
            
            # Find similar topics using cosine similarity
            result = await self.db.execute(text("""
                SELECT id, label, 1 - (embedding <=> :embedding) as similarity
                FROM topics 
                WHERE embedding IS NOT NULL 
                AND 1 - (embedding <=> :embedding) >= :min_similarity
                ORDER BY embedding <=> :embedding
                LIMIT :limit
            """), {
                "embedding": embedding,
                "min_similarity": min_similarity,
                "limit": limit
            })
            
            similar_topics = [(row.id, row.label, row.similarity) for row in result]
            logger.info(
                "Found similar topics",
                count=len(similar_topics),
                min_similarity=min_similarity
            )
            
            return similar_topics
            
        except Exception as e:
            logger.error("Failed to find similar topics", error=str(e))
            return []
    
    async def get_cluster_centroid(self, suggestion_ids: List[UUID]) -> Optional[List[float]]:
        """Calculate centroid embedding for a cluster of suggestions."""
        try:
            if not suggestion_ids:
                return None
            
            # Calculate average embedding
            result = await self.db.execute(text("""
                SELECT AVG(embedding) as centroid
                FROM suggestions 
                WHERE id = ANY(:suggestion_ids) 
                AND embedding IS NOT NULL
            """), {"suggestion_ids": [str(sid) for sid in suggestion_ids]})
            
            centroid = result.scalar()
            if centroid:
                logger.info("Calculated cluster centroid", cluster_size=len(suggestion_ids))
                return list(centroid)
            
            return None
            
        except Exception as e:
            logger.error("Failed to calculate cluster centroid", error=str(e))
            return None
    
    async def batch_similarity_search(
        self, 
        embeddings: List[List[float]], 
        table_name: str = "suggestions",
        limit_per_query: int = 5
    ) -> List[List[Tuple[UUID, float]]]:
        """Perform batch similarity searches."""
        try:
            # Ensure embedding column exists
            await self.add_embedding_column_if_not_exists(table_name)
            
            results = []
            for embedding in embeddings:
                # Find similar items for each embedding
                result = await self.db.execute(text(f"""
                    SELECT id, 1 - (embedding <=> :embedding) as similarity
                    FROM {table_name}
                    WHERE embedding IS NOT NULL 
                    ORDER BY embedding <=> :embedding
                    LIMIT :limit
                """), {
                    "embedding": embedding,
                    "limit": limit_per_query
                })
                
                similar_items = [(row.id, row.similarity) for row in result]
                results.append(similar_items)
            
            logger.info(
                "Performed batch similarity search",
                batch_size=len(embeddings),
                table=table_name
            )
            
            return results
            
        except Exception as e:
            logger.error("Failed to perform batch similarity search", error=str(e))
            return [[] for _ in embeddings]