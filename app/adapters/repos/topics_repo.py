from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.domain.models import Topic, TopicAlias, DocumentTopic, SuggestionTopic, Suggestion
from app.domain.schemas import TopicCreate
from app.adapters.vector.pgvector_adapter import PgVectorAdapter


class TopicRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.vector_adapter = PgVectorAdapter(db)

    async def create(self, topic_data: TopicCreate, embedding: Optional[List[float]] = None) -> Topic:
        """Create a new topic."""
        topic = Topic(
            label=topic_data.label,
            description=topic_data.description,
        )
        
        self.db.add(topic)
        await self.db.commit()
        await self.db.refresh(topic)
        
        # Store embedding if provided
        if embedding:
            await self.vector_adapter.store_topic_embedding(topic.id, embedding)
        
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

    async def find_similar_topics(
        self, 
        embedding: List[float], 
        threshold: float = 0.8,
        limit: int = 5
    ) -> List[Tuple[Topic, float]]:
        """Find topics similar to the given embedding using vector similarity."""
        try:
            # Use vector adapter to find similar topics
            similar_topic_data = await self.vector_adapter.find_similar_topics(
                embedding=embedding,
                min_similarity=threshold,
                limit=limit
            )
            
            # Fetch full Topic objects for the similar topics
            result = []
            for topic_id, label, similarity in similar_topic_data:
                topic = await self.get_by_id(topic_id)
                if topic:
                    result.append((topic, similarity))
            
            return result
        except Exception as e:
            # Fallback to empty list if vector search fails
            return []

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

    async def add_suggestion_topic_association(
        self, 
        suggestion_id: UUID, 
        topic_id: UUID, 
        confidence: float = 0.5
    ) -> SuggestionTopic:
        """Create an association between a suggestion and a topic."""
        suggestion_topic = SuggestionTopic(
            suggestion_id=suggestion_id,
            topic_id=topic_id,
            confidence=confidence
        )
        
        self.db.add(suggestion_topic)
        await self.db.commit()
        await self.db.refresh(suggestion_topic)
        return suggestion_topic

    async def get_suggestions_by_topic(
        self, 
        topic_id: UUID,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> List[Tuple[Suggestion, float]]:
        """Get all suggestions associated with a topic."""
        result = await self.db.execute(
            select(Suggestion, SuggestionTopic.confidence)
            .join(SuggestionTopic, Suggestion.id == SuggestionTopic.suggestion_id)
            .where(SuggestionTopic.topic_id == topic_id)
            .where(SuggestionTopic.confidence >= min_confidence)
            .order_by(SuggestionTopic.confidence.desc())
            .limit(limit)
        )
        return result.all()

    async def get_topics_by_suggestion(
        self, 
        suggestion_id: UUID,
        min_confidence: float = 0.0
    ) -> List[Tuple[Topic, float]]:
        """Get all topics associated with a suggestion."""
        result = await self.db.execute(
            select(Topic, SuggestionTopic.confidence)
            .join(SuggestionTopic, Topic.id == SuggestionTopic.topic_id)
            .where(SuggestionTopic.suggestion_id == suggestion_id)
            .where(SuggestionTopic.confidence >= min_confidence)
            .order_by(SuggestionTopic.confidence.desc())
        )
        return result.all()

    async def remove_suggestion_topic_association(
        self, 
        suggestion_id: UUID, 
        topic_id: UUID
    ) -> bool:
        """Remove an association between a suggestion and a topic."""
        result = await self.db.execute(
            select(SuggestionTopic)
            .where(SuggestionTopic.suggestion_id == suggestion_id)
            .where(SuggestionTopic.topic_id == topic_id)
        )
        suggestion_topic = result.scalar_one_or_none()
        
        if not suggestion_topic:
            return False
            
        await self.db.delete(suggestion_topic)
        await self.db.commit()
        return True