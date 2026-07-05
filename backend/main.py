from fastapi import FastAPI, Request, HTTPException, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from env import load_environment

load_environment()

from router import (
    projects,
    users,
    folders,
    dashboards,
    files,
    sessions,
    webSockets,
    authService,
    data,
    data_collection,
    invitations, 
    refresh,
    health
)

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from fastapi.responses import JSONResponse

try:
    from router import elk_data
except ModuleNotFoundError as exc:
    if exc.name != "pm4py":
        raise
    elk_data = None
    print("WARNING: Process-mining ELK routes disabled because pm4py is not installed.")


# Import security middleware
from middleware.request_logger import RequestLoggingMiddleware
from middleware.request_size_limiter import RequestSizeLimitMiddleware
from utils.authentication import decode_access_token, validate_jwt_config
from utils.error_handlers import setup_error_handlers

# ---------------------------------------------------------------------------
# Security Configuration Validation
# ---------------------------------------------------------------------------
# Validate JWT configuration at startup to fail fast if misconfigured
try:
    validate_jwt_config()
    print("✅ JWT configuration validated successfully")
except ValueError as e:
    print(f"❌ CRITICAL: {e}")
    sys.exit(1)

# Validate FRONTEND_URL is set for CORS
FRONTEND_URL = os.getenv("FRONTEND_URL")
if not FRONTEND_URL:
    print("❌ CRITICAL: FRONTEND_URL environment variable is not set. This is required for CORS security.")
    sys.exit(1)
print(f"✅ FRONTEND_URL configured: {FRONTEND_URL}")

# ---------------------------------------------------------------------------
# FastAPI App Setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Backend Server",
    version="1.0.0",
    description="Backend server with transformation and process analysis capabilities",
    openapi_url=f"/api/openapi.json",
    docs_url=f"/api/docs",
    redoc_url=f"/api/redoc",
)

# SECURITY FIX-007: Setup global error handlers
setup_error_handlers(app)

@app.on_event("startup")
def _create_audit_table():
    """Ensure admin_audit_logs table exists on startup."""
    try:
        from database import get_db
        from utils.audit_logger import _ensure_audit_table
        db = next(get_db())
        _ensure_audit_table(db)
        print("✅ Audit logs table ready")
    except Exception as e:
        print(f"⚠️ Could not ensure audit table (non-fatal): {e}")

app.include_router(projects.router)
app.include_router(users.router)
app.include_router(folders.router)
app.include_router(dashboards.router)
app.include_router(files.router)
app.include_router(sessions.router)
app.include_router(webSockets.router)
app.include_router(authService.router)
app.include_router(data.router)
app.include_router(data_collection.router)
app.include_router(invitations.router)
app.include_router(refresh.router)
if elk_data is not None:
    app.include_router(elk_data.router)
app.include_router(health.router)

# create a rate limiter
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Security Configuration
# ---------------------------------------------------------------------------

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    "/",
    "/api/health",
    "/api/health/live",
    "/api/health/ready",
    "/api/health/full-check",
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
    "/api/v1/auth/signup",
    "/api/v1/auth/signin",
    "/api/v1/invitations/verify",
    "/api/v1/invitations/accept",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/verify-email"
]

# ---------------------------------------------------------------------------
# Middleware Configuration
# ---------------------------------------------------------------------------

# Add request size limiter (10MB default) - FIRST to reject large requests early
app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)

# Add request logging for audit trails
app.add_middleware(RequestLoggingMiddleware)

# Add GZip compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add trusted host middleware (optional - uncomment for production)
# ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Add the rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ---------------------------------------------------------------------------
# Authentication Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    """
    Global authentication middleware - protects all endpoints except public ones
    
    To disable: Comment out this entire function
    """
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Skip authentication for public endpoints
    if request.url.path in PUBLIC_ENDPOINTS or request.url.path.startswith("/api/chart-thumbnail"):
        return await call_next(request)
    
    # Check for Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid authorization header"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract and verify token
    token = auth_header.replace("Bearer ", "")
    token_data = decode_access_token(token)
    
    if not token_data:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Attach user data to request state for downstream use
    request.state.user = token_data
    
    # Continue processing request
    return await call_next(request)


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Set up CORS with specific origins
# SECURITY: Only allow localhost in development; strictly enforce FRONTEND_URL in production
origins = [FRONTEND_URL]
if not IS_PRODUCTION:
    origins.extend([
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Add security headers to all responses
    """
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Only add HSTS in production
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response


# Upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)

# Serve thumbnails as static files
THUMBNAIL_DIR = Path(__file__).parent / "thumbnails"
Path(THUMBNAIL_DIR).mkdir(exist_ok=True)
app.mount(
    "/api/chart-thumbnail", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails"
)


@app.get("/api/")
async def root():
    return {"message": "Backend is running. Refer to /docs for Swagger UI."}

# if __name__ == "__main__":uvicorn.run("main:app", host=host, port=port, reload=True)

# uvicorn main:app --reload
# uvicorn main:app --reload --host 127.0.0.1 --port 8000
# uvicorn main:app --host 127.0.0.1 --reload --port 8001 --ws-ping-interval 10 --ws-ping-timeout 30
