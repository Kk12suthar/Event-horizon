"""
License enforcement utility.
Checks license limits before allowing resource creation.
"""

import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

SCHEMA = "instance01"


def _get_license_data(db: Session) -> dict:
    """Fetch current license data from data_collection table."""
    sel_q = text(
        f"SELECT data FROM {SCHEMA}.data_collection WHERE title = 'license'"
    )
    result = db.execute(sel_q).fetchone()
    if not result:
        return {}
    return result[0] if isinstance(result[0], dict) else json.loads(result[0])


def enforce_user_limit(db: Session, role: str):
    """
    Check if adding a user with the given role would exceed the license limit.
    
    Args:
        db: Database session
        role: Role of the user being added (ADMIN, ANALYST, VIEWER)
        
    Raises:
        HTTPException: 403 if the license limit would be exceeded
    """
    license_data = _get_license_data(db)
    if not license_data:
        return  # No license data = no enforcement

    role_upper = role.upper()

    if role_upper == "ADMIN":
        current = int(license_data.get("active_admin", "0"))
        maximum = int(license_data.get("max_admin_allowed", "0"))
        role_label = "Admin"
    elif role_upper == "ANALYST":
        current = int(license_data.get("active_analyst", "0"))
        maximum = int(license_data.get("max_analyst_allowed", "0"))
        role_label = "Analyst"
    else:
        current = int(license_data.get("active_viewer", "0"))
        maximum = int(license_data.get("max_viewer_allowed", "0"))
        role_label = "Viewer"

    if maximum > 0 and current >= maximum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"License limit reached: {role_label} users ({current}/{maximum}). "
                   f"Please upgrade your license or remove existing {role_label.lower()} users."
        )


def enforce_project_limit(db: Session):
    """
    Check if creating a new project would exceed the license limit.
    
    Args:
        db: Database session
        
    Raises:
        HTTPException: 403 if the project limit would be exceeded
    """
    license_data = _get_license_data(db)
    if not license_data:
        return

    # Count actual active projects from DB for accuracy
    count_q = text(
        f"SELECT COUNT(*) FROM {SCHEMA}.mtd_project WHERE UPPER(status) = 'ACTIVE'"
    )
    current_active = db.execute(count_q).scalar() or 0

    # License doesn't currently have a max_project_allowed field,
    # but we check total_project against a reasonable cap if present
    # For now, no hard project limit exists in license schema
    # This is a placeholder for when the field is added
    max_projects = license_data.get("max_project_allowed")
    if max_projects:
        max_val = int(max_projects)
        if max_val > 0 and current_active >= max_val:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"License limit reached: Active projects ({current_active}/{max_val}). "
                       f"Please upgrade your license or archive existing projects."
            )


def enforce_transformation_limit(db: Session):
    """
    Check if running a transformation would exceed the license limit.
    
    Args:
        db: Database session
        
    Raises:
        HTTPException: 403 if the transformation limit would be exceeded
    """
    license_data = _get_license_data(db)
    if not license_data:
        return

    current = int(license_data.get("transformations_done", "0"))
    maximum = int(license_data.get("max_transformations_allowed", "0"))

    if maximum > 0 and current >= maximum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"License limit reached: Transformations ({current}/{maximum}). "
                   f"Please upgrade your license."
        )


def enforce_dashboard_limit(db: Session):
    """
    Check if creating a dashboard would exceed the license limit.
    
    Args:
        db: Database session
        
    Raises:
        HTTPException: 403 if the dashboard limit would be exceeded
    """
    license_data = _get_license_data(db)
    if not license_data:
        return

    current = int(license_data.get("dashboard_created", "0"))
    maximum = int(license_data.get("max_dashboard_allowed", "0"))

    if maximum > 0 and current >= maximum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"License limit reached: Dashboards ({current}/{maximum}). "
                   f"Please upgrade your license."
        )
