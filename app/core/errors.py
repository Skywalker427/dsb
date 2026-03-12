from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_424_FAILED_DEPENDENCY,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.core.config import get_settings
from app.core.logging import get_structured_logger

logger = get_structured_logger(__name__)


def _cors_headers(request: Request) -> Dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    allowed = frozenset(o.strip() for o in get_settings().cors_origins.split(",") if o.strip())
    if origin in allowed:
        return {"Access-Control-Allow-Origin": origin}
    return {}


class DSBException(Exception):
    """Base exception for DSB application."""
    
    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None,
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(DSBException):
    """Validation error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details,
            status_code=HTTP_400_BAD_REQUEST,
        )


class UnauthorizedError(DSBException):
    """Unauthorized access error."""
    
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(DSBException):
    """Forbidden access error."""
    
    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=HTTP_403_FORBIDDEN,
        )


class NotFoundError(DSBException):
    """Resource not found error."""
    
    def __init__(self, message: str, resource: str = "Resource"):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            details={"resource": resource},
            status_code=HTTP_404_NOT_FOUND,
        )


class ConflictError(DSBException):
    """Resource conflict error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CONFLICT",
            details=details,
            status_code=HTTP_409_CONFLICT,
        )


class RateLimitError(DSBException):
    """Rate limit exceeded error."""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            code="RATE_LIMITED",
            status_code=HTTP_429_TOO_MANY_REQUESTS,
        )


class DependencyError(DSBException):
    """External dependency failure error."""
    
    def __init__(self, message: str, service: str = "External service"):
        super().__init__(
            message=message,
            code="DEPENDENCY_FAILED",
            details={"service": service},
            status_code=HTTP_424_FAILED_DEPENDENCY,
        )


class ServiceUnavailableError(DSBException):
    """Service unavailable error."""
    
    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
        )


async def dsb_exception_handler(request: Request, exc: DSBException) -> JSONResponse:
    """Handle DSB application exceptions."""
    logger.error(
        "DSB Exception",
        error_code=exc.code,
        error_message=exc.message,
        error_details=exc.details,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
        headers=_cors_headers(request),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error(
        "Unhandled Exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "ok": False,
            "error": {
                "code": "SERVER_ERROR",
                "message": "Internal server error",
                "details": {},
            },
        },
        headers=_cors_headers(request),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    logger.warning(
        "HTTP Exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
    )
    
    # Map HTTP status codes to error codes
    status_to_code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    
    error_code = status_to_code.get(exc.status_code, "HTTP_ERROR")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "code": error_code,
                "message": exc.detail,
                "details": {},
            },
        },
        headers=_cors_headers(request),
    )