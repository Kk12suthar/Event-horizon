"""Routers for mtd_session table.
Provides CRUD endpoints and queries as described in endpoints.json.
"""

from datetime import datetime, timezone
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    MessageResponse,
    SessionCreate,
    SessionEdit,
    SessionDelete,
    SessionOut,
)

from security.policy import (
    current_user_id,
    require_folder_access,
    require_same_user_or_admin,
    require_session_owner_or_folder_access,
    user_from_request,
)

router = APIRouter(prefix="/api/v1/session", tags=["sessions"])

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _hexify(val: Any) -> Any:
    """Convert PostgreSQL UUIDs/datetime to readable str/json."""
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _format_datetime(dt: str) -> str:
    """Ensure ISO datetime string is converted to PostgreSQL compatible format."""
    if isinstance(dt, str):
        # Accept both iso 8601 with/without Z
        if dt.endswith("Z"):
            dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        else:
            dt_obj = datetime.fromisoformat(dt)
    elif isinstance(dt, datetime):
        dt_obj = dt
    else:
        dt_obj = datetime.now(timezone.utc)
    return dt_obj.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# CRUD ENDPOINTS
# ---------------------------------------------------------------------------


@router.post("/createSession", response_model=MessageResponse)
def create_session(
    payload: SessionCreate, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Insert a new session.
    
    **HTTP Method:** POST
    **Path:** /api/v1/session/createSession
    
    **Parameters:**
    - id (UUID): Session ID
    - created_at (timestamp): Creation timestamp
    - created_by (UUID): User ID who created the session
    - status (str): Session status
    - folder_id (UUID): Associated folder ID
    - app_name (str): Application name
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2025-10-08T20:13:12Z",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "app_name": "ProcessMining"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Session created successfully",
        "data": null
    }
    ```
    """
    try:
        user = user_from_request(request)
        require_folder_access(payload.folder_id, user, db, min_level="ANALYST")
        payload_dict = payload.dict()
        payload_dict["created_by"] = current_user_id(user)
        payload_dict["created_at"] = _format_datetime(payload_dict["created_at"])
        # Remove entities field if present (no longer in schema)
        if "entities" in payload_dict:
            del payload_dict["entities"]
        # ------------------------------------------------------------------
        # Prevent duplicate primary-key errors - check if the session exists
        # ------------------------------------------------------------------
        exists_q = text(
            "SELECT 1 FROM instance01.mtd_session WHERE id = CAST(:sid AS uuid) LIMIT 1"
        )
        exists = db.execute(exists_q, {"sid": payload.id}).fetchone()
        if exists:
            # Session already present - treat as success and bail early
            return MessageResponse(message="Session already exists", data=None)

        insert_q = text(
            """
            INSERT INTO instance01.mtd_session (id, created_at, created_by, status, folder_id, app_name)
            VALUES (
                CAST(:id AS uuid),
                :created_at,
                :created_by,
                :status,
                CAST(:folder_id AS uuid),
                :app_name
            )
            """
        )
        db.execute(insert_q, payload_dict)
        db.commit()
        return MessageResponse(message="Session created successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in create_session: {exc}")
        raise


@router.put("/editSession", response_model=MessageResponse)
def edit_session(
    payload: SessionEdit, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update a session's mutable fields.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/session/editSession
    
    **Parameters:**
    - id (UUID): Session ID to update
    - status (str, optional): New status
    - app_name (str, optional): New application name
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "COMPLETED"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Session updated successfully",
        "data": null
    }
    ```
    """
    try:
        require_session_owner_or_folder_access(payload.id, user_from_request(request), db, min_level="ANALYST")
        payload_dict = payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params: Dict[str, Any] = {"sid": payload.id}
        # Only allow updating status and app_name (entities removed from schema)
        for key in ("status", "app_name"):
            if key in payload_dict and payload_dict[key] is not None:
                update_fields.append(f"{key} = :{key}")
                params[key] = payload_dict[key]
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        update_q = text(
            f"UPDATE instance01.mtd_session SET {', '.join(update_fields)} WHERE id = CAST(:sid AS uuid)"
        )
        db.execute(update_q, params)
        db.commit()
        return MessageResponse(message="Session updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_session: {exc}")
        raise


@router.put("/deleteSession", response_model=MessageResponse)
def delete_session(
    payload: SessionDelete, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Soft delete a session by setting status to 'DELETED'.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/session/deleteSession
    
    **Parameters:**
    - id (UUID): Session ID to delete
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Session deleted successfully",
        "data": null
    }
    ```
    """
    try:
        require_session_owner_or_folder_access(payload.id, user_from_request(request), db, min_level="ANALYST")
        del_q = text(
            "UPDATE instance01.mtd_session SET status = 'DELETED' WHERE id = CAST(:sid AS uuid)"
        )
        db.execute(del_q, {"sid": payload.id})
        db.commit()
        return MessageResponse(message="Session deleted successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_session: {exc}")
        raise


@router.get("/getSession/{session_id}", response_model=MessageResponse)
def get_session(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Fetch a session by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/session/getSession/{session_id}
    
    **Parameters:**
    - session_id (UUID): Session ID to retrieve
    
    **Returns:**
    - MessageResponse with session data
    
    **Example Request:**
    ```
    GET /api/v1/session/getSession/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Success",
        "data": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2025-10-08T20:13:12",
            "created_by": "660e8400-e29b-41d4-a716-446655440000",
            "status": "ACTIVE",
            "folder_id": "770e8400-e29b-41d4-a716-446655440000",
            "app_name": "ProcessMining"
        }
    }
    ```
    """
    try:
        require_session_owner_or_folder_access(session_id, user_from_request(request), db, min_level="VIEWER")
        sel_q = text("SELECT * FROM instance01.mtd_session WHERE id = CAST(:sid AS uuid)")
        res = db.execute(sel_q, {"sid": session_id}).fetchone()
        if not res:
            return MessageResponse(message="Session not found", data=None)
        sess_d = (
            res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        )
        for k, v in sess_d.items():
            sess_d[k] = _hexify(v)
        return MessageResponse(message="Success", data=sess_d)
    except Exception as exc:
        print(f"Error in get_session: {exc}")
        raise


@router.get(
    "/getSessionByFolderAndUser/{folder_id}/{user_id}", response_model=SessionOut
)
def get_session_by_folder_and_user(
    folder_id: uuid.UUID, user_id: str, request: Request, db: Session = Depends(get_db)
) -> SessionOut:
    """
    Return single session for a folder and user (non-deleted), latest created.
    
    **HTTP Method:** GET
    **Path:** /api/v1/session/getSessionByFolderAndUser/{folder_id}/{user_id}
    
    **Parameters:**
    - folder_id (UUID): Folder ID
    - user_id (UUID): User ID
    
    **Returns:**
    - SessionOut with the most recent active session
    
    **Example Request:**
    ```
    GET /api/v1/session/getSessionByFolderAndUser/770e8400-e29b-41d4-a716-446655440000/660e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2025-10-08T20:13:12",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "app_name": "ProcessMining"
    }
    ```
    
    **Error Cases:**
    - 404: No session found for the given folder and user
    """
    try:
        user_id = require_same_user_or_admin(user_id, user_from_request(request), db)
        require_folder_access(folder_id, user_from_request(request), db, min_level="VIEWER")
        query = text(
            """
            SELECT 
                id,
                created_at,
                created_by,
                status,
                folder_id,
                app_name
            FROM instance01.mtd_session
            WHERE folder_id = CAST(:fid AS uuid)
              AND created_by = :uid
              AND status != 'DELETED' AND status != 'ARCHIVED'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = db.execute(query, {"fid": folder_id, "uid": user_id}).fetchone()
        if row:
            d = row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            for k, v in d.items():
                d[k] = _hexify(v)
            return SessionOut(**d)
        else:
            raise HTTPException(status_code=404, detail="No session found")
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error in get_session_by_folder_and_user: {exc}")
        raise
