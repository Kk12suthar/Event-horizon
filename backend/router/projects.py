# routers/projects.py
from sqlalchemy import or_, and_, text
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database import get_db
from fastapi import Depends, Request
from schemas import (
    ProjectCreate,
    ProjectEdit,
    ProjectDelete,
    ProjectOut,
    MessageResponse,
)
import uuid
import json
from fastapi import APIRouter
from fastapi import HTTPException
from utils.audit_logger import log_admin_action, ACTION_ACCESS_GRANTED, ACTION_ACCESS_REVOKED, ACTION_ACCESS_CHANGED, ACTION_PROJECT_CREATED, ACTION_PROJECT_EDITED, ACTION_PROJECT_DELETED
from utils.license_enforcement import enforce_project_limit
from security.policy import (
    require_admin,
    require_project_access,
    require_same_user_or_admin,
    user_from_request,
)

router = APIRouter(prefix="/api/v1/project", tags=["projects"])


def _update_project_counts(db: Session, status_change: Dict[str, str] = None, delta: int = 0):
    """
    Update license data project counts when projects are added/removed or status changes.

    Args:
        db: Database session
        status_change: Dict with 'old_status' and 'new_status' for status changes
        delta: +1 for add, -1 for remove (used when creating/deleting projects)
    """
    try:
        # Get current license data
        sel_q = text(
            "SELECT data FROM instance01.data_collection WHERE title = 'license'"
        )
        result = db.execute(sel_q).fetchone()
        if not result:
            return

        # Ensure we have a dict (PostgreSQL returns JSONB as dict)
        license_data = result[0] if isinstance(result[0], dict) else json.loads(result[0])

        if delta != 0:
            # Adding or removing a project
            # Recalculate total_project by counting all non-deleted projects (case-insensitive)
            total_count_q = text(
                "SELECT COUNT(*) FROM instance01.mtd_project"
            )
            total_count = db.execute(total_count_q).scalar()
            print(f"[DEBUG] Total deleted projects: {total_count}")
            license_data["total_project"] = str(total_count)

            # For adds, increment active count
            if delta > 0:
                license_data["total_active_project"] = str(int(license_data.get("total_active_project", "0")) + delta)
            # For deletes, always recalculate active count (case-insensitive)
            else:
                count_q = text(
                    "SELECT COUNT(*) FROM instance01.mtd_project WHERE UPPER(status) = 'ACTIVE'"
                )
                active_count = db.execute(count_q).scalar()
                print(f"[DEBUG] Active project count after delete: {active_count}")
                license_data["total_active_project"] = str(active_count)
        
        elif status_change:
            # Status is changing
            old_status = status_change.get('old_status', '')
            new_status = status_change.get('new_status', '')

            # Recalculate active projects count (case-insensitive)
            count_q = text(
                "SELECT COUNT(*) FROM instance01.mtd_project WHERE UPPER(status) = 'ACTIVE'"
            )
            active_count = db.execute(count_q).scalar()
            license_data["total_active_project"] = str(active_count)
        
        # Save updated license data
        upd_q = text(
            "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE title = 'license'"
        )
        db.execute(upd_q, {"data": json.dumps(license_data)})
    except Exception as exc:
        print(f"Error updating project counts: {exc}")
        raise


@router.get("/getProjectNames", response_model=List[Dict[str, str]])
def get_project_names(request: Request, db: Session = Depends(get_db)) -> List[Dict[str, str]]:
    """
    Get only project IDs and names for autocomplete purposes
    Returns: List of {id, name} objects
    """
    try:
        require_admin(user_from_request(request), db)
        query = text("SELECT id, name FROM instance01.mtd_project WHERE status != 'DELETED'")
        rows = db.execute(query).fetchall()
        return [
            {"id": str(row[0]), "name": row[1]} 
            for row in rows
        ]
    except Exception as exc:
        print(f"Error in get_project_names: {exc}")
        raise


@router.get("/getAllProjects", response_model=List[Dict[str, Any]])
def get_all_projects(request: Request, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get all projects including non-ACTIVE statuses for admin management.
    
    **Endpoint**: GET /api/v1/project/getAllProjects
    
    **Description**:
    Retrieves all projects in the system regardless of status (ACTIVE, ARCHIVED, DELETED).
    This endpoint is intended for admin management purposes.
    
    **Returns**:
        - List[Dict]: Array of project objects, each containing:
            - id (str): Project UUID
            - name (str): Project name
            - description (str): Project description
            - created_at (str): ISO timestamp of creation
            - created_by (str): Creator's user UUID
            - status (str): Project status (ACTIVE/ARCHIVED/DELETED)
            - created_by_name (str): Name of the user who created the project
    
    **Example Response**:
        ```json
        [
            {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "name": "Sales Analysis",
                "description": "Q4 sales process mining",
                "created_at": "2025-01-15T10:30:00",
                "created_by": "f6e5d4c3-b2a1-0987-6543-210fedcba987",
                "status": "ACTIVE",
                "created_by_name": "John Doe"
            }
        ]
        ```
    
    **Raises**:
        - Exception: Database errors or invalid UUID format
    """
    try:
        require_admin(user_from_request(request), db)
        query = text(
            """
            SELECT 
                p.id,
                p.name,
                p.description,
                p.created_at,
                p.created_by,
                p.status,
                u.name as created_by_name
            FROM instance01.mtd_project p
            LEFT JOIN instance01.mtd_users u ON p.created_by = u.id
            ORDER BY p.created_at DESC
            """
        )
        rows = db.execute(query).fetchall()
        
        projects = []
        for row in rows:
            project_dict = (
                row._asdict()
                if hasattr(row, "_asdict")
                else dict(zip(row.keys(), row))
            )
            
            # Convert UUID and datetime fields to strings
            for key, value in project_dict.items():
                if isinstance(value, uuid.UUID):
                    project_dict[key] = str(value)
                elif isinstance(value, (bytes, bytearray)):
                    project_dict[key] = value.hex()
                elif isinstance(value, datetime):
                    project_dict[key] = value.isoformat()
            
            projects.append(project_dict)
        
        return projects
    except Exception as exc:
        print(f"Error in get_all_projects: {exc}")
        raise


@router.get("/getProjectByUser/{user_id}", response_model=List[ProjectOut])
def get_user_projects(
    user_id: str, request: Request, db: Session = Depends(get_db), include: Optional[str] = None
) -> List[ProjectOut]:
    """
    Get all projects a user has access to via the mtd_access table.
    
    **Endpoint**: GET /api/v1/project/getProjectByUser/{user_id}
    
    **Description**: 
    Retrieves all active projects that the specified user has access to, along with
    associated folders and users (if user is admin/owner). Only returns projects where
    the user has valid, non-expired access and the project status is not 'DELETED'.

    **Path Parameters**:
        - user_id (str): UUID of the user (can be with or without hyphens)

    **Query Parameters**:
        - include (Optional[str]): Reserved for future use to include additional related data

    **Returns**:
        - List[ProjectOut]: Array of project objects, each containing:
            - id (str): Project UUID in hex format
            - name (str): Project name
            - description (str): Project description
            - created_at (str): ISO timestamp of creation
            - created_by (str): Creator's user UUID in hex format
            - status (str): Project status (ACTIVE/ARCHIVED/DELETED)
            - created_by_name (str): Name of the user who created the project
            - user_access_level (str): Access level of the requesting user (OWNER/ADMIN/ANALYST/VIEWER)
            - folders (List): Array of folders the user has access to within this project
            - users (List): Array of users with access (only included if requesting user is admin/owner)
    
    **Database Tables Used**:
        - mtd_project: Project details
        - mtd_users: User information
        - mtd_access: Access control entries
        - mtd_folder: Folder information
    
    **Access Control**:
        - Returns only projects where user has active access via mtd_access table
        - User list is only included for admin/owner level access
        - Filters out expired access (expiration_date check)
    
    **Example Response**:
        ```json
        [
            {
                "id": "a1b2c3d4e5f6...",
                "name": "Sales Analysis",
                "description": "Q4 sales process mining",
                "created_at": "2025-01-15T10:30:00",
                "created_by": "f6e5d4c3b2a1...",
                "status": "ACTIVE",
                "created_by_name": "John Doe",
                "user_access_level": "ADMIN",
                "folders": [...],
                "users": [...]
            }
        ]
        ```
    
    **Raises**:
        - Exception: Database errors or invalid UUID format
    """
    try:
        # Normalize user_id to UUID string format
        try:
            user_uuid = uuid.UUID(user_id)
            user_id_str = str(user_uuid)
        except (ValueError, AttributeError):
            # If not a valid UUID string, use as-is
            user_id_str = user_id

        user_id_str = require_same_user_or_admin(user_id_str, user_from_request(request), db)

        # ── ADMIN bypass: workspace-level ADMIN sees all projects ──────────
        role_query = text(
            "SELECT role FROM instance01.mtd_users WHERE id = :user_id"
        )
        role_result = db.execute(role_query, {"user_id": user_id_str}).fetchone()
        is_workspace_admin = role_result and role_result[0] == "ADMIN"

        if is_workspace_admin:
            # ADMIN users bypass mtd_access - return all non-deleted projects
            query = text(
                """
            SELECT 
                p.id,
                p.name,
                p.description,
                p.created_at,
                p.created_by,
                p.status,
                u.name as created_by_name,
                'ADMIN' as user_access_level
            FROM instance01.mtd_project p
            JOIN instance01.mtd_users u ON p.created_by = u.id
            WHERE p.status != 'DELETED'
            ORDER BY p.created_at DESC
            """
            )
            result = db.execute(query).fetchall()
        else:
            # Non-admin: query via mtd_access table as before
            query = text(
                """
            SELECT 
                p.id,
                p.name,
                p.description,
                p.created_at,
                p.created_by,
                p.status,
                u.name as created_by_name,
                a.level as user_access_level
            FROM instance01.mtd_project p
            JOIN instance01.mtd_users u ON p.created_by = u.id
            JOIN instance01.mtd_access a ON p.id = a.entity_id 
              AND a.user_id = CAST(:user_id AS VARCHAR)
              AND a.entity_type = 'PROJECT'
            WHERE (a.expiration_date IS NULL OR a.expiration_date > CURRENT_TIMESTAMP)
              AND p.status != 'DELETED'
              AND a.level != 'NONE' 
            ORDER BY p.created_at DESC
            """
            )
            result = db.execute(query, {"user_id": user_id_str}).fetchall()

        # Convert SQLAlchemy Row objects to dictionaries and process binary fields
        projects = []
        for row in result:
            # Convert row to dictionary using _asdict() if available (SQLAlchemy 1.4+)
            if hasattr(row, "_asdict"):
                project_dict = row._asdict()
            else:
                # Fallback for older SQLAlchemy versions
                project_dict = dict(zip(row.keys(), row))

            # Convert UUID and datetime fields to strings
            project_id = None
            for key, value in project_dict.items():
                if isinstance(value, uuid.UUID):
                    project_dict[key] = str(value)
                    if key == "id":
                        project_id = project_dict[key]
                elif isinstance(value, (bytes, bytearray)):
                    project_dict[key] = value.hex()
                    if key == "id":
                        project_id = project_dict[key]
                elif isinstance(value, datetime):
                    project_dict[key] = value.isoformat()

            # Get users with access to this project (if admin/workspace admin)
            if is_workspace_admin or project_dict.get("user_access_level", "").lower() == "admin":
                users_query = text(
                    """
                SELECT DISTINCT u.id, u.name, u.email, u.role, a.level as access_level
                FROM instance01.mtd_access a
                JOIN instance01.mtd_users u ON a.user_id = u.id
                WHERE a.entity_type = 'PROJECT' 
                AND a.entity_id = CAST(:project_id AS uuid)
                AND a.level != 'NONE'
                """
                )
                users_result = db.execute(
                    users_query, {"project_id": project_id}
                ).fetchall()
                users = []
                for user_row in users_result:
                    user_dict = (
                        user_row._asdict()
                        if hasattr(user_row, "_asdict")
                        else dict(zip(user_row.keys(), user_row))
                    )
                    for k, v in user_dict.items():
                        if isinstance(v, uuid.UUID):
                            user_dict[k] = str(v)
                        elif isinstance(v, (bytes, bytearray)):
                            user_dict[k] = v.hex()
                    users.append(user_dict)

                project_dict["users"] = users

            # Get folders for this project
            if is_workspace_admin:
                # ADMIN sees all folders in each project
                folders_query = text(
                    """
                SELECT f.*, u.name as created_by_name, 'ADMIN' as user_access_level
                FROM instance01.mtd_folder f
                JOIN instance01.mtd_users u ON f.created_by = u.id
                WHERE f.project_id = CAST(:project_id AS uuid)
                AND f.status != 'DELETED'
                ORDER BY f.created_at DESC
                """
                )
                folders_result = db.execute(
                    folders_query, {"project_id": project_id}
                ).fetchall()
            else:
                # Non-admin: only folders with explicit access
                folders_query = text(
                    """
                SELECT f.*, u.name as created_by_name, a.level as user_access_level
                FROM instance01.mtd_folder f
                JOIN instance01.mtd_users u ON f.created_by = u.id
                JOIN instance01.mtd_access a ON f.id = a.entity_id
                WHERE f.project_id = CAST(:project_id AS uuid)
                AND a.user_id = :user_id
                AND a.entity_type = 'FOLDER'
                AND a.level != 'NONE'
                AND (a.expiration_date IS NULL OR a.expiration_date > CURRENT_TIMESTAMP)
                AND f.status != 'DELETED'
                ORDER BY f.created_at DESC
                """
                )
                folders_result = db.execute(
                    folders_query, {"project_id": project_id, "user_id": user_id_str}
                ).fetchall()

            folders = []
            for folder_row in folders_result:
                folder_dict = (
                    folder_row._asdict()
                    if hasattr(folder_row, "_asdict")
                    else dict(zip(folder_row.keys(), folder_row))
                )
                for k, v in folder_dict.items():
                    if isinstance(v, uuid.UUID):
                        folder_dict[k] = str(v)
                    elif isinstance(v, (bytes, bytearray)):
                        folder_dict[k] = v.hex()
                    elif isinstance(v, datetime):
                        folder_dict[k] = v.isoformat()
                folders.append(folder_dict)

            project_dict["folders"] = folders
            projects.append(project_dict)

        return projects

    except Exception as e:
        # Log the error and re-raise
        print(f"Error in get_projects_by_user_id: {str(e)}")
        raise


@router.get("/getProject/{project_id}", response_model=MessageResponse)
def get_project(project_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get a single project by its ID.
    
    **Endpoint**: GET /api/v1/project/getProject/{project_id}
    
    **Description**:
    Retrieves detailed information about a specific project by its UUID.
    
    **Path Parameters**:
        - project_id (str): UUID of the project (with or without hyphens)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Success" or "Project not found"
            - data (dict): Project object containing:
                - id (str): Project UUID in hex format
                - name (str): Project name
                - description (str): Project description
                - created_at (str): ISO timestamp
                - created_by (str): Creator UUID in hex format
                - status (str): ACTIVE/ARCHIVED/DELETED
                - created_by_name (str): Name of creator
    
    **Database Tables Used**:
        - mtd_project: Project details
        - mtd_users: Creator information
    
    **Example Response**:
        ```json
        {
            "message": "Success",
            "data": {
                "id": "a1b2c3d4e5f6...",
                "name": "Sales Analysis",
                "description": "Q4 sales process mining",
                "created_at": "2025-01-15T10:30:00",
                "created_by": "f6e5d4c3b2a1...",
                "status": "ACTIVE",
                "created_by_name": "John Doe"
            }
        }
        ```
    
    **Raises**:
        - Exception: Database errors or invalid UUID format
    """
    try:
        require_project_access(project_id, user_from_request(request), db, min_level="VIEWER")
        query = text(
            """
            SELECT p.id,
                   p.name,
                   p.description,
                   p.created_at,
                   p.created_by,
                   p.status,
                   u.name AS created_by_name
            FROM instance01.mtd_project p
            JOIN instance01.mtd_users u ON p.created_by = u.id
            WHERE p.id = CAST(:pid AS uuid)
            """
        )
        result = db.execute(query, {"pid": project_id}).fetchone()
        if not result:
            return MessageResponse(message="Project not found", data=None)
        project_dict = (
            result._asdict()
            if hasattr(result, "_asdict")
            else dict(zip(result.keys(), result))
        )
        for k, v in project_dict.items():
            if isinstance(v, uuid.UUID):
                project_dict[k] = str(v)
            elif isinstance(v, (bytes, bytearray)):
                project_dict[k] = v.hex()
            elif isinstance(v, datetime):
                project_dict[k] = v.isoformat()
        return MessageResponse(message="Success", data=project_dict)
    except Exception as e:
        print(f"Error in get_project: {e}")
        raise


@router.post("/createProject", response_model=MessageResponse)
def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create a new project in the mtd_project table.
    
    **Endpoint**: POST /api/v1/project/createProject
    
    **Description**:
    Creates a new project with the provided details. The project ID must be a valid UUID.
    
    **Request Body** (ProjectCreate):
        - id (str): UUID for the new project (required)
        - name (str): Project name (required)
        - description (str): Project description (optional)
        - created_at (str): ISO timestamp of creation (required)
        - created_by (str): UUID of the creator (required)
        - status (str): Project status - ACTIVE/ARCHIVED/DELETED (required)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Project created successfully"
            - data: None
    
    **Database Tables Modified**:
        - mtd_project: Inserts new project record
    
    **Example Request**:
        ```json
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "Sales Analysis",
            "description": "Q4 sales process mining",
            "created_at": "2025-01-15T10:30:00",
            "created_by": "f6e5d4c3-b2a1-0987-6543-210fedcba987",
            "status": "ACTIVE"
        }
        ```
    
    **Example Response**:
        ```json
        {
            "message": "Project created successfully",
            "data": null
        }
        ```
    
    **Notes**:
        - Transaction is rolled back on error
        - UUID hyphens are automatically handled
        - After creating a project, you typically need to grant access via grantProjectAccess
    
    **Raises**:
        - Exception: Database errors, constraint violations, or invalid UUID format
    """
    try:
        # Enforce license limit before creating project
        enforce_project_limit(db)
        
        # First validate user exists
        user_check = text("""
            SELECT id FROM instance01.mtd_users 
            WHERE id = :user_id
            """)
        if not db.execute(user_check, {"user_id": payload.created_by}).fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"User {payload.created_by}  does not exist"
            )
        
        insert_query = text(
            """
            INSERT INTO instance01.mtd_project(id, name, description, created_at, created_by, status)
            VALUES (CAST(:id AS uuid), :name, :description, :created_at, :created_by, :status)
            """
        )
        # Convert Pydantic model to dictionary
        payload_dict = payload.dict()
        db.execute(insert_query, payload_dict)
        
        # Update project counts in license data
        _update_project_counts(db, delta=1)
        log_admin_action(db, ACTION_PROJECT_CREATED, target_type="PROJECT", target_id=str(payload.id), details={"name": payload.name})
        
        db.commit()
        return MessageResponse(message="Project created successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in create_project: {e}")
        raise


@router.put("/editProject", response_model=MessageResponse)
def edit_project(
    payload: ProjectEdit, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Update an existing project's details.
    
    **Endpoint**: PUT /api/v1/project/editProject
    
    **Description**:
    Updates one or more fields of an existing project. Only provided fields are updated.
    
    **Request Body** (ProjectEdit):
        - id (str): UUID of the project to update (required)
        - name (str): New project name (optional)
        - description (str): New project description (optional)
        - status (str): New status - ACTIVE/ARCHIVED/DELETED (optional)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Project updated successfully" or "No valid fields to update"
            - data: None
    
    **Database Tables Modified**:
        - mtd_project: Updates specified fields
    
    **Example Request**:
        ```json
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "Updated Sales Analysis",
            "description": "Q4 2025 sales process mining"
        }
        ```
    
    **Example Response**:
        ```json
        {
            "message": "Project updated successfully",
            "data": null
        }
        ```
    
    **Notes**:
        - Only non-null fields in the payload are updated
        - Transaction is rolled back on error
        - Use deleteProject endpoint for soft deletion instead of setting status to DELETED
    
    **Raises**:
        - Exception: Database errors, project not found, or invalid UUID format
    """
    try:
        payload_dict = payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params = {"pid": payload.id}
        
        # Check if status is being changed
        status_changed = False
        old_status = None
        if "status" in payload_dict and payload_dict["status"] is not None:
            # Get current status
            status_q = text("SELECT status FROM instance01.mtd_project WHERE id = CAST(:pid AS uuid)")
            old_status = db.execute(status_q, {"pid": payload.id}).scalar()
            if old_status != payload_dict["status"]:
                status_changed = True
        
        for key in ("name", "description", "status"):
            if key in payload_dict and payload_dict[key] is not None:
                update_fields.append(f"{key} = :{key}")
                params[key] = payload_dict[key]
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        update_query = text(
            f"UPDATE instance01.mtd_project SET {', '.join(update_fields)} WHERE id = CAST(:pid AS uuid)"
        )
        db.execute(update_query, params)
        
        # Update project counts if status changed
        if status_changed:
            _update_project_counts(db, status_change={
                'old_status': old_status,
                'new_status': payload_dict["status"]
            })
        
        db.commit()
        return MessageResponse(message="Project updated successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in edit_project: {e}")
        raise


@router.delete("/deleteProject", response_model=MessageResponse)
def delete_project(
    payload: ProjectDelete, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Soft-delete a project by setting its status to 'DELETED'.

    **Endpoint**: DELETE /api/v1/project/deleteProject

    **Description**:
    Performs a soft delete by changing the project status to 'DELETED'. The project
    record remains in the database but will be filtered out from normal queries.

    **Request Body** (ProjectDelete):
        - id (str): UUID of the project to delete (required)

    **Returns**:
        - MessageResponse:
            - message (str): "Project deleted successfully"
            - data: None

    **Database Tables Modified**:
        - mtd_project: Updates status field to 'DELETED'
        - mtd_folder: Updates status field to 'DELETED' for all folders in the project

    **Example Request**:
        ```json
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        }
        ```

    **Example Response**:
        ```json
        {
            "message": "Project deleted successfully",
            "data": null
        }
        ```

    **Notes**:
        - This is a soft delete - data is not physically removed
        - Deleted projects won't appear in getProjectByUser results
        - All folders within the project are also soft-deleted (status set to 'DELETED')
        - Access records remain unchanged for audit purposes
        - Transaction is rolled back on error

    **Raises**:
        - Exception: Database errors, project not found, or invalid UUID format
    """
    try:
        # Get current status before deletion
        status_q = text("SELECT status FROM instance01.mtd_project WHERE id = CAST(:pid AS uuid)")
        old_status = db.execute(status_q, {"pid": payload.id}).scalar()
        print(f"[DEBUG] Deleting project {payload.id} with status: {old_status}")

        # Soft-delete all folders associated with this project
        delete_folders_query = text(
            """UPDATE instance01.mtd_folder
               SET status = 'DELETED'
               WHERE project_id = CAST(:pid AS uuid)
               AND UPPER(status) != 'DELETED'"""
        )
        folders_result = db.execute(delete_folders_query, {"pid": payload.id})
        deleted_folders_count = folders_result.rowcount
        print(f"[DEBUG] Soft-deleted {deleted_folders_count} folders for project {payload.id}")

        # Soft-delete the project
        delete_query = text(
            """UPDATE instance01.mtd_project SET status = 'DELETED' WHERE id = CAST(:pid AS uuid)"""
        )
        db.execute(delete_query, {"pid": payload.id})

        # Check how many active projects exist after the update
        debug_q = text("SELECT COUNT(*) FROM instance01.mtd_project WHERE UPPER(status) = 'ACTIVE'")
        debug_count = db.execute(debug_q).scalar()
        print(f"[DEBUG] Active projects after setting status to DELETED: {debug_count}")

        # Update project counts - both total and active counts need to be recalculated
        # Use delta=-1 to decrement total_project AND recalculate active count
        _update_project_counts(db, delta=-1)

        db.commit()
        return MessageResponse(message="Project deleted successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in delete_project: {e}")
        raise


@router.post("/grantProjectAccess", response_model=MessageResponse)
def grant_project_access(
    payload: Dict[str, Any], db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Grant or update access level to a user for a project.
    
    **Endpoint**: POST /api/v1/project/grantProjectAccess
    
    **Description**:
    Grants a user access to a project with a specified access level. If access already
    exists, it updates the level and expiration date. Also automatically grants the same
    access level to all folders within the project.
    
    **Request Body** (Dict):
        - entity_id (str): UUID of the project (required)
        - user_id (str): UUID of the user to grant access (required)
        - access_level (str): Access level - OWNER/ADMIN/ANALYST/VIEWER (required)
        - access_granted_date (str): ISO timestamp when access is granted (required)
        - access_granted_by (str): UUID of the user granting access (required)
        - access_expiration_date (str): ISO timestamp when access expires (optional, null for no expiration)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Access granted/updated successfully"
            - data: None
    
    **Database Tables Modified**:
        - mtd_access: Inserts/updates access record for project and all its folders
        - mtd_folder: Queries to find all folders in the project
    
    **Access Levels**:
        - OWNER: Full control including deletion and user management
        - ADMIN: Can manage users and edit project
        - ANALYST: Can edit project content
        - VIEWER: Read-only access
    
    **Example Request**:
        ```json
        {
            "entity_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "user_id": "f6e5d4c3-b2a1-0987-6543-210fedcba987",
            "access_level": "ANALYST",
            "access_granted_date": "2025-01-15T10:30:00",
            "access_granted_by": "12345678-90ab-cdef-1234-567890abcdef",
            "access_expiration_date": null
        }
        ```
    
    **Example Response**:
        ```json
        {
            "message": "Access granted/updated successfully",
            "data": null
        }
        ```
    
    **Notes**:
        - Empty string expiration_date is automatically converted to null
        - Automatically grants same access level to all folders in the project
        - Transaction is rolled back on error if any operation fails
        - Constraint: (entity_id, entity_type, user_id) must be unique
    
    **Raises**:
        - Exception: Database errors, constraint violations, or invalid UUID format
    """
    try:
        # Convert empty string expiration_date to None
        if "expiration_date" in payload and payload["expiration_date"] == "":
            payload["expiration_date"] = None

        #print(f"[ProjectAccess] Searching for user: {payload['user_id']} (type: {type(payload['user_id'])})")
        #print(f"[ProjectAccess] Searching in mtd_access for entity: {payload['entity_id']}")
        check_query = text(
            """
            SELECT COUNT(*) as count 
            FROM instance01.mtd_access 
            WHERE entity_id = :entity_id
            AND entity_type = 'PROJECT' 
            AND user_id = :user_id
            """
        )
        result = db.execute(check_query, payload).fetchone()
        #print(f"[ProjectAccess] Query result: {result}")
        exists = result[0] > 0 if result else False
        #print(f"[ProjectAccess] Access exists: {exists}")

        if exists:
            # Update existing access
            update_query = text(
                """
                UPDATE instance01.mtd_access 
                SET level = :access_level, 
                    expiration_date = :access_expiration_date,
                    granted_date = :access_granted_date,
                    granted_by = :access_granted_by
                WHERE entity_id = :entity_id
                AND entity_type = 'PROJECT' 
                AND user_id = :user_id
                """
            )
            db.execute(update_query, payload)
        else:
            # Insert new access
            insert_query = text(
                """
                INSERT INTO instance01.mtd_access(entity_id, entity_type, user_id, level, granted_date, granted_by, expiration_date)
                VALUES (
                    :entity_id, 
                    'PROJECT', 
                    :user_id, 
                    :access_level,
                    :access_granted_date, 
                    :access_granted_by, 
                    :access_expiration_date
                )
                """
            )
            db.execute(insert_query, payload)
        
        # Grant access to all folders in the project
        folders_query = text(
            """
            SELECT id 
            FROM instance01.mtd_folder 
            WHERE project_id = :entity_id
            """
        )
        folders = db.execute(folders_query, {"entity_id": payload["entity_id"]}).fetchall()
        
        # Grant access to each folder
        for folder in folders:
            folder_id = str(folder[0]) if isinstance(folder[0], uuid.UUID) else folder[0]
            
            # Check if folder access exists
            check_folder_query = text(
                """
                SELECT COUNT(*) as count 
                FROM instance01.mtd_access 
                WHERE entity_id = :folder_id 
                AND entity_type = 'FOLDER' 
                AND user_id = :user_id
                """
            )
            folder_result = db.execute(
                check_folder_query, {
                "folder_id": folder_id,
                "user_id": payload["user_id"]
            }).fetchone()
            folder_exists = folder_result[0] > 0 if folder_result else False
            
            if folder_exists:
                # Update existing folder access
                update_folder_query = text(
                    """
                    UPDATE instance01.mtd_access 
                    SET level = :access_level, 
                        expiration_date = :access_expiration_date,
                        granted_date = :access_granted_date,
                        granted_by = :access_granted_by
                    WHERE entity_id = :folder_id 
                    AND entity_type = 'FOLDER' 
                    AND user_id = :user_id
                    """
                )
                db.execute(update_folder_query, {
                    "folder_id": folder_id,
                    "user_id": payload["user_id"],
                    "access_level": payload["access_level"],
                    "access_expiration_date": payload.get("access_expiration_date"),
                    "access_granted_date": payload["access_granted_date"],
                    "access_granted_by": payload["access_granted_by"]
                })
            else:
                # Insert new folder access
                insert_folder_query = text(
                    """
                    INSERT INTO instance01.mtd_access(entity_id, entity_type, user_id, level, granted_date, granted_by, expiration_date)
                    VALUES (
                        CAST(:folder_id AS uuid), 
                        'FOLDER', 
                        :user_id, 
                        :access_level, 
                        :access_granted_date, 
                        :access_granted_by, 
                        :access_expiration_date
                    )
                    """
                )
                db.execute(insert_folder_query, {
                    "folder_id": folder_id,
                    "user_id": payload["user_id"],
                    "access_level": payload["access_level"],
                    "access_granted_date": payload["access_granted_date"],
                    "access_granted_by": payload["access_granted_by"],
                    "access_expiration_date": payload.get("access_expiration_date")
                })
        
        log_admin_action(db, ACTION_ACCESS_GRANTED, target_type="PROJECT", target_id=str(payload.get('entity_id')), details={"user_id": payload.get('user_id'), "access_level": payload.get('access_level')})
        db.commit()
        return MessageResponse(message="Access granted/updated successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in grant_project_access: {e}")
        raise


@router.put("/revokeProjectAccess", response_model=MessageResponse)
def revoke_project_access(
    payload: Dict[str, Any], db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Revoke a user's access to a project by setting level to 'NONE'.
    
    **Endpoint**: PUT /api/v1/project/revokeProjectAccess
    
    **Description**:
    Revokes a user's access to a project by setting their access level to 'NONE'.
    Also revokes access to all folders within the project.
    The access records remain in the database for audit purposes.
    
    **Request Body** (Dict):
        - entity_id (str): UUID of the project (required)
        - user_id (str): UUID of the user whose access to revoke (required)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Access revoked successfully"
            - data: None
    
    **Database Tables Modified**:
        - mtd_access: Updates level field to 'NONE' for project and all its folders
        - mtd_folder: Queries to find all folders in the project
    
    **Example Request**:
        ```json
        {
            "entity_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "user_id": "f6e5d4c3-b2a1-0987-6543-210fedcba987"
        }
        ```
    
    **Example Response**:
        ```json
        {
            "message": "Access revoked successfully",
            "data": null
        }
        ```
    
    **Notes**:
        - Sets level to 'NONE' rather than deleting the record (audit trail)
        - Automatically revokes access to all folders in the project
        - User will no longer see the project or its folders
        - Transaction is rolled back on error if any operation fails
    
    **Raises**:
        - Exception: Database errors, access record not found, or invalid UUID format
    """
    try:
        update_query = text(
            """
            UPDATE instance01.mtd_access 
            SET level = 'NONE' 
            WHERE entity_id = CAST(:entity_id AS uuid) 
            AND user_id = :user_id 
            AND entity_type = 'PROJECT'
            """
        )
        db.execute(update_query, payload)
        
        # Revoke access to all folders in the project
        folders_query = text(
            """
            SELECT id 
            FROM instance01.mtd_folder 
            WHERE project_id = CAST(:entity_id AS uuid)
            """
        )
        folders = db.execute(folders_query, {"entity_id": payload["entity_id"]}).fetchall()
        
        # Revoke access to each folder
        for folder in folders:
            folder_id = str(folder[0]) if isinstance(folder[0], uuid.UUID) else folder[0]
            
            update_folder_query = text(
                """
                UPDATE instance01.mtd_access 
                SET level = 'NONE' 
                WHERE entity_id = CAST(:folder_id AS uuid) 
                AND user_id = :user_id 
                AND entity_type = 'FOLDER'
                """
            )
            db.execute(update_folder_query, {
                "folder_id": folder_id,
                "user_id": payload["user_id"]
            })
        
        log_admin_action(db, ACTION_ACCESS_REVOKED, target_type="PROJECT", target_id=str(payload.get('entity_id')), details={"user_id": payload.get('user_id')})
        db.commit()
        return MessageResponse(message="Access revoked successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in revoke_project_access: {e}")
        raise


@router.put("/changeProjectAccess", response_model=MessageResponse)
def change_project_access(
    payload: Dict[str, Any], db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Change an existing user's access level for a project.
    
    **Endpoint**: PUT /api/v1/project/changeProjectAccess
    
    **Description**:
    Updates the access level of a user who already has access to a project.
    Use this to promote/demote users between access levels.
    
    **Request Body** (Dict):
        - entity_id (str): UUID of the project (required)
        - user_id (str): UUID of the user whose access level to change (required)
        - access_level (str): New access level - OWNER/ADMIN/ANALYST/VIEWER (required)
    
    **Returns**:
        - MessageResponse:
            - message (str): "Access level changed successfully"
            - data: None
    
    **Database Tables Modified**:
        - mtd_access: Updates level field
    
    **Access Levels**:
        - OWNER: Full control including deletion and user management
        - ADMIN: Can manage users and edit project
        - ANALYST: Can edit project content
        - VIEWER: Read-only access
    
    **Example Request**:
        ```json
        {
            "entity_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "user_id": "f6e5d4c3-b2a1-0987-6543-210fedcba987",
            "access_level": "ADMIN"
        }
        ```
    
    **Example Response**:
        ```json
        {
            "message": "Access level changed successfully",
            "data": null
        }
        ```
    
    **Notes**:
        - User must already have access (use grantProjectAccess for new users)
        - Does not update expiration_date (use grantProjectAccess for that)
        - Transaction is rolled back on error
        - Only affects PROJECT entity type access
    
    **Raises**:
        - Exception: Database errors, access record not found, or invalid UUID format
    """
    try:
        update_query = text(
            """
            UPDATE instance01.mtd_access 
            SET level = :access_level 
            WHERE entity_id = CAST(:entity_id AS uuid) 
            AND user_id = :user_id 
            AND entity_type = 'PROJECT'
            """
        )
        db.execute(update_query, payload)
        log_admin_action(db, ACTION_ACCESS_CHANGED, target_type="PROJECT", target_id=str(payload.get('entity_id')), details={"user_id": payload.get('user_id'), "new_level": payload.get('access_level')})
        db.commit()
        return MessageResponse(message="Access level changed successfully", data=None)
    except Exception as e:
        db.rollback()
        print(f"Error in change_project_access: {e}")
        raise
