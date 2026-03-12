from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine
from app.core.errors import (
    DSBException,
    dsb_exception_handler,
    general_exception_handler,
    http_exception_handler,
)
from app.core.logging import setup_logging, get_structured_logger

# Setup logging
setup_logging()
logger = get_structured_logger(__name__)

# Get settings
settings = get_settings()
ALLOWED_ORIGINS = frozenset(o.strip() for o in settings.cors_origins.split(",") if o.strip())


class EnsureCORSHeadersMiddleware(BaseHTTPMiddleware):
    """Ensure CORS headers are on every response (including 5xx) so the browser can read the body."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        origin = request.headers.get("origin")
        if origin and origin in ALLOWED_ORIGINS and "access-control-allow-origin" not in {
            k.lower() for k in response.headers
        }:
            response.headers["Access-Control-Allow-Origin"] = origin
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting DSB Backend API", version="1.0.0", environment=settings.environment)
    
    # Test database connection
    try:
        async with engine.begin() as conn:
            logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down DSB Backend API")
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Digital Suggestion Box API",
    description="Backend API for the Digital Suggestion Box system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

_cors_origins = list(ALLOWED_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(EnsureCORSHeadersMiddleware)

# Exception handlers
app.add_exception_handler(DSBException, dsb_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "ok": True,
        "data": {
            "status": "healthy",
            "version": "1.0.0",
            "environment": settings.environment,
        }
    }


# Import API routers
from app.api.v1 import suggestions, clusters, topics, templates, documents, jobs, metrics

# Include API routers
app.include_router(
    suggestions.router,
    prefix="/v1/suggestions",
    tags=["suggestions"],
)

app.include_router(
    clusters.router,
    prefix="/v1/clusters",
    tags=["clusters"],
)

app.include_router(
    topics.router,
    prefix="/v1/topics",
    tags=["topics"],
)

app.include_router(
    templates.router,
    prefix="/v1/templates",
    tags=["templates"],
)

app.include_router(
    documents.router,
    prefix="/v1/documents",
    tags=["documents"],
)

app.include_router(
    jobs.router,
    prefix="/v1/jobs",
    tags=["jobs"],
)

app.include_router(
    metrics.router,
    prefix="/v1/metrics",
    tags=["metrics"],
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=9000,
        reload=settings.environment == "development",
        workers=1 if settings.environment == "development" else settings.uvicorn_workers,
    )