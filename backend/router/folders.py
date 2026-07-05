from datetime import datetime, timezone
import json
import uuid
from typing import List, Dict, Any

from fastapi import Depends, APIRouter, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    FolderCreate,
    FolderEdit,
    FolderDelete,
    FolderOut,
    MessageResponse,
)
from router.projects import _update_project_counts
from security.policy import (
    current_user_id,
    require_admin,
    require_folder_access,
    require_project_access,
    user_from_request,
)

router = APIRouter(prefix="/api/v1/folder", tags=["folders"])

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
    """Ensure ISO datetime string is converted to MySQL compatible format."""
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


def _parse_entities(entities_str: Any) -> Any:
    """Parse entities JSON string back to dict/list."""
    if isinstance(entities_str, str):
        try:
            return json.loads(entities_str)
        except (json.JSONDecodeError, ValueError):
            return entities_str
    return entities_str


# ---------------------------------------------------------------------------
# CRUD ENDPOINTS FOR mtd_folder
# ---------------------------------------------------------------------------


@router.post("/createFolder", response_model=MessageResponse)
def create_folder(
    payload: FolderCreate, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create a new folder in the system.
    
    **HTTP Method:** POST  
    **Path:** /api/v1/folder/createFolder
    
    **Parameters:**
    - `id` (UUID): Unique identifier for the folder
    - `name` (str): Folder name (max 50 chars)
    - `description` (str, optional): Folder description (max 100 chars)
    - `created_at` (datetime): Timestamp of creation
    - `created_by` (UUID): ID of user creating the folder
    - `status` (str): Folder status (e.g., 'ACTIVE')
    - `project_id` (UUID): ID of parent project
    - `entities` (dict/list, optional): JSON object containing folder entities
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "My Folder",
        "description": "Project data folder",
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": "660e8400-e29b-41d4-a716-446655440001",
        "status": "ACTIVE",
        "project_id": "770e8400-e29b-41d4-a716-446655440002",
        "entities": {"tables": [], "files": []}
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Folder created successfully",
        "data": null
    }
    ```
    
    **Error Cases:**
    - Folder with same ID already exists (returns success message)
    - Database constraint violations
    - Invalid UUID format
    """
    try:
        user = user_from_request(request)
        require_project_access(payload.project_id, user, db, min_level="ANALYST")
        payload_dict = payload.dict()
        payload_dict["created_by"] = current_user_id(user)
        payload_dict["created_at"] = _format_datetime(payload_dict["created_at"])
        # Ensure entities is serializable (store as JSON string)
        if "entities" in payload_dict and payload_dict["entities"] is not None:
            if isinstance(payload_dict["entities"], (dict, list)):
                payload_dict["entities"] = json.dumps(payload_dict["entities"])
            elif isinstance(payload_dict["entities"], str):
                # Already a string, keep as-is
                pass
        else:
            # Set to None if not provided or is None
            payload_dict["entities"] = None
        # ------------------------------------------------------------------
        # Prevent duplicate primary-key errors - check if the folder exists
        # ------------------------------------------------------------------
        exists_q = text(
            "SELECT 1 FROM instance01.mtd_folder WHERE id = CAST(:fid AS uuid) LIMIT 1"
        )
        exists = db.execute(exists_q, {"fid": payload.id}).fetchone()
        if exists:
            # Folder already present - treat as success and bail early
            return MessageResponse(message="Folder already exists", data=None)

        insert_q = text(
            """
            INSERT INTO instance01.mtd_folder (id, name, description, created_at, created_by, status, project_id, entities)
            VALUES (
                CAST(:id AS uuid),
                :name,
                :description,
                :created_at,
                :created_by,
                :status,
                CAST(:project_id AS uuid),
                :entities
            )
            """
        )
        db.execute(insert_q, payload_dict)
        
        # Get all users with full PROJECT access to this project
        get_users_q = text(
            """
            SELECT user_id, level 
            FROM instance01.mtd_access 
            WHERE entity_id = CAST(:project_id AS uuid) 
            AND entity_type = 'PROJECT' 
            """
        )
        users = db.execute(get_users_q, {"project_id": payload.project_id}).fetchall()
        
        # Grant each user access to the new folder
        for user in users:
            grant_access_q = text(
                """
                INSERT INTO instance01.mtd_access(
                    entity_id, entity_type, user_id, level, 
                    granted_date, granted_by, expiration_date
                )
                VALUES (
                    CAST(:folder_id AS uuid), 'FOLDER', :user_id, :level,
                    :created_at, :created_by, NULL
                )
                ON CONFLICT (entity_id, entity_type, user_id) DO NOTHING
                """
            )
            db.execute(grant_access_q, {
                "folder_id": payload.id,
                "user_id": user[0],
                "level": user[1],
                "created_at": payload_dict["created_at"],
                "created_by": payload_dict["created_by"]
            })
        
        db.commit()
        return MessageResponse(message="Folder created successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in create_folder: {exc}")
        raise


@router.put("/editFolder", response_model=MessageResponse)
def edit_folder(
    payload: FolderEdit, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update an existing folder's mutable fields.
    
    **HTTP Method:** PUT  
    **Path:** /api/v1/folder/editFolder
    
    **Parameters:**
    - `id` (UUID): Folder ID to update
    - `name` (str, optional): New folder name
    - `description` (str, optional): New description
    - `status` (str, optional): New status
    - `entities` (dict, optional): Entities to merge with existing ones
    
    **Behavior:**
    - Only provided fields are updated
    - Entities are merged with existing entities (preserves existing keys)
    - Uses spread operator pattern: {**current_entities, **new_entities}
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Updated Folder Name",
        "entities": {"files": ["file1.csv", "file2.csv"]}
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Folder updated successfully",
        "data": null
    }
    ```
    
    **Error Cases:**
    - Folder not found
    - No valid fields to update
    - Invalid UUID format
    """
    try:
        require_folder_access(payload.id, user_from_request(request), db, min_level="ANALYST")
        payload_dict = payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params: Dict[str, Any] = {"fid": payload.id}
        
        # Handle entities merging separately
        if "entities" in payload_dict and payload_dict["entities"] is not None:
            # Fetch current entities from database
            fetch_q = text(
                "SELECT entities FROM instance01.mtd_folder WHERE id = CAST(:fid AS uuid)"
            )
            result = db.execute(fetch_q, {"fid": payload.id}).fetchone()
            
            if result:
                current_entities_str = result[0]
                current_entities = {}
                
                # Parse existing entities
                if current_entities_str:
                    # Check if already a dict (PostgreSQL may return JSON as dict)
                    if isinstance(current_entities_str, dict):
                        current_entities = current_entities_str
                    elif isinstance(current_entities_str, str):
                        try:
                            current_entities = json.loads(current_entities_str)
                            if not isinstance(current_entities, dict):
                                current_entities = {}
                        except (json.JSONDecodeError, ValueError):
                            current_entities = {}
                    else:
                        current_entities = {}
                
                # Merge new entities with existing ones
                new_entities = payload_dict["entities"]
                if isinstance(new_entities, dict):
                    merged_entities = {**current_entities, **new_entities}
                    payload_dict["entities"] = merged_entities
        
        # Process all fields
        for key in ("name", "description", "status", "entities"):
            if key in payload_dict and payload_dict[key] is not None:
                if key == "entities":
                    # Convert dict/list to JSON string
                    value = payload_dict[key]
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    update_fields.append(f"{key} = :{key}")
                    params[key] = value
                else:
                    update_fields.append(f"{key} = :{key}")
                    params[key] = payload_dict[key]
        
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        
        update_q = text(
            f"UPDATE instance01.mtd_folder SET {', '.join(update_fields)} WHERE id = CAST(:fid AS uuid)"
        )
        db.execute(update_q, params)
        db.commit()
        return MessageResponse(message="Folder updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_folder: {exc}")
        raise


@router.put("/deleteFolder", response_model=MessageResponse)
def delete_folder(
    payload: FolderDelete, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    try:
        require_folder_access(payload.id, user_from_request(request), db, min_level="ADMIN")
        # First get project_id for this folder
        project_q = text(
            "SELECT project_id FROM instance01.mtd_folder WHERE id = CAST(:fid AS uuid)"
        )
        project_id = db.execute(project_q, {"fid": payload.id}).scalar()
        
        # Delete the folder
        del_q = text(
            "UPDATE instance01.mtd_folder SET status = 'DELETED' WHERE id = CAST(:fid AS uuid)"
        )
        db.execute(del_q, {"fid": payload.id})
        
        # Trigger project count update
        if project_id:
            # Get current folder count for this project
            count_q = text(
                "SELECT COUNT(*) FROM instance01.mtd_folder "
                "WHERE project_id = CAST(:pid AS uuid) AND status != 'DELETED'"
            )
            folder_count = db.execute(count_q, {"pid": project_id}).scalar()
            
            # Update license data with new folder count
            sel_q = text(
                "SELECT data FROM instance01.data_collection WHERE title = 'license'"
            )
            result = db.execute(sel_q).fetchone()
            if result:
                license_data = result[0] if isinstance(result[0], dict) else json.loads(result[0])
                license_data["total_active_project"] = str(folder_count)
                upd_q = text(
                    "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) "
                    "WHERE title = 'license'"
                )
                db.execute(upd_q, {"data": json.dumps(license_data)})
            
            # Also update project counts
            _update_project_counts(db)
        
        db.commit()
        return MessageResponse(message="Folder deleted successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_folder: {exc}")
        raise


@router.post("/grantFolderAccess", response_model=MessageResponse)
def grant_folder_access(
    payload: Dict[str, Any], request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Grant or update access level for a user on a folder.
    Also creates/updates a project-level PARTIAL access entry.
    
    **HTTP Method:** POST  
    **Path:** /api/v1/folder/grantFolderAccess
    
    **Parameters:**
    - `entity_id` (UUID): Folder ID
    - `user_id` (UUID): User ID to grant access to
    - `access_level` (str): Access level (e.g., 'READ', 'WRITE', 'ADMIN')
    - `access_granted_date` (datetime): When access was granted
    - `access_granted_by` (UUID): ID of user granting access
    - `access_expiration_date` (datetime, optional): When access expires
    
    **Behavior:**
    - Uses ON CONFLICT to upsert (insert or update)
    - If access already exists, updates level and expiration_date
    - Empty string expiration_date is converted to None
    - Also creates/updates project-level PARTIAL access entry
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "entity_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "660e8400-e29b-41d4-a716-446655440001",
        "access_level": "WRITE",
        "access_granted_date": "2024-01-15T10:30:00Z",
        "access_granted_by": "770e8400-e29b-41d4-a716-446655440002",
        "access_expiration_date": "2024-12-31T23:59:59Z"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Access granted/updated successfully",
        "data": null
    }
    ```
    
    **Error Cases:**
    - Invalid UUID format
    - Foreign key constraint violations
    """
    try:
        require_admin(user_from_request(request), db)
        payload["access_granted_by"] = current_user_id(user_from_request(request))
        # Convert empty string expiration_date to None
        if "expiration_date" in payload and payload["expiration_date"] == "":
            payload["expiration_date"] = None
                
        # Ensure access_granted_by is properly formatted with hyphens
        """
        if 'access_granted_by' in payload and '-' not in payload['access_granted_by']:
            payload['access_granted_by'] = f"{payload['access_granted_by'][:8]}-{payload['access_granted_by'][8:12]}-{payload['access_granted_by'][12:16]}-{payload['access_granted_by'][16:20]}-{payload['access_granted_by'][20:]}"
        """
        
        # First, get the project_id for this folder
        project_query = text(
            """
            SELECT project_id 
            FROM instance01.mtd_folder 
            WHERE id = CAST(:entity_id AS uuid)
            """
        )
        project_result = db.execute(project_query, {"entity_id": payload["entity_id"]}).fetchone()
        
        if not project_result:
            raise Exception("Folder not found")
        
        project_id = str(project_result[0]) if isinstance(project_result[0], uuid.UUID) else project_result[0]

        # Grant folder access
        insert_query = text(
            """
            INSERT INTO instance01.mtd_access(entity_id, entity_type, user_id, level, granted_date, granted_by, expiration_date)
            VALUES (
                CAST(:entity_id AS uuid), 
                'FOLDER', 
                :user_id, 
                :access_level, 
                :access_granted_date, 
                :access_granted_by, 
                :access_expiration_date
            )
            ON CONFLICT (entity_id, entity_type, user_id) DO UPDATE SET 
                level = EXCLUDED.level, 
                expiration_date = EXCLUDED.expiration_date
            """
        )
        db.execute(insert_query, payload)
        
        # Check if user has PROJECT-level access to this project
        check_project_access = text(
            """
            SELECT level
            FROM instance01.mtd_access
            WHERE entity_id = CAST(:project_id AS uuid)
            AND entity_type = 'PROJECT'
            AND user_id = :user_id
            """
        )
        project_access_result = db.execute(check_project_access, {
            "project_id": project_id,
            "user_id": payload["user_id"]
        }).fetchone()

        # Only create PARTIAL entry if user has no project access or access level is NONE
        # Do nothing if user already has full project access (READ/WRITE/ADMIN/PARTIAL)
        if not project_access_result or (project_access_result and project_access_result[0] == 'NONE'):
            # Create or update project-level PARTIAL access entry
            project_access_query = text(
                """
                INSERT INTO instance01.mtd_access(entity_id, entity_type, user_id, level, granted_date, granted_by, expiration_date)
                VALUES (
                    CAST(:project_id AS uuid),
                    'PROJECT',
                    :user_id,
                    'PARTIAL',
                    :access_granted_date,
                    :access_granted_by,
                    :access_expiration_date
                )
                ON CONFLICT (entity_id, entity_type, user_id) DO UPDATE SET
                    level = EXCLUDED.level,
                    granted_date = EXCLUDED.granted_date,
                    granted_by = EXCLUDED.granted_by,
                    expiration_date = EXCLUDED.expiration_date
                """
            )
            db.execute(project_access_query, {
                "project_id": project_id,
                "user_id": payload["user_id"],
                "access_granted_date": payload["access_granted_date"],
                "access_granted_by": payload["access_granted_by"],
                "access_expiration_date": payload.get("access_expiration_date")
            })
        
        db.commit()
        return MessageResponse(message="Access granted/updated successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in grant_folder_access: {e}")
        raise


@router.put("/revokeFolderAccess", response_model=MessageResponse)
def revoke_folder_access(
    payload: Dict[str, Any], request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Revoke a user's access to a folder.
    
    **HTTP Method:** PUT  
    **Path:** /api/v1/folder/revokeFolderAccess
    
    **Parameters:**
    - `entity_id` (UUID): Folder ID
    - `user_id` (UUID): User ID to revoke access from
    
    **Behavior:**
    - Sets access level to 'NONE'
    - Does not delete the access record
    - Only affects FOLDER entity type
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "entity_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "660e8400-e29b-41d4-a716-446655440001"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Access revoked successfully",
        "data": null
    }
    ```
    
    **Error Cases:**
    - Access record not found (no error, returns success)
    - Invalid UUID format
    """
    try:
        require_admin(user_from_request(request), db)
        update_query = text(
            """
            UPDATE instance01.mtd_access 
            SET level = 'NONE' 
            WHERE entity_id = CAST(:entity_id AS uuid) 
            AND user_id = :user_id 
            AND entity_type = 'FOLDER'
            """
        )
        db.execute(update_query, payload)
        db.commit()
        return MessageResponse(message="Access revoked successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in revoke_folder_access: {e}")
        raise


@router.put("/changeFolderAccess", response_model=MessageResponse)
def change_folder_access(
    payload: Dict[str, Any], request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Change an existing user's access level for a folder.
    
    **HTTP Method:** PUT  
    **Path:** /api/v1/folder/changeFolderAccess
    
    **Parameters:**
    - `entity_id` (UUID): Folder ID
    - `user_id` (UUID): User ID whose access to change
    - `access_level` (str): New access level (e.g., 'READ', 'WRITE', 'ADMIN')
    
    **Behavior:**
    - Updates only the access level field
    - Does not modify granted_date, granted_by, or expiration_date
    - Only affects FOLDER entity type
    
    **Returns:**
    - MessageResponse with success/error message
    
    **Example Request:**
    ```json
    {
        "entity_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "660e8400-e29b-41d4-a716-446655440001",
        "access_level": "ADMIN"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Access level changed successfully",
        "data": null
    }
    ```
    
    **Error Cases:**
    - Access record not found (no error, returns success)
    - Invalid UUID format
    """
    try:
        require_admin(user_from_request(request), db)
        update_query = text(
            """
            UPDATE instance01.mtd_access 
            SET level = :access_level 
            WHERE entity_id = CAST(:entity_id AS uuid) 
            AND user_id = :user_id 
            AND entity_type = 'FOLDER'
            """
        )
        db.execute(update_query, payload)
        db.commit()
        return MessageResponse(message="Access level changed successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in change_folder_access: {e}")
        raise



@router.get("/getFolder/{folder_id}", response_model=MessageResponse)
def get_folder(folder_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Fetch a single folder by its ID.
    
    **HTTP Method:** GET  
    **Path:** /api/v1/folder/getFolder/{folder_id}
    
    **Parameters:**
    - `folder_id` (UUID, path): Folder ID to retrieve
    
    **Behavior:**
    - Returns complete folder details
    - Converts UUIDs to string format
    - Parses entities JSON to dict/list
    
    **Returns:**
    - MessageResponse with folder data or error message
    
    **Example Request:**
    ```
    GET /api/v1/folder/getFolder/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
        "message": "Success",
        "data": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "My Folder",
            "description": "Project data folder",
            "created_at": "2024-01-15T10:30:00",
            "created_by": "660e8400-e29b-41d4-a716-446655440001",
            "status": "ACTIVE",
            "project_id": "770e8400-e29b-41d4-a716-446655440002",
            "entities": {"tables": ["table1"], "files": ["file1.csv"]}
        }
    }
    ```
    
    **Error Cases:**
    - Folder not found: returns {"message": "Folder not found", "data": null}
    - Invalid UUID format
    """
    try:
        require_folder_access(folder_id, user_from_request(request), db, min_level="VIEWER")
        sel_q = text("SELECT * FROM instance01.mtd_folder WHERE id = CAST(:fid AS uuid)")
        res = db.execute(sel_q, {"fid": folder_id}).fetchone()
        if not res:
            return MessageResponse(message="Folder not found", data=None)
        folder_d = (
            res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        )
        for k, v in folder_d.items():
            folder_d[k] = _hexify(v)
        # Parse entities JSON string back to dict/list
        if "entities" in folder_d and folder_d["entities"]:
            folder_d["entities"] = _parse_entities(folder_d["entities"])
        return MessageResponse(message="Success", data=folder_d)
    except Exception as exc:
        print(f"Error in get_folder: {exc}")
        raise


@router.get("/getAllFolders", response_model=List[Dict[str, Any]])
def get_all_folders(request: Request, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get all folders including non-ACTIVE statuses for admin management.
    
    **HTTP Method:** GET  
    **Path:** /api/v1/folder/getAllFolders
    
    **Description**:
    Retrieves all folders in the system regardless of status (ACTIVE, ARCHIVED, DELETED).
    This endpoint is intended for admin management purposes.
    
    **Returns**:
    - List[Dict]: Array of folder objects with all fields
    
    **Example Response:**
    ```json
    [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "My Folder",
            "description": "Project data folder",
            "created_at": "2024-01-15T10:30:00",
            "created_by": "660e8400-e29b-41d4-a716-446655440001",
            "status": "ACTIVE",
            "project_id": "770e8400-e29b-41d4-a716-446655440002",
            "project_name": "Sales Analysis",
            "entities": {"tables": [], "files": []}
        }
    ]
    ```
    
    **Error Cases:**
    - Database errors
    """
    try:
        require_admin(user_from_request(request), db)
        query = text(
            """
            SELECT 
                f.id,
                f.name,
                f.description,
                f.created_at,
                f.created_by,
                f.status,
                f.project_id,
                f.entities,
                p.name as project_name
            FROM instance01.mtd_folder f
            LEFT JOIN instance01.mtd_project p ON f.project_id = p.id
            ORDER BY f.created_at DESC
            """
        )
        rows = db.execute(query).fetchall()
        
        folders = []
        for row in rows:
            folder_dict = (
                row._asdict()
                if hasattr(row, "_asdict")
                else dict(zip(row.keys(), row))
            )
            
            # Convert UUID and datetime fields to strings
            for key, value in folder_dict.items():
                if isinstance(value, uuid.UUID):
                    folder_dict[key] = str(value)
                elif isinstance(value, (bytes, bytearray)):
                    folder_dict[key] = value.hex()
                elif isinstance(value, datetime):
                    folder_dict[key] = value.isoformat()
            
            # Parse entities JSON string back to dict/list
            if "entities" in folder_dict and folder_dict["entities"]:
                folder_dict["entities"] = _parse_entities(folder_dict["entities"])
            
            folders.append(folder_dict)
        
        return folders
    except Exception as exc:
        print(f"Error in get_all_folders: {exc}")
        raise


@router.get("/getFolderByProject/{project_id}", response_model=List[FolderOut])
def get_folder_by_project(
    project_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> List[FolderOut]:
    """
    Retrieve all folders belonging to a specific project.
    
    **HTTP Method:** GET  
    **Path:** /api/v1/folder/getFolderByProject/{project_id}
    
    **Parameters:**
    - `project_id` (UUID, path): Project ID to get folders for
    
    **Behavior:**
    - Returns all folders under the project (including deleted ones)
    - Ordered by created_at DESC (newest first)
    - Converts all UUIDs to string format
    - Parses entities JSON to dict/list
    
    **Returns:**
    - List of FolderOut objects
    
    **Example Request:**
    ```
    GET /api/v1/folder/getFolderByProject/770e8400-e29b-41d4-a716-446655440002
    ```
    
    **Example Response:**
    ```json
    [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Folder 1",
            "description": "First folder",
            "created_at": "2024-01-15T10:30:00",
            "created_by": "660e8400-e29b-41d4-a716-446655440001",
            "status": "ACTIVE",
            "project_id": "770e8400-e29b-41d4-a716-446655440002",
            "entities": {"tables": [], "files": []}
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "name": "Folder 2",
            "description": "Second folder",
            "created_at": "2024-01-14T09:20:00",
            "created_by": "660e8400-e29b-41d4-a716-446655440001",
            "status": "ACTIVE",
            "project_id": "770e8400-e29b-41d4-a716-446655440002",
            "entities": {"tables": ["table1"], "files": ["data.csv"]}
        }
    ]
    ```
    
    **Error Cases:**
    - No folders found: returns empty list []
    - Invalid UUID format
    """
    try:
        require_project_access(project_id, user_from_request(request), db, min_level="VIEWER")
        query = text(
            """
            SELECT 
                f.id,
                f.name,
                f.description,
                f.created_at,
                f.created_by,
                u.name as created_by_name,
                f.status,
                f.project_id,
                f.entities
            FROM instance01.mtd_folder f
            LEFT JOIN instance01.mtd_users u ON f.created_by = u.id
            WHERE f.project_id = CAST(:pid AS uuid)
            ORDER BY f.created_at DESC
            """
        )
        rows = db.execute(query, {"pid": project_id}).fetchall()
        folders = []
        for row in rows:
            d = row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            # Convert UUID objects and other types to strings
            for k, v in d.items():
                if isinstance(v, uuid.UUID):
                    d[k] = str(v)
                elif isinstance(v, (bytes, bytearray)):
                    d[k] = v.hex()
                elif hasattr(v, "isoformat"):  # Handle datetime objects
                    d[k] = v.isoformat()
            # Parse entities JSON string back to dict/list
            if "entities" in d and d["entities"]:
                d["entities"] = _parse_entities(d["entities"])
            folders.append(FolderOut(**d))
        return folders
    except Exception as exc:
        print(f"Error in get_folder_by_project: {exc}")
        raise
