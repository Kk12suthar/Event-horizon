"""Request logging middleware for audit trails"""

import logging
import time
from pathlib import Path
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logger
logger = logging.getLogger("api_access")
logger.setLevel(logging.INFO)

# Ensure logs directory exists
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# File handler for persistent logs
handler = logging.FileHandler(log_dir / "api_access.log")
handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(handler)

# Also log to console in development
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(console_handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests and responses for audit trails
    """
    
    async def dispatch(self, request: Request, call_next):
        # Start timer
        start_time = time.time()
        
        # Get user info if available (from middleware-attached state)
        user_id = 'anonymous'
        if hasattr(request.state, 'user') and request.state.user:
            user_id = request.state.user.get('sub', 'unknown')
        
        # Get client IP
        client_ip = request.client.host if request.client else 'unknown'
        
        # Log request
        logger.info(
            f"REQUEST  | "
            f"method={request.method:6s} | "
            f"path={request.url.path:50s} | "
            f"user={user_id:20s} | "
            f"ip={client_ip}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log response
        logger.info(
            f"RESPONSE | "
            f"method={request.method:6s} | "
            f"path={request.url.path:50s} | "
            f"user={user_id:20s} | "
            f"status={response.status_code:3d} | "
            f"duration={duration:.3f}s"
        )
        
        return response
