from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.clusters_repo import ClusterRepository
from app.core.errors import NotFoundError
from app.domain.schemas import (
    ApiResponse,
    ClusterCreate,
    ClusterResponse,
    ClusterFilters,
    PaginationMeta,
)
from app.core.database import get_db

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def get_clusters(
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_weight: Optional[float] = Query(None),
    tag: Optional[str] = Query(None),
    topic_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get clusters with optional filters and pagination."""
    clusters_repo = ClusterRepository(db)
    
    filters = ClusterFilters(
        kind=kind,
        status=status,
        min_weight=min_weight,
        tag=tag,
        topic_id=topic_id,
    )
    
    offset = (page - 1) * page_size
    clusters = await clusters_repo.get_all(filters, offset, page_size)
    total = await clusters_repo.count(filters)
    
    cluster_responses = [ClusterResponse.model_validate(c) for c in clusters]
    
    return ApiResponse(
        ok=True,
        data=cluster_responses,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ).model_dump(),
    )


@router.get("/{cluster_id}", response_model=ApiResponse)
async def get_cluster(
    cluster_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a cluster by ID."""
    clusters_repo = ClusterRepository(db)
    
    cluster = await clusters_repo.get_by_id(cluster_id)
    if not cluster:
        raise NotFoundError(f"Cluster {cluster_id} not found", "Cluster")
    
    return ApiResponse(
        ok=True,
        data=ClusterResponse.model_validate(cluster),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_cluster(
    cluster_data: ClusterCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new cluster."""
    clusters_repo = ClusterRepository(db)
    
    cluster = await clusters_repo.create(cluster_data)
    
    return ApiResponse(
        ok=True,
        data=ClusterResponse.model_validate(cluster),
    )


@router.patch("/{cluster_id}", response_model=ApiResponse)
async def update_cluster(
    cluster_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a cluster."""
    clusters_repo = ClusterRepository(db)
    
    cluster = await clusters_repo.update(cluster_id, **updates)
    if not cluster:
        raise NotFoundError(f"Cluster {cluster_id} not found", "Cluster")
    
    return ApiResponse(
        ok=True,
        data=ClusterResponse.model_validate(cluster),
    )


@router.post("/{cluster_id}/members", response_model=ApiResponse)
async def add_cluster_member(
    cluster_id: UUID,
    member_data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Add a member to a cluster."""
    clusters_repo = ClusterRepository(db)
    
    member = await clusters_repo.add_member(
        cluster_id=cluster_id,
        document_id=member_data.get("document_id"),
        suggestion_id=member_data.get("suggestion_id"),
        similarity=member_data.get("similarity"),
        is_manual=member_data.get("is_manual", False),
    )
    
    return ApiResponse(
        ok=True,
        data={"message": "Member added to cluster successfully"},
    )


@router.delete("/{cluster_id}/members/{member_id}", response_model=ApiResponse)
async def remove_cluster_member(
    cluster_id: UUID,
    member_id: UUID,
    member_type: str = Query(..., regex="^(document|suggestion)$"),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a cluster."""
    clusters_repo = ClusterRepository(db)
    
    if member_type == "document":
        success = await clusters_repo.remove_member(cluster_id, document_id=member_id)
    else:
        success = await clusters_repo.remove_member(cluster_id, suggestion_id=member_id)
    
    if not success:
        raise NotFoundError("Member not found in cluster", "ClusterMember")
    
    return ApiResponse(
        ok=True,
        data={"message": "Member removed from cluster successfully"},
    )