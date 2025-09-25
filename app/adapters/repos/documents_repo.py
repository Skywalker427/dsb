from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, func, text

from app.domain.models import (
    Document, DocumentVersion, DocumentCluster, DocumentTopic, DocumentTag,
    Cluster, Topic, Tag
)
from app.domain.enums import DocStatus, DocFormat


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, document_data: Dict[str, Any]) -> Document:
        """Create a new document."""
        document = Document(
            title=document_data.get("title"),
            template_id=document_data["template_id"],
            status=document_data.get("status", DocStatus.DRAFT),
            rendered_format=document_data.get("rendered_format"),
            rendered_url=document_data.get("rendered_url"),
            draft_content=document_data.get("draft_content"),
            created_by=document_data.get("created_by"),
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def get_by_id(self, document_id: UUID) -> Optional[Document]:
        """Get document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        status: Optional[DocStatus] = None,
        template_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Document]:
        """Get all documents with optional filters."""
        query = select(Document)
        
        filters = []
        
        if status:
            filters.append(Document.status == status)
        
        if template_id:
            filters.append(Document.template_id == template_id)
        
        if created_by:
            filters.append(Document.created_by == created_by)
            
        if search:
            search_filter = or_(
                Document.title.ilike(f"%{search}%"),
                Document.draft_content['markdown'].astext.ilike(f"%{search}%")
            )
            filters.append(search_filter)
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(Document.updated_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count(
        self,
        status: Optional[DocStatus] = None,
        template_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count documents with optional filters."""
        query = select(func.count(Document.id))
        
        filters = []
        
        if status:
            filters.append(Document.status == status)
        
        if template_id:
            filters.append(Document.template_id == template_id)
        
        if created_by:
            filters.append(Document.created_by == created_by)
            
        if search:
            search_filter = or_(
                Document.title.ilike(f"%{search}%"),
                Document.draft_content['markdown'].astext.ilike(f"%{search}%")
            )
            filters.append(search_filter)
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update(self, document_id: UUID, **updates) -> Optional[Document]:
        """Update a document."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        
        for field, value in updates.items():
            if hasattr(document, field):
                setattr(document, field, value)
        
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def delete(self, document_id: UUID) -> bool:
        """Delete a document."""
        document = await self.get_by_id(document_id)
        if not document:
            return False
        
        await self.db.delete(document)
        await self.db.commit()
        return True

    # Relationship management methods

    async def add_cluster_association(
        self, 
        document_id: UUID, 
        cluster_id: UUID, 
        contribution_weight: float = 1.0
    ) -> bool:
        """Add association between document and cluster."""
        association = DocumentCluster(
            document_id=document_id,
            cluster_id=cluster_id,
            contribution_weight=contribution_weight
        )
        
        self.db.add(association)
        try:
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False

    async def remove_cluster_association(self, document_id: UUID, cluster_id: UUID) -> bool:
        """Remove association between document and cluster."""
        result = await self.db.execute(
            select(DocumentCluster).where(
                and_(
                    DocumentCluster.document_id == document_id,
                    DocumentCluster.cluster_id == cluster_id
                )
            )
        )
        association = result.scalar_one_or_none()
        
        if not association:
            return False
        
        await self.db.delete(association)
        await self.db.commit()
        return True

    async def add_topic_association(
        self, 
        document_id: UUID, 
        topic_id: UUID, 
        confidence: float = 1.0
    ) -> bool:
        """Add association between document and topic."""
        association = DocumentTopic(
            document_id=document_id,
            topic_id=topic_id,
            confidence=confidence
        )
        
        self.db.add(association)
        try:
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False

    async def remove_topic_association(self, document_id: UUID, topic_id: UUID) -> bool:
        """Remove association between document and topic."""
        result = await self.db.execute(
            select(DocumentTopic).where(
                and_(
                    DocumentTopic.document_id == document_id,
                    DocumentTopic.topic_id == topic_id
                )
            )
        )
        association = result.scalar_one_or_none()
        
        if not association:
            return False
        
        await self.db.delete(association)
        await self.db.commit()
        return True

    async def add_tag_association(self, document_id: UUID, tag_id: UUID) -> bool:
        """Add association between document and tag."""
        association = DocumentTag(
            document_id=document_id,
            tag_id=tag_id
        )
        
        self.db.add(association)
        try:
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False

    async def remove_tag_association(self, document_id: UUID, tag_id: UUID) -> bool:
        """Remove association between document and tag."""
        result = await self.db.execute(
            select(DocumentTag).where(
                and_(
                    DocumentTag.document_id == document_id,
                    DocumentTag.tag_id == tag_id
                )
            )
        )
        association = result.scalar_one_or_none()
        
        if not association:
            return False
        
        await self.db.delete(association)
        await self.db.commit()
        return True

    async def get_document_clusters(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Get clusters associated with a document."""
        result = await self.db.execute(
            select(Cluster, DocumentCluster.contribution_weight)
            .join(DocumentCluster, Cluster.id == DocumentCluster.cluster_id)
            .where(DocumentCluster.document_id == document_id)
        )
        
        return [
            {
                "cluster": cluster,
                "contribution_weight": weight
            }
            for cluster, weight in result.fetchall()
        ]

    async def get_document_topics(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Get topics associated with a document."""
        result = await self.db.execute(
            select(Topic, DocumentTopic.confidence)
            .join(DocumentTopic, Topic.id == DocumentTopic.topic_id)
            .where(DocumentTopic.document_id == document_id)
        )
        
        return [
            {
                "topic": topic,
                "confidence": confidence
            }
            for topic, confidence in result.fetchall()
        ]

    async def get_document_tags(self, document_id: UUID) -> List[Tag]:
        """Get tags associated with a document."""
        result = await self.db.execute(
            select(Tag)
            .join(DocumentTag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id == document_id)
        )
        
        return result.scalars().all()

    # Version management methods

    async def create_version(
        self, 
        document_id: UUID, 
        version_no: int,
        diff: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None
    ) -> DocumentVersion:
        """Create a new document version."""
        version = DocumentVersion(
            document_id=document_id,
            version_no=version_no,
            diff=diff,
            prompt=prompt
        )
        
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def get_document_versions(self, document_id: UUID) -> List[DocumentVersion]:
        """Get all versions for a document."""
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
        )
        
        return result.scalars().all()

    async def get_latest_version_number(self, document_id: UUID) -> int:
        """Get the latest version number for a document."""
        result = await self.db.execute(
            select(func.max(DocumentVersion.version_no))
            .where(DocumentVersion.document_id == document_id)
        )
        
        max_version = result.scalar()
        return max_version or 0

    async def get_documents_by_cluster(self, cluster_id: UUID) -> List[Document]:
        """Get all documents associated with a cluster."""
        result = await self.db.execute(
            select(Document)
            .join(DocumentCluster, Document.id == DocumentCluster.document_id)
            .where(DocumentCluster.cluster_id == cluster_id)
            .order_by(Document.updated_at.desc())
        )
        
        return result.scalars().all()

    async def get_documents_by_topic(self, topic_id: UUID) -> List[Document]:
        """Get all documents associated with a topic."""
        result = await self.db.execute(
            select(Document)
            .join(DocumentTopic, Document.id == DocumentTopic.document_id)
            .where(DocumentTopic.topic_id == topic_id)
            .order_by(Document.updated_at.desc())
        )
        
        return result.scalars().all()