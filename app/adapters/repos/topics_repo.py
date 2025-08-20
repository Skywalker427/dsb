from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.domain.models import Topic, TopicAlias, DocumentTopic
from app.domain.schemas import TopicCreate


class TopicRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, topic_data: TopicCreate) -> Topic:
        """Create a new topic."""
        topic = Topic(
            label=topic_data.label,
            description=topic_data.description,
        )
        
        self.db.add(topic)
        await self.db.commit()
        await self.db.refresh(topic)
        return topic

    async def get_by_id(self, topic_id: UUID) -> Optional[Topic]:
        """Get topic by ID."""
        result = await self.db.execute(
            select(Topic).where(Topic.id == topic_id)
        )
        return result.scalar_one_or_none()

    async def get_by_label(self, label: str) -> Optional[Topic]:
        """Get topic by exact label match."""
        result = await self.db.execute(
            select(Topic).where(Topic.label == label)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        query: Optional[str] = None,
        min_support: Optional[int] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Topic]:
        """Get all topics with optional filters."""
        db_query = select(Topic)
        
        if query:
            db_query = db_query.where(Topic.label.ilike(f"%{query}%"))
            
        if min_support is not None:
            # Join with document_topics to filter by support count
            support_subquery = (
                select(DocumentTopic.topic_id, func.count().label("support_count"))
                .group_by(DocumentTopic.topic_id)
                .having(func.count() >= min_support)
                .subquery()
            )
            db_query = db_query.join(support_subquery, Topic.id == support_subquery.c.topic_id)
        
        db_query = db_query.offset(offset).limit(limit).order_by(Topic.label)
        
        result = await self.db.execute(db_query)
        return result.scalars().all()

    async def update(self, topic_id: UUID, **kwargs) -> Optional[Topic]:
        """Update a topic."""
        result = await self.db.execute(
            select(Topic).where(Topic.id == topic_id)
        )
        topic = result.scalar_one_or_none()
        
        if not topic:
            return None
            
        for key, value in kwargs.items():
            if hasattr(topic, key):
                setattr(topic, key, value)
                
        await self.db.commit()
        await self.db.refresh(topic)
        return topic

    async def delete(self, topic_id: UUID) -> bool:
        """Delete a topic and its aliases."""
        # First delete topic aliases
        await self.db.execute(
            select(TopicAlias).where(TopicAlias.topic_id == topic_id)
        )
        
        # Then delete the topic
        result = await self.db.execute(
            select(Topic).where(Topic.id == topic_id)
        )
        topic = result.scalar_one_or_none()
        
        if not topic:
            return False
            
        await self.db.delete(topic)
        await self.db.commit()
        return True

    async def add_alias(self, topic_id: UUID, alias: str) -> TopicAlias:
        """Add an alias to a topic."""
        topic_alias = TopicAlias(
            topic_id=topic_id,
            alias=alias,
        )
        
        self.db.add(topic_alias)
        await self.db.commit()
        await self.db.refresh(topic_alias)
        return topic_alias

    async def get_aliases(self, topic_id: UUID) -> List[TopicAlias]:
        """Get all aliases for a topic."""
        result = await self.db.execute(
            select(TopicAlias).where(TopicAlias.topic_id == topic_id)
        )
        return result.scalars().all()

    async def find_similar_topics(self, label: str, threshold: float = 0.8) -> List[Topic]:
        """Find topics similar to the given label.
        
        This is a placeholder implementation. In a real system, this would use
        vector similarity search with embeddings.
        """
        # For now, use simple text matching
        result = await self.db.execute(
            select(Topic).where(Topic.label.ilike(f"%{label}%"))
        )
        return result.scalars().all()

    async def get_support_count(self, topic_id: UUID) -> int:
        """Get the support count (number of documents) for a topic."""
        result = await self.db.execute(
            select(func.count()).where(DocumentTopic.topic_id == topic_id)
        )
        return result.scalar() or 0

    async def merge_topics(self, source_topic_ids: List[UUID], target_label: str) -> Topic:
        """Merge multiple topics into a new target topic."""
        # Create or get the target topic
        target_topic = await self.get_by_label(target_label)
        if not target_topic:
            target_topic = await self.create(TopicCreate(label=target_label))

        # Move all document associations to the target topic
        for source_id in source_topic_ids:
            # Get all document associations for this source topic
            result = await self.db.execute(
                select(DocumentTopic).where(DocumentTopic.topic_id == source_id)
            )
            doc_topics = result.scalars().all()
            
            # Update them to point to the target topic
            for doc_topic in doc_topics:
                doc_topic.topic_id = target_topic.id
            
            # Delete the source topic
            await self.delete(source_id)

        await self.db.commit()
        return target_topic

    async def count(self, query: Optional[str] = None, min_support: Optional[int] = None) -> int:
        """Count topics with optional filters."""
        db_query = select(func.count(Topic.id))
        
        if query:
            db_query = db_query.where(Topic.label.ilike(f"%{query}%"))
            
        if min_support is not None:
            support_subquery = (
                select(DocumentTopic.topic_id)
                .group_by(DocumentTopic.topic_id)
                .having(func.count() >= min_support)
                .subquery()
            )
            db_query = db_query.where(Topic.id.in_(select(support_subquery.c.topic_id)))
        
        result = await self.db.execute(db_query)
        return result.scalar()