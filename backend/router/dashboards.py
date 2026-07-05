from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database import get_db
from fastapi import Depends, APIRouter, Request
from sqlalchemy import text
from schemas import (
    DashboardCreate,
    DashboardEdit,
    DashboardDelete,
    DashboardOut,
    MessageResponse,
    DashboardBase,
)
import uuid
import json

from fastapi import HTTPException
from security.policy import current_user_id, require_folder_access, user_from_request

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboards"])

# ---------------------------------------------------------------------------


def _hexify(v):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(v, uuid.UUID):
        return str(v)
    elif isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v
def _require_dashboard_access(dashboard_id: uuid.UUID | str, request: Request, db: Session, min_level: str = "VIEWER") -> str:
    row = db.execute(
        text("SELECT parent_folder_id FROM instance01.mtd_dashboard WHERE id = CAST(:did AS uuid) AND COALESCE(status, 'ACTIVE') != 'DELETED'"),
        {"did": dashboard_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    folder_id = row[0] if not hasattr(row, "parent_folder_id") else row.parent_folder_id
    require_folder_access(folder_id, user_from_request(request), db, min_level=min_level)
    return str(folder_id)


@router.post("/createDashboard", response_model=MessageResponse)
def create_dashboard(
    payload: DashboardCreate, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create a new dashboard.
    
    **HTTP Method:** POST
    **Path:** /api/v1/dashboard/createDashboard
    
    **Parameters:**
    - payload: DashboardCreate - Dashboard object to create
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Sales Dashboard",
      "description": "Q1 2024 Sales Analysis",
      "created_at": "2024-01-15T10:30:00Z",
      "created_by": "660e8400-e29b-41d4-a716-446655440000",
      "status": "ACTIVE",
      "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
      "layout_config": {"charts": [], "layout": []}
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Dashboard created successfully",
      "data": null
    }
    ```
    """
    try:
        user = user_from_request(request)
        require_folder_access(payload.parent_folder_id, user, db, min_level="ANALYST")
        # Convert the payload to a dictionary and handle the layout_config
        data = payload.dict()
        data["created_by"] = current_user_id(user)
        if "layout_config" in data and isinstance(data["layout_config"], dict):
            data["layout_config"] = json.dumps(data["layout_config"])

        insert_q = text(
            """
            INSERT INTO instance01.mtd_dashboard(id, name, description, created_at, created_by, status, parent_folder_id, layout_config)
            VALUES (CAST(:id AS uuid), :name, :description, :created_at, :created_by,
                    :status, CAST(:parent_folder_id AS uuid), CAST(:layout_config AS jsonb))
            """
        )
        db.execute(insert_q, data)
        db.commit()
        return MessageResponse(message="Dashboard created successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in create_dashboard: {exc}")
        raise


@router.put("/editDashboard", response_model=MessageResponse)
def edit_dashboard(
    payload: DashboardEdit, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update dashboard metadata and layout.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/dashboard/editDashboard
    
    **Parameters:**
    - payload: DashboardEdit - Dashboard object with id and fields to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Updated Sales Dashboard",
      "description": "Q1-Q2 2024 Sales Analysis",
      "status": "ACTIVE",
      "layout_config": {"charts": ["chart1"], "layout": [...]}
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Dashboard updated successfully",
      "data": null
    }
    ```
    """
    try:
        _require_dashboard_access(payload.id, request, db, min_level="ANALYST")
        payload_dict = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params = {"did": payload.id}
        for key in ("name", "description", "status", "layout_config"):
            if key in payload_dict and payload_dict[key] is not None:
                # Convert layout_config to JSON string if it's a dictionary
                if key == "layout_config" and isinstance(payload_dict[key], dict):
                    params[key] = json.dumps(payload_dict[key])
                    update_fields.append(f"{key} = CAST(:{key} AS jsonb)")
                else:
                    params[key] = payload_dict[key]
                    update_fields.append(f"{key} = :{key}")
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        upd_q = text(
            f"UPDATE instance01.mtd_dashboard SET {', '.join(update_fields)} WHERE id = CAST(:did AS uuid)"
        )
        db.execute(upd_q, params)
        db.commit()
        return MessageResponse(message="Dashboard updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_dashboard: {exc}")
        raise


@router.put("/deleteDashboard", response_model=MessageResponse)
def delete_dashboard(
    payload: DashboardDelete, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Soft delete a dashboard by marking it as DELETED.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/dashboard/deleteDashboard
    
    **Parameters:**
    - payload: DashboardDelete - Dashboard object with id to delete
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Dashboard deleted successfully",
      "data": null
    }
    ```
    """
    try:
        _require_dashboard_access(payload.id, request, db, min_level="ANALYST")
        q = text(
            "UPDATE instance01.mtd_dashboard SET status='DELETED' WHERE id = CAST(:did AS uuid)"
        )
        db.execute(q, {"did": payload.id})
        db.commit()
        return MessageResponse(message="Dashboard deleted successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_dashboard: {exc}")
        raise


@router.get("/getDashboard/{dashboard_id}", response_model=MessageResponse)
def get_dashboard(dashboard_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get a single dashboard by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/dashboard/getDashboard/{dashboard_id}
    
    **Parameters:**
    - dashboard_id: str - UUID of the dashboard
    
    **Returns:**
    - MessageResponse with dashboard data
    
    **Example Request:**
    ```
    GET /api/v1/dashboard/getDashboard/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Sales Dashboard",
        "description": "Q1 2024 Sales Analysis",
        "created_at": "2024-01-15T10:30:00",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "layout_config": {"charts": [], "layout": []}
      }
    }
    ```
    """
    try:
        _require_dashboard_access(dashboard_id, request, db, min_level="VIEWER")
        sel_q = text(
            "SELECT * FROM instance01.mtd_dashboard WHERE id = CAST(:did AS uuid) AND status != 'DELETED'"
        )
        res = db.execute(sel_q, {"did": dashboard_id}).fetchone()
        if not res:
            return MessageResponse(message="Dashboard not found", data=None)
        d = res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        for k, v in d.items():
            if k == "created_at" and v is not None:
                d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
            elif k == "layout_config" and isinstance(v, str):
                d[k] = json.loads(v) if v else None
            else:
                d[k] = _hexify(v)
        return MessageResponse(message="Success", data=d)
    except Exception as exc:
        print(f"Error in get_dashboard: {exc}")
        raise


def _convert_value(value):
    """Convert value to appropriate type for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if hasattr(value, "isoformat"):  # Handles datetime objects
        return value.isoformat()
    return value


@router.get("/getDashboardByFolder/{folder_id}", response_model=List[DashboardOut])
def get_dashboard_by_folder(
    folder_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> List[DashboardOut]:
    """
    Get all dashboards in a specific folder.
    
    **HTTP Method:** GET
    **Path:** /api/v1/dashboard/getDashboardByFolder/{folder_id}
    
    **Parameters:**
    - folder_id: str - UUID of the parent folder
    
    **Returns:**
    - List[DashboardOut] - List of dashboard objects
    
    **Example Request:**
    ```
    GET /api/v1/dashboard/getDashboardByFolder/770e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Sales Dashboard",
        "description": "Q1 2024 Sales Analysis",
        "created_at": "2024-01-15T10:30:00",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "layout_config": {"charts": [], "layout": []}
      }
    ]
    ```
    """
    try:
        require_folder_access(folder_id, user_from_request(request), db, min_level="VIEWER")
        q = text(
            "SELECT * FROM instance01.mtd_dashboard WHERE parent_folder_id = CAST(:fid AS uuid) AND status != 'DELETED'"
        )
        rows = db.execute(q, {"fid": folder_id}).fetchall()
        dashboards = []
        for row in rows:
            d = row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            # Convert all values to appropriate JSON-serializable types
            d = {k: _convert_value(v) for k, v in d.items()}
            # Parse layout_config if it's a string
            if "layout_config" in d and isinstance(d["layout_config"], str):
                d["layout_config"] = json.loads(d["layout_config"]) if d["layout_config"] else None
            dashboards.append(d)
        return dashboards
    except Exception as exc:
        print(f"Error in get_dashboard_by_folder: {exc}")
        raise


@router.post("/saveDashboard", response_model=MessageResponse)
def save_dashboard(
    payload: DashboardCreate, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """Save dashboard - creates a new dashboard or updates an existing one."""
    try:
        user = user_from_request(request)
        require_folder_access(payload.parent_folder_id, user, db, min_level="ANALYST")
        # Convert the payload to a dictionary and handle the layout_config
        data = payload.dict()
        data["created_by"] = current_user_id(user)
        if "layout_config" in data and isinstance(data["layout_config"], (dict, list)):
            import json

            data["layout_config"] = json.dumps(data["layout_config"])

        # Check if dashboard exists
        dashboard_id = data["id"]
        check_q = text(
            "SELECT COUNT(*) as count FROM instance01.mtd_dashboard WHERE id = CAST(:id AS uuid)"
        )
        result = db.execute(check_q, {"id": dashboard_id}).fetchone()
        dashboard_exists = result[0] > 0 if result else False

        if dashboard_exists:
            # Update existing dashboard
            update_fields = []
            params = {"did": dashboard_id}

            # Add fields to update
            for key in ("name", "description", "status", "layout_config"):
                if key in data and data[key] is not None:
                    if key == "layout_config":
                        params[key] = data[key]
                        update_fields.append(f"{key} = CAST(:{key} AS jsonb)")
                    else:
                        params[key] = data[key]
                        update_fields.append(f"{key} = :{key}")

            if update_fields:
                upd_q = text(
                    f"UPDATE instance01.mtd_dashboard SET {', '.join(update_fields)} WHERE id = CAST(:did AS uuid)"
                )
                db.execute(upd_q, params)
                db.commit()
                return MessageResponse(
                    message="Dashboard updated successfully", data=None
                )
            else:
                return MessageResponse(message="No changes to update", data=None)
        else:
            # Insert new dashboard
            insert_q = text(
                """
                INSERT INTO instance01.mtd_dashboard(id, name, description, created_at, created_by, status, parent_folder_id, layout_config)
                VALUES (CAST(:id AS uuid), :name, :description, :created_at, CAST(:created_by AS uuid),
                        :status, CAST(:parent_folder_id AS uuid), CAST(:layout_config AS jsonb))
                """
            )
            db.execute(insert_q, data)
            db.commit()
            return MessageResponse(
                message="Dashboard created successfully", data=None
            )
    except Exception as exc:
        db.rollback()
        print(f"Error in save_dashboard: {exc}")
        import traceback

        traceback.print_exc()
        raise
