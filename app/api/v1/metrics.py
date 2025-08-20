from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.clusters_repo import ClusterRepository
from app.adapters.repos.jobs_repo import JobRepository
from app.core.database import get_db
from app.domain.schemas import ApiResponse

router = APIRouter()


@router.get("/overview", response_model=ApiResponse)
async def get_overview_metrics(db: AsyncSession = Depends(get_db)):
    """Get overview metrics."""
    try:
        suggestions_repo = SuggestionRepository(db)
        clusters_repo = ClusterRepository(db)
        jobs_repo = JobRepository(db)
        
        # Get basic counts
        total_suggestions = await suggestions_repo.count()
        total_clusters = await clusters_repo.count()
        job_stats = await jobs_repo.get_job_stats()
        
        metrics = {
            "total_suggestions": total_suggestions,
            "total_clusters": total_clusters,
            "jobs": job_stats,
            "system_status": "operational",
            "timestamp": "2025-01-10"
        }
        
        return ApiResponse(ok=True, data=metrics)
        
    except Exception as e:
        return ApiResponse(
            ok=False, 
            data={"error": f"Failed to get overview metrics: {str(e)}"}
        )


@router.get("/clusters", response_model=ApiResponse)
async def get_cluster_metrics(db: AsyncSession = Depends(get_db)):
    """Get cluster metrics."""
    try:
        clusters_repo = ClusterRepository(db)
        
        # Get all clusters for analysis
        clusters = await clusters_repo.get_all(offset=0, limit=1000)
        
        kind_counts = {}
        status_counts = {}
        total_weight = 0.0
        
        for cluster in clusters:
            kind_counts[cluster.kind.value] = kind_counts.get(cluster.kind.value, 0) + 1
            status_counts[cluster.status.value] = status_counts.get(cluster.status.value, 0) + 1
            total_weight += cluster.weight
        
        metrics = {
            "total_clusters": len(clusters),
            "by_kind": kind_counts,
            "by_status": status_counts,
            "total_weight": total_weight,
            "avg_weight": total_weight / len(clusters) if clusters else 0,
        }
        
        return ApiResponse(ok=True, data=metrics)
        
    except Exception as e:
        return ApiResponse(
            ok=False,
            data={"error": f"Failed to get cluster metrics: {str(e)}"}
        )


@router.get("/topics", response_model=ApiResponse)
async def get_topic_metrics(db: AsyncSession = Depends(get_db)):
    """Get topic metrics."""
    try:
        # Placeholder implementation
        metrics = {
            "total_topics": 0,
            "reuse_rate": 0.0,
            "avg_confidence": 0.0,
            "message": "Topic metrics implementation needed"
        }
        
        return ApiResponse(ok=True, data=metrics)
        
    except Exception as e:
        return ApiResponse(
            ok=False,
            data={"error": f"Failed to get topic metrics: {str(e)}"}
        )


@router.get("/generation", response_model=ApiResponse)
async def get_generation_metrics(db: AsyncSession = Depends(get_db)):
    """Get document generation metrics."""
    try:
        # Placeholder implementation  
        metrics = {
            "documents_generated": 0,
            "success_rate": 0.0,
            "avg_generation_time": 0.0,
            "message": "Generation metrics implementation needed"
        }
        
        return ApiResponse(ok=True, data=metrics)
        
    except Exception as e:
        return ApiResponse(
            ok=False,
            data={"error": f"Failed to get generation metrics: {str(e)}"}
        )