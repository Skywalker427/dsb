from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.domain.models import Cluster, ClusterMember
from app.domain.schemas import ClusterCreate, ClusterFilters


class ClusterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, cluster_data: ClusterCreate) -> Cluster:
        """Create a new cluster."""
        cluster = Cluster(
            kind=cluster_data.kind,
            title=cluster_data.title,
            description=cluster_data.description,
            tags=cluster_data.tags or [],
            primary_topic_id=cluster_data.primary_topic_id,
            fusion_params=cluster_data.fusion_params,
        )
        
        self.db.add(cluster)
        await self.db.commit()
        await self.db.refresh(cluster)
        return cluster

    async def get_by_id(self, cluster_id: UUID) -> Optional[Cluster]:
        """Get cluster by ID."""
        result = await self.db.execute(
            select(Cluster).where(Cluster.id == cluster_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        filters: Optional[ClusterFilters] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Cluster]:
        """Get all clusters with optional filters."""
        query = select(Cluster)
        
        if filters:
            if filters.kind:
                query = query.where(Cluster.kind == filters.kind)
            if filters.status:
                query = query.where(Cluster.status == filters.status)
            if filters.min_weight is not None:
                query = query.where(Cluster.weight >= filters.min_weight)
            if filters.tag:
                query = query.where(Cluster.tags.any(filters.tag))
            if filters.topic_id:
                query = query.where(Cluster.primary_topic_id == filters.topic_id)
        
        query = query.offset(offset).limit(limit).order_by(Cluster.weight.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update(self, cluster_id: UUID, **kwargs) -> Optional[Cluster]:
        """Update a cluster."""
        result = await self.db.execute(
            select(Cluster).where(Cluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        
        if not cluster:
            return None
            
        for key, value in kwargs.items():
            if hasattr(cluster, key):
                setattr(cluster, key, value)
                
        await self.db.commit()
        await self.db.refresh(cluster)
        return cluster

    async def delete(self, cluster_id: UUID) -> bool:
        """Delete a cluster and its members."""
        # First delete cluster members
        await self.db.execute(
            select(ClusterMember).where(ClusterMember.cluster_id == cluster_id)
        )
        
        # Then delete the cluster
        result = await self.db.execute(
            select(Cluster).where(Cluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        
        if not cluster:
            return False
            
        await self.db.delete(cluster)
        await self.db.commit()
        return True

    async def add_member(
        self,
        cluster_id: UUID,
        document_id: Optional[UUID] = None,
        suggestion_id: Optional[UUID] = None,
        similarity: Optional[float] = None,
        is_manual: bool = False,
    ) -> ClusterMember:
        """Add a member to a cluster."""
        member = ClusterMember(
            cluster_id=cluster_id,
            document_id=document_id,
            suggestion_id=suggestion_id,
            similarity=similarity,
            is_manual=is_manual,
        )
        
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def remove_member(
        self,
        cluster_id: UUID,
        document_id: Optional[UUID] = None,
        suggestion_id: Optional[UUID] = None,
    ) -> bool:
        """Remove a member from a cluster."""
        query = select(ClusterMember).where(ClusterMember.cluster_id == cluster_id)
        
        if document_id:
            query = query.where(ClusterMember.document_id == document_id)
        elif suggestion_id:
            query = query.where(ClusterMember.suggestion_id == suggestion_id)
        else:
            return False
            
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()
        
        if not member:
            return False
            
        await self.db.delete(member)
        await self.db.commit()
        return True

    async def get_members(self, cluster_id: UUID) -> List[ClusterMember]:
        """Get all members of a cluster."""
        result = await self.db.execute(
            select(ClusterMember).where(ClusterMember.cluster_id == cluster_id)
        )
        return result.scalars().all()

    async def count(self, filters: Optional[ClusterFilters] = None) -> int:
        """Count clusters with optional filters."""
        from sqlalchemy import func
        
        query = select(func.count(Cluster.id))
        
        if filters:
            if filters.kind:
                query = query.where(Cluster.kind == filters.kind)
            if filters.status:
                query = query.where(Cluster.status == filters.status)
            if filters.min_weight is not None:
                query = query.where(Cluster.weight >= filters.min_weight)
            if filters.tag:
                query = query.where(Cluster.tags.any(filters.tag))
            if filters.topic_id:
                query = query.where(Cluster.primary_topic_id == filters.topic_id)
        
        result = await self.db.execute(query)
        return result.scalar()