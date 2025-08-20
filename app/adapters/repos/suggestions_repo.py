from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.adapters.repos.base import Base
from app.domain.models import Suggestion
from app.domain.schemas import SuggestionCreate, SuggestionFilters


class SuggestionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, suggestion_data: SuggestionCreate) -> Suggestion:
        """Create a new suggestion."""
        suggestion = Suggestion(
            author_type=suggestion_data.author_type,
            category=suggestion_data.category,
            title=suggestion_data.title,
            body=suggestion_data.body,
            contact=suggestion_data.contact.dict(exclude_unset=True),
            attachments=suggestion_data.attachments or [],
        )
        
        self.db.add(suggestion)
        await self.db.commit()
        await self.db.refresh(suggestion)
        return suggestion

    async def get_by_id(self, suggestion_id: UUID) -> Optional[Suggestion]:
        """Get suggestion by ID."""
        result = await self.db.execute(
            select(Suggestion).where(Suggestion.id == suggestion_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        filters: Optional[SuggestionFilters] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Suggestion]:
        """Get all suggestions with optional filters."""
        query = select(Suggestion)
        
        if filters:
            if filters.author_type:
                query = query.where(Suggestion.author_type == filters.author_type)
            if filters.category:
                query = query.where(Suggestion.category == filters.category)
            if filters.status:
                query = query.where(Suggestion.status == filters.status)
            if filters.language:
                query = query.where(Suggestion.language == filters.language)
            if filters.tag:
                query = query.where(Suggestion.tags.any(filters.tag))
            if filters.created_after:
                query = query.where(Suggestion.created_at >= filters.created_after)
            if filters.created_before:
                query = query.where(Suggestion.created_at <= filters.created_before)
        
        query = query.offset(offset).limit(limit).order_by(Suggestion.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update(self, suggestion_id: UUID, **kwargs) -> Optional[Suggestion]:
        """Update a suggestion."""
        result = await self.db.execute(
            select(Suggestion).where(Suggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()
        
        if not suggestion:
            return None
            
        for key, value in kwargs.items():
            if hasattr(suggestion, key):
                setattr(suggestion, key, value)
                
        await self.db.commit()
        await self.db.refresh(suggestion)
        return suggestion

    async def delete(self, suggestion_id: UUID) -> bool:
        """Delete a suggestion."""
        result = await self.db.execute(
            select(Suggestion).where(Suggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()
        
        if not suggestion:
            return False
            
        await self.db.delete(suggestion)
        await self.db.commit()
        return True

    async def count(self, filters: Optional[SuggestionFilters] = None) -> int:
        """Count suggestions with optional filters."""
        from sqlalchemy import func
        
        query = select(func.count(Suggestion.id))
        
        if filters:
            if filters.author_type:
                query = query.where(Suggestion.author_type == filters.author_type)
            if filters.category:
                query = query.where(Suggestion.category == filters.category)
            if filters.status:
                query = query.where(Suggestion.status == filters.status)
            if filters.language:
                query = query.where(Suggestion.language == filters.language)
            if filters.tag:
                query = query.where(Suggestion.tags.any(filters.tag))
            if filters.created_after:
                query = query.where(Suggestion.created_at >= filters.created_after)
            if filters.created_before:
                query = query.where(Suggestion.created_at <= filters.created_before)
        
        result = await self.db.execute(query)
        return result.scalar()