"""Request size limit middleware to prevent DoS attacks"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit request body size and prevent DoS attacks
    """
    
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        """
        Args:
            app: FastAPI application
            max_size: Maximum request body size in bytes (default: 10MB)
        """
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next):
        # Only check for methods that have request bodies
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            
            if content_length:
                try:
                    size = int(content_length)
                    if size > self.max_size:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": f"Request body too large. Maximum size: {self.max_size / 1024 / 1024:.1f}MB"
                            }
                        )
                except ValueError:
                    # Invalid content-length header
                    pass
        
        return await call_next(request)
