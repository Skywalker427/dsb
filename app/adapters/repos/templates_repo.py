from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, func

from app.domain.models import Template
from app.domain.schemas import TemplateCreate


class TemplateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, template_data: TemplateCreate) -> Template:
        """Create a new template."""
        template = Template(
            name=template_data.name,
            description=template_data.description,
            version=template_data.version,
            kind=template_data.kind,
            engine=template_data.engine,
            content_markdown=template_data.content_markdown,
        )
        
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def get_by_id(self, template_id: UUID) -> Optional[Template]:
        """Get template by ID."""
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Template]:
        """Get template by name."""
        result = await self.db.execute(
            select(Template).where(Template.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        kind: Optional[str] = None,
        active_only: bool = True,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Template]:
        """Get all templates with optional filters."""
        query = select(Template)
        
        filters = []
        
        if active_only:
            filters.append(Template.active == True)
        
        if kind:
            filters.append(Template.kind == kind)
            
        if search:
            search_filter = or_(
                Template.name.ilike(f"%{search}%"),
                Template.description.ilike(f"%{search}%")
            )
            filters.append(search_filter)
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(Template.updated_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count(
        self,
        kind: Optional[str] = None,
        active_only: bool = True,
        search: Optional[str] = None,
    ) -> int:
        """Count templates with optional filters."""
        query = select(func.count(Template.id))
        
        filters = []
        
        if active_only:
            filters.append(Template.active == True)
        
        if kind:
            filters.append(Template.kind == kind)
            
        if search:
            search_filter = or_(
                Template.name.ilike(f"%{search}%"),
                Template.description.ilike(f"%{search}%")
            )
            filters.append(search_filter)
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update(self, template_id: UUID, **updates) -> Optional[Template]:
        """Update a template."""
        template = await self.get_by_id(template_id)
        if not template:
            return None
        
        for field, value in updates.items():
            if hasattr(template, field):
                setattr(template, field, value)
        
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def delete(self, template_id: UUID) -> bool:
        """Delete a template (soft delete by setting active=False)."""
        template = await self.get_by_id(template_id)
        if not template:
            return False
        
        template.active = False
        await self.db.commit()
        return True

    async def hard_delete(self, template_id: UUID) -> bool:
        """Permanently delete a template."""
        template = await self.get_by_id(template_id)
        if not template:
            return False
        
        await self.db.delete(template)
        await self.db.commit()
        return True

    async def get_kinds(self) -> List[str]:
        """Get all unique template kinds."""
        result = await self.db.execute(
            select(Template.kind).distinct().where(Template.active == True)
        )
        return [kind for kind in result.scalars().all() if kind]