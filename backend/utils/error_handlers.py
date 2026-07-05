"""Generic error handler for sanitizing error responses"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import traceback
import sys

logger = logging.getLogger(__name__)


def sanitize_error_message(error: Exception, include_details: bool = False) -> str:
    """
    Sanitize error message for user-facing responses
    
    SECURITY FIX-007: Remove sensitive information from error messages
    
    Args:
        error: The exception to sanitize
        include_details: Whether to include technical details (dev mode only)
        
    Returns:
        Sanitized error message safe for user consumption
    """
    # Generic user-friendly messages
    error_type = type(error).__name__
    
    # Map error types to user-friendly messages
    user_friendly_messages = {
        "ValidationError": "Invalid input data provided",
        "IntegrityError": "Data integrity constraint violated",
        "OperationalError": "Database operation failed",
        "TimeoutError": "Request timed out",
        "ConnectionError": "Service temporarily unavailable",
        "PermissionError": "Access denied",
        "FileNotFoundError": "Requested resource not found",
    }
    
    base_message = user_friendly_messages.get(error_type, "An error occurred processing your request")
    
    # In development, include more details (controlled by env var)
    if include_details:
        return f"{base_message}: {str(error)}"
    
    return base_message


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Generic exception handler for all unhandled exceptions
    
    SECURITY FIX-007: Log full details server-side, return sanitized message to client
    """
    # Log full error details server-side
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}",
        exc_info=True
    )
    
    # Determine if we're in development mode
    import os
    is_dev = os.getenv("ENVIRONMENT", "production").lower() in ["development", "dev"]
    
    # Return sanitized error to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": sanitize_error_message(exc, include_details=is_dev),
            "type": "internal_server_error"
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handler for HTTP exceptions
    
    SECURITY FIX-007: Sanitize HTTP exception messages
    """
    # Log error details
    if exc.status_code >= 500:
        logger.error(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    else:
        logger.warning(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    
    # Return response (HTTP exceptions are already user-safe)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler for request validation errors
    
    SECURITY FIX-007: Return sanitized validation errors
    """
    # Log validation error
    logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    
    # Return user-friendly validation errors
    errors = []
    for error in exc.errors():
        # Sanitize error details
        field = " -> ".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append({
            "field": field,
            "message": message,
            "type": error["type"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors
        },
    )


def setup_error_handlers(app):
    """
    Setup global error handlers for the FastAPI application
    
    Usage in main.py:
        from utils.error_handlers import setup_error_handlers
        setup_error_handlers(app)
    """
    app.add_exception_handler(Exception, generic_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    logger.info("✅ Global error handlers configured")
