"""
Health Check Router - Tiered health checks for system monitoring

Provides three levels of health checks:
1. /health/live - Liveness probe (always fast, just checks if process is alive)
2. /health/ready - Readiness probe (checks if system can serve traffic)
3. /health - Detailed health check (comprehensive system status)
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
import asyncio
from typing import Dict, Any
from database import engine
from sqlalchemy.sql import text
import shutil
import psutil
import sys
import os

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/live")
async def liveness_check():
    """
    Kubernetes liveness probe - Ultra-lightweight check
    
    Returns immediately to confirm the process is alive.
    Does NOT check database, workers, or any other dependencies.
    
    Use this for:
    - Kubernetes/Docker liveness probes
    - Load balancer health checks
    - Quick "is server running" checks
    
    Returns:
        200 OK: Process is alive
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "check_type": "liveness"
    }


async def check_database_connection() -> bool:
    """Quick database connection check with timeout"""
    try:
        def db_ping():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        
        # Run in thread pool with timeout to avoid blocking
        result = await asyncio.wait_for(
            run_in_threadpool(db_ping),
            timeout=2.0
        )
        return result
    except asyncio.TimeoutError:
        return False
    except Exception as e:
        print(f"Database health check error: {e}")
        return False



async def check_worker_pool() -> bool:
    """Check if thread pool workers are responsive"""
    try:
        # Submit a simple task to verify workers aren't deadlocked
        result = await asyncio.wait_for(
            run_in_threadpool(lambda: True),
            timeout=1.0
        )
        return result
    except asyncio.TimeoutError:
        return False
    except Exception as e:
        print(f"Worker pool health check error: {e}")
        return False


def check_disk_usage() -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage("/")
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        percent_used = (used_gb / total_gb) * 100

        status = "healthy"
        if percent_used > 90:
            status = "warning"
        if percent_used > 95:
            status = "critical"

        return {
            "status": status,
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_used": round(percent_used, 2),
        }
    except Exception as e:
        return {"status": "error", "message": f"Disk check failed: {str(e)}"}


def check_memory_usage() -> Dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024**3)
        available_gb = memory.available / (1024**3)
        percent_used = memory.percent

        status = "healthy"
        if percent_used > 80:
            status = "warning"
        if percent_used > 90:
            status = "critical"

        return {
            "status": status,
            "total_gb": round(total_gb, 2),
            "available_gb": round(available_gb, 2),
            "percent_used": round(percent_used, 2),
        }
    except Exception as e:
        return {"status": "error", "message": f"Memory check failed: {str(e)}"}



@router.get("/ready")
async def readiness_check():
    """
    Kubernetes readiness probe - Checks if system can serve traffic
    
    Verifies:
    - Database connectivity (with timeout)
    - Worker thread pool responsiveness (with timeout)
    
    Use this for:
    - Kubernetes/Docker readiness probes
    - Load balancer backend pool checks
    - Determining if server should receive traffic
    
    Returns:
        200 OK: System is ready to serve traffic
        503 Service Unavailable: System is not ready
    """
    checks = {}
    
    # Check database connection
    try:
        db_healthy = await check_database_connection()
        checks["database"] = "healthy" if db_healthy else "unhealthy"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
    
    # Check worker pool
    try:
        worker_healthy = await check_worker_pool()
        checks["workers"] = "healthy" if worker_healthy else "unhealthy"
    except Exception as e:
        checks["workers"] = f"error: {str(e)}"
    
    # Determine overall readiness
    all_healthy = all(v == "healthy" for v in checks.values())
    
    response_data = {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
        "check_type": "readiness"
    }
    
    # Return 503 if not ready (for load balancers to remove from pool)
    status_code = 200 if all_healthy else 503
    
    return JSONResponse(
        content=response_data,
        status_code=status_code
    )


@router.get("/full-check")
async def detailed_health_check():
    """
    Detailed health check - Comprehensive system status including resources
    """
    checks = {}
    
    # Database
    try:
        db_healthy = await check_database_connection()
        checks["database"] = {"status": "healthy" if db_healthy else "unhealthy"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
    
    # Workers
    try:
        worker_healthy = await check_worker_pool()
        checks["workers"] = {"status": "healthy" if worker_healthy else "unhealthy"}
    except Exception as e:
        checks["workers"] = {"status": "error", "message": str(e)}

    # System Resources
    checks["disk_usage"] = check_disk_usage()
    checks["memory_usage"] = check_memory_usage()

    # Determine overall status
    statuses = [
        checks["database"].get("status"), 
        checks["workers"].get("status"),
        checks["disk_usage"].get("status"),
        checks["memory_usage"].get("status")
    ]
    
    overall_status = "healthy"
    if "unhealthy" in statuses or "critical" in statuses or "error" in statuses:
        overall_status = "unhealthy"
    elif "warning" in statuses:
        overall_status = "warning"
        
    status_code = 200
    if overall_status == "unhealthy":
        status_code = 503
    elif overall_status == "warning":
        status_code = 206 # Partial Content as a warning indicator substitute

    return JSONResponse(
        content={
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "check_type": "full",
            "checks": checks,
            "system": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            }
        },
        status_code=status_code
    )


@router.get("")
@router.get("/")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "message": "Service is running", "timestamp": datetime.utcnow().isoformat()}

