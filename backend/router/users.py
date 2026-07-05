from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database import get_db
from fastapi import Depends, APIRouter, Security, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import text
from schemas import (
    UserCreate,
    UserEdit,
    UserDelete,
    UserOut,
    MessageResponse,
)
import uuid
import json
from fastapi import HTTPException
from utils.firebase_auth import get_firebase_auth_manager
from utils.audit_logger import log_admin_action, ACTION_USER_CREATED, ACTION_USER_EDITED, ACTION_USER_DELETED, ACTION_ROLE_CHANGED
from utils.license_enforcement import enforce_user_limit
import os
from pathlib import Path


router = APIRouter(prefix="/api/v1/user", tags=["users"])


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _hexify(val):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(val, uuid.UUID):
        return str(val)
    elif isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val


def _update_license_counts(db: Session, role: str, delta: int, update_total_user: bool = True):
    """
    Update license data counts when users are added/removed or roles change
    
    Args:
        db: Database session
        role: User role (ADMIN, ANALYST, VIEWER)
        delta: +1 for add, -1 for remove
        update_total_user: Whether to update total_user count (True for add/remove, False for role change)
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
        
        # Update counts based on role
        if role == "ADMIN":
            license_data["active_admin"] = str(int(license_data.get("active_admin", "0")) + delta)
        elif role == "ANALYST":
            license_data["active_analyst"] = str(int(license_data.get("active_analyst", "0")) + delta)
        else:  # VIEWER
            license_data["active_viewer"] = str(int(license_data.get("active_viewer", "0")) + delta)
            
        # Update total active users (sum of all role counts)
        license_data["total_active_user"] = str(
            int(license_data.get("active_admin", "0")) +
            int(license_data.get("active_analyst", "0")) +
            int(license_data.get("active_viewer", "0"))
        )
        
        # Update total users (all users regardless of role) when adding/removing
        if update_total_user:
            license_data["total_user"] = str(int(license_data.get("total_user", "0")) + delta)
        
        # Save updated license data
        upd_q = text(
            "UPDATE instance01.data_collection SET data = CAST(:data AS jsonb) WHERE title = 'license'"
        )
        db.execute(upd_q, {"data": json.dumps(license_data)})
    except Exception as exc:
        print(f"Error updating license counts: {exc}")
        raise


# ---------------------------------------------------------------------------
# CRUD ENDPOINTS
# ---------------------------------------------------------------------------


@router.post("/createUser", response_model=MessageResponse)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create a new user.
    
    **HTTP Method:** POST
    **Path:** /api/v1/user/createUser
    
    **Parameters:**
    - payload: UserCreate - User object to create
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "John Doe",
      "email": "john.doe@example.com",
      "role": "ADMIN"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "User created successfully",
      "data": null
    }
    ```
    """
    try:
        # Enforce license limit before creating user
        enforce_user_limit(db, payload.role)
        
        insert_q = text(
            """
            INSERT INTO instance01.mtd_users(id, name, email, role)
            VALUES (:id, :name, :email, :role)
            """
        )
        db.execute(insert_q, payload.dict())
        # Add new user count BEFORE commit (update_total_user=True for new user)
        _update_license_counts(db, payload.role, 1, update_total_user=True)
        log_admin_action(db, ACTION_USER_CREATED, target_type="USER", target_id=str(payload.id), details={"email": payload.email, "role": payload.role})
        db.commit()
        return {"message": "User created successfully", "data": None}
    except Exception as exc:
        db.rollback()
        print(f"Error in create_user: {exc}")
        raise


@router.put("/editUser", response_model=MessageResponse)
def edit_user(payload: UserEdit, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Update user details (name, email, role).
    
    **HTTP Method:** PUT
    **Path:** /api/v1/user/editUser
    
    **Parameters:**
    - payload: UserEdit - User object with id and fields to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "John Smith",
      "email": "john.smith@example.com",
      "role": "USER"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "User updated successfully",
      "data": null
    }
    ```
    """
    try:
        # Get current role before update
        current_role_q = text(
            "SELECT role FROM instance01.mtd_users WHERE id = :uid"
        )
        current_role = db.execute(current_role_q, {"uid": payload.id}).scalar()
        
        payload_dict = payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params = {"uid": payload.id}
        for key in ("name", "email", "role"):
            if key in payload_dict and payload_dict[key] is not None:
                update_fields.append(f"{key} = :{key}")
                params[key] = payload_dict[key]
                
        if not update_fields:
            return {"message": "No valid fields to update", "data": None}
            
        update_q = text(
            f"UPDATE instance01.mtd_users SET {', '.join(update_fields)} WHERE id = :uid"
        )
        db.execute(update_q, params)
        
        # If role changed, update license counts (don't update total_user for role changes)
        if "role" in payload_dict and payload_dict["role"] != current_role:
            _update_license_counts(db, current_role, -1, update_total_user=False)  # Remove old role
            _update_license_counts(db, payload_dict["role"], 1, update_total_user=False)  # Add new role
            log_admin_action(db, ACTION_ROLE_CHANGED, target_type="USER", target_id=str(payload.id), details={"old_role": current_role, "new_role": payload_dict["role"]})
        else:
            log_admin_action(db, ACTION_USER_EDITED, target_type="USER", target_id=str(payload.id), details=payload_dict)
            
        db.commit()
        return {"message": "User updated successfully", "data": None}
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_user: {exc}")
        raise


@router.delete("/deleteUser", response_model=MessageResponse)
def delete_user(payload: UserDelete, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Delete a user record (hard delete).
    
    **HTTP Method:** DELETE
    **Path:** /api/v1/user/deleteUser
    
    **Parameters:**
    - payload: UserDelete - User object with id to delete
    
    **Returns:**
    - MessageResponse with success message
    
    **Note:** This is a hard delete. Cascade constraints may apply.
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "User deleted successfully",
      "data": null
    }
    ```
    """
    try:
        # Get user role and status before deletion
        user_q = text(
            "SELECT role, status FROM instance01.mtd_users WHERE id = :uid"
        )
        user_res = db.execute(user_q, {"uid": payload.id}).fetchone()
        
        if user_res:
            role = user_res[0]
            status = user_res[1]
            
            # Only decrement license count if user is not already inactive
            if status != "inactive":
                _update_license_counts(db, role, -1, update_total_user=True)

        # Remove access records to avoid foreign key constraints
        del_access_q = text("DELETE FROM instance01.mtd_access WHERE user_id = :uid")
        db.execute(del_access_q, {"uid": payload.id})

        # Hard delete: Remove user from database
        hard_del_q = text("DELETE FROM instance01.mtd_users WHERE id = :uid")
        db.execute(hard_del_q, {"uid": payload.id})
        # Note: Firebase deletion and mtd_access cleanup deferred to background job
        # firebase_manager = get_firebase_auth_manager(...)
        # success, error_msg = firebase_manager.delete_user(payload.id)
        log_admin_action(db, ACTION_USER_DELETED, target_type="USER", target_id=str(payload.id), details={"role": role if user_res else None})
        
        db.commit()
        return {"message": "User deleted successfully", "data": None}
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_user: {exc}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete user: {str(exc)}"
        )


@router.get("/getUser/{user_id}", response_model=MessageResponse)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Fetch a user by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/user/getUser/{user_id}
    
    **Parameters:**
    - user_id: str - UUID of the user
    
    **Returns:**
    - MessageResponse with user data
    
    **Example Request:**
    ```
    GET /api/v1/user/getUser/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "role": "ADMIN"
      }
    }
    ```
    """
    try:
        sel_q = text(
            """
            SELECT id, name, email, role FROM instance01.mtd_users
            WHERE id = :uid
            """
        )
        res = db.execute(sel_q, {"uid": user_id}).fetchone()
        if not res:
            return {"message": "User not found", "data": None}
        user_dict = (
            res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        )
        # Convert UUID objects to strings
        for k, v in user_dict.items():
            user_dict[k] = _hexify(v)
        return MessageResponse(message="Success", data=user_dict)
    except Exception as exc:
        print(f"Error in get_user: {exc}")
        raise

@router.get('/getUserByEmail/{email}', response_model=MessageResponse)
def get_user_by_email(email: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Fetch a user by email address.
    
    **HTTP Method:** GET
    **Path:** /api/v1/user/getUserByEmail/{email}
    
    **Parameters:**
    - email: str - Email address of the user
    
    **Returns:**
    - MessageResponse with user data
    
    **Example Request:**
    ```
    GET /api/v1/user/getUserByEmail/john.doe@example.com
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "role": "ADMIN"
      }
    }
    ```
    """
    try:
        sel_q = text(
            """
            SELECT id, name, email, role FROM instance01.mtd_users
            WHERE email = :email
            """
        )
        res = db.execute(sel_q, {"email": email}).fetchone()
        if not res:
            return {"message": "User not found", "data": None}
        user_dict = (
            res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        )
        # Convert UUID objects to strings
        for k, v in user_dict.items():
            user_dict[k] = _hexify(v)
        return MessageResponse(message="Success", data=user_dict)
    except Exception as exc:
        print(f"Error in get_user_by_email: {exc}")
        raise

@router.get("/getUsersByProject/{project_id}", response_model=List[UserOut])
def get_users_by_project(
    project_id: uuid.UUID, db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get all users with access to a specific project.
    
    **HTTP Method:** GET
    **Path:** /api/v1/user/getUsersByProject/{project_id}
    
    **Parameters:**
    - project_id: str - UUID of the project
    
    **Returns:**
    - List[UserOut] - List of users with their access levels
    
    **Example Request:**
    ```
    GET /api/v1/user/getUsersByProject/770e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "role": "ADMIN",
        "access_level": "OWNER"
      }
    ]
    ```
    """
    try:
        query = text(
            """
            SELECT DISTINCT u.id, u.name, u.email, u.role, a.level AS access_level
            FROM instance01.mtd_access a
            JOIN instance01.mtd_users u ON a.user_id = u.id
            WHERE a.entity_type = 'PROJECT'
            AND a.entity_id = CAST(:pid AS uuid)
            """
        )
        rows = db.execute(query, {"pid": project_id}).fetchall()
        users = []
        for row in rows:
            user_d = (
                row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            )
            for k, v in user_d.items():
                user_d[k] = _hexify(v)
            users.append(user_d)
        return users
    except Exception as exc:
        print(f"Error in get_users_by_project: {exc}")
        raise

@router.get("/getAllUsers", response_model=List[UserOut])
def get_all_users(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get all users with full details (requires admin privileges)
    """
    try:
        query = text("SELECT id, name, email, role FROM instance01.mtd_users")
        rows = db.execute(query).fetchall()
        users = []
        for row in rows:
            user_d = (
                row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            )
            for k, v in user_d.items():
                user_d[k] = _hexify(v)
            users.append(user_d)
        return users
    except Exception as exc:
        print(f"Error in get_all_users: {exc}")
        raise

@router.get("/getUserEmails", response_model=List[Dict[str, str]])
def get_user_emails(db: Session = Depends(get_db)) -> List[Dict[str, str]]:
    """
    Get only user emails for autocomplete purposes
    Returns: List of {id, email} objects
    """
    try:
        query = text("SELECT id, email FROM instance01.mtd_users")
        rows = db.execute(query).fetchall()
        return [
            {"id": str(row[0]), "email": row[1]} 
            for row in rows
        ]
    except Exception as exc:
        print(f"Error in get_user_emails: {exc}")
        raise

@router.get("/getAllUsersWithAccess")
def get_all_users_with_access(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get all users grouped by access status with their comprehensive access information.
    
    **HTTP Method:** GET
    **Path:** /api/v1/user/getAllUsersWithAccess
    
    **Returns:**
    - Object with users_with_access and users_without_access arrays
    
    **Example Response:**
    ```json
    {
      "users_with_access": [
        {
          "id": "550e8400-e29b-41d4-a716-446655440000",
          "name": "John Doe",
          "email": "john.doe@example.com",
          "role": "ADMIN",
          "projects": [
            {
              "project_id": "770e8400-e29b-41d4-a716-446655440000",
              "project_name": "Project Alpha",
              "access_level": "ADMIN",
              "access_type": "PROJECT",
              "folders": []
            }
          ]
        }
      ],
      "users_without_access": {
        "ADMIN": [...],
        "ANALYST": [...],
        "VIEWER": [...]
      }
    }
    ```
    """
    try:
        # Get all users
        users_query = text("SELECT id, name, email, role FROM instance01.mtd_users")
        users_rows = db.execute(users_query).fetchall()
        
        users_with_access = []
        users_without_access = {"ADMIN": [], "ANALYST": [], "VIEWER": []}
        
        for user_row in users_rows:
            user_dict = (
                user_row._asdict() if hasattr(user_row, "_asdict") 
                else dict(zip(user_row.keys(), user_row))
            )
            
            # Hexify user fields
            for k, v in user_dict.items():
                user_dict[k] = _hexify(v)
            
            user_id = user_dict['id']
            
            # Get all access records for this user
            access_query = text(
                """
                SELECT 
                    a.entity_id,
                    a.entity_type,
                    a.level as access_level,
                    a.granted_date,
                    a.expiration_date,
                    CASE 
                        WHEN a.entity_type = 'PROJECT' THEN p.name
                        WHEN a.entity_type = 'FOLDER' THEN f.name
                        ELSE NULL
                    END as entity_name,
                    CASE 
                        WHEN a.entity_type = 'FOLDER' THEN f.project_id
                        ELSE a.entity_id
                    END as project_id,
                    CASE 
                        WHEN a.entity_type = 'FOLDER' THEN p2.name
                        WHEN a.entity_type = 'PROJECT' THEN p.name
                        ELSE NULL
                    END as project_name
                FROM instance01.mtd_access a
                LEFT JOIN instance01.mtd_project p ON a.entity_id = p.id AND a.entity_type = 'PROJECT'
                LEFT JOIN instance01.mtd_folder f ON a.entity_id = f.id AND a.entity_type = 'FOLDER'
                LEFT JOIN instance01.mtd_project p2 ON f.project_id = p2.id
                WHERE a.user_id = :user_id
                AND a.level != 'NONE'
                AND (a.expiration_date IS NULL OR a.expiration_date > CURRENT_TIMESTAMP)
                ORDER BY project_name, a.entity_type DESC, a.granted_date DESC
                """
            )
            
            access_rows = db.execute(access_query, {"user_id": user_id}).fetchall()
            
            if len(access_rows) > 0:
                # User has access - organize by projects
                projects_map = {}
                
                for access_row in access_rows:
                    access_dict = (
                        access_row._asdict() if hasattr(access_row, "_asdict") 
                        else dict(zip(access_row.keys(), access_row))
                    )
                    
                    # Hexify access fields
                    for k, v in access_dict.items():
                        access_dict[k] = _hexify(v)
                    
                    project_id = access_dict['project_id']
                    project_name = access_dict['project_name']
                    
                    if project_id not in projects_map:
                        projects_map[project_id] = {
                            'project_id': project_id,
                            'project_name': project_name,
                            'access_level': None,
                            'access_type': 'PARTIAL',  # Default to partial
                            'folders': []
                        }
                    
                    if access_dict['entity_type'] == 'PROJECT':
                        # User has project-level access
                        projects_map[project_id]['access_level'] = access_dict['access_level']
                        projects_map[project_id]['access_type'] = 'PROJECT'
                    elif access_dict['entity_type'] == 'FOLDER':
                        # User has folder-level access
                        projects_map[project_id]['folders'].append({
                            'folder_id': access_dict['entity_id'],
                            'folder_name': access_dict['entity_name'],
                            'access_level': access_dict['access_level']
                        })
                        # Set project access level to first folder's level if not set
                        if not projects_map[project_id]['access_level']:
                            projects_map[project_id]['access_level'] = access_dict['access_level']
                
                user_dict['projects'] = list(projects_map.values())
                users_with_access.append(user_dict)
            else:
                # User has no access - group by role
                user_role = user_dict.get('role', 'VIEWER').upper()
                if user_role not in users_without_access:
                    users_without_access[user_role] = []
                users_without_access[user_role].append({
                    'id': user_dict['id'],
                    'name': user_dict['name'],
                    'email': user_dict['email'],
                    'role': user_dict['role']
                })
        
        return {
            'users_with_access': users_with_access,
            'users_without_access': users_without_access
        }
    except Exception as exc:
        print(f"Error in get_all_users_with_access: {exc}")
        raise