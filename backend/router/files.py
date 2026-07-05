from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database import get_db
from fastapi import Depends, APIRouter, Request
from sqlalchemy import text
from schemas import (
    FileCreate,
    FileEdit,
    FileDelete,
    FileOut,
    MessageResponse,
)
from fastapi import HTTPException, status
import uuid
import json

from security.policy import current_user_id, require_folder_access, user_from_request

router = APIRouter(prefix="/api/v1/file", tags=["files"])


def _hexify(val):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(val, uuid.UUID):
        return str(val)
    elif isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val
def _require_file_access(file_id: uuid.UUID | str, request: Request, db: Session, min_level: str = "VIEWER") -> str:
    row = db.execute(
        text("SELECT parent_folder_id FROM instance01.mtd_file WHERE id = CAST(:fid AS uuid) AND COALESCE(status, 'ACTIVE') != 'DELETED'"),
        {"fid": file_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    folder_id = row[0] if not hasattr(row, "parent_folder_id") else row.parent_folder_id
    require_folder_access(folder_id, user_from_request(request), db, min_level=min_level)
    return str(folder_id)


@router.post("/createFile", response_model=MessageResponse)
def create_file(payload: FileCreate, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Create a new file record.
    
    **HTTP Method:** POST
    **Path:** /api/v1/file/createFile
    
    **Parameters:**
    - payload: FileCreate - File object to create
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "sales_data.csv",
      "created_at": "2024-01-15T10:30:00Z",
      "uploaded_by": "660e8400-e29b-41d4-a716-446655440000",
      "status": "ACTIVE",
      "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
      "originalName": "Sales Data 2024.csv"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "File created successfully",
      "data": null
    }
    ```
    """
    try:
        user = user_from_request(request)
        require_folder_access(payload.parent_folder_id, user, db, min_level="ANALYST")
        payload_data = payload.dict()
        payload_data["uploaded_by"] = current_user_id(user)
        q = text(
            """
            INSERT INTO instance01.mtd_file(id, name, created_at, uploaded_by, status, parent_folder_id, original_name)
            VALUES (CAST(:id AS uuid), :name, :created_at, :uploaded_by,
                    :status, CAST(:parent_folder_id AS uuid), :originalName)
            """
        )
        db.execute(q, payload_data)
        db.commit()
        return MessageResponse(message="File created successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in create_file: {exc}")
        raise


@router.put("/editFile", response_model=MessageResponse)
def edit_file(payload: FileEdit, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Update file metadata fields.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/file/editFile
    
    **Parameters:**
    - payload: FileEdit - File object with id and fields to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "updated_sales_data.csv",
      "status": "PROCESSING"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "File updated successfully",
      "data": null
    }
    """
    try:
        _require_file_access(payload.id, request, db, min_level="ANALYST")
        payload_dict = payload.dict(exclude_unset=True)
        update_fields: List[str] = []
        params = {"fid": payload.id}
        
        # SECURITY: Whitelist of allowed fields to prevent SQL injection
        # Map payload keys to actual database column names
        ALLOWED_FIELDS = {
            "name": "name",
            "originalName": "original_name",
            "status": "status"
        }
        
        # Only process whitelisted fields
        for key in ("name", "originalName", "status"):
            if key in payload_dict and payload_dict[key] is not None:
                # Validate key is in whitelist (extra safety check)
                if key not in ALLOWED_FIELDS:
                    continue
                
                col = ALLOWED_FIELDS[key]  # Use mapped column name
                update_fields.append(f"{col} = :{key}")
                params[key] = payload_dict[key]
        
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        
        # SECURITY: Build query with whitelisted field names only
        q = text(
            f"UPDATE instance01.mtd_file SET {', '.join(update_fields)} WHERE id = CAST(:fid AS uuid)"
        )
        db.execute(q, params)
        db.commit()
        return MessageResponse(message="File updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_file: {exc}")
        raise


@router.put("/deleteFile", response_model=MessageResponse)
def delete_file(payload: FileDelete, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Soft delete a file by marking it as DELETED.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/file/deleteFile
    
    **Parameters:**
    - payload: FileDelete - File object with id to delete
    
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
      "message": "File deleted successfully",
      "data": null
    }
    ```
    """
    try:
        _require_file_access(payload.id, request, db, min_level="ANALYST")
        q = text(
            "UPDATE instance01.mtd_file SET status = 'DELETED' WHERE id = CAST(:fid AS uuid)"
        )
        db.execute(q, {"fid": payload.id})
        db.commit()
        return MessageResponse(message="File deleted successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_file: {exc}")
        raise


@router.get("/getFile/{file_id}", response_model=MessageResponse)
def get_file(file_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get a single file by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/file/getFile/{file_id}
    
    **Parameters:**
    - file_id: str - UUID of the file
    
    **Returns:**
    - MessageResponse with file data
    
    **Example Request:**
    ```
    GET /api/v1/file/getFile/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "sales_data.csv",
        "created_at": "2024-01-15T10:30:00",
        "uploaded_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "original_name": "Sales Data 2024.csv"
      }
    }
    ```
    """
    try:
        _require_file_access(file_id, request, db, min_level="VIEWER")
        q = text("SELECT * FROM instance01.mtd_file WHERE id = CAST(:fid AS uuid)")
        res = db.execute(q, {"fid": file_id}).fetchone()
        if not res:
            return MessageResponse(message="File not found", data=None)
        d = res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        for k, v in d.items():
            if k == "created_at" and v is not None:
                d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
            else:
                d[k] = _hexify(v)
        return MessageResponse(message="Success", data=d)
    except Exception as exc:
        print(f"Error in get_file: {exc}")
        raise


@router.get("/getFilesByFolder/{folder_id}", response_model=List[FileOut])
def get_files_by_folder(folder_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> List[FileOut]:
    """
    Get all files in a specific folder.
    
    **HTTP Method:** GET
    **Path:** /api/v1/file/getFilesByFolder/{folder_id}
    
    **Parameters:**
    - folder_id: str - UUID of the parent folder
    
    **Returns:**
    - List[FileOut] - List of file objects
    
    **Example Request:**
    ```
    GET /api/v1/file/getFilesByFolder/770e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "sales_data.csv",
        "created_at": "2024-01-15T10:30:00",
        "uploaded_by": "660e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "parent_folder_id": "770e8400-e29b-41d4-a716-446655440000",
        "original_name": "Sales Data 2024.csv"
      }
    ]
    ```
    """
    try:
        require_folder_access(folder_id, user_from_request(request), db, min_level="VIEWER")
        q = text(
            "SELECT * FROM instance01.mtd_file WHERE parent_folder_id = CAST(:fid AS uuid)"
        )
        rows = db.execute(q, {"fid": folder_id}).fetchall()
        out = []
        for row in rows:
            d = row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            for k, v in d.items():
                if k == "created_at" and v is not None:
                    d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
                else:
                    d[k] = _hexify(v)
            out.append(d)
        return out
    except Exception as exc:
        print(f"Error in get_files_by_folder: {exc}")
        raise


@router.delete(
    "/deleteFileByFolder/{folder_id}/{file_id}", response_model=MessageResponse
)
def delete_file_by_folder(
    folder_id: uuid.UUID, file_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Delete a specific file from a specific folder and update folder entities

    Args:
        folder_id: UUID of the folder
        file_id: UUID of the file to delete
        db: Database session

    Returns:
        MessageResponse with success/failure message
    """
    try:
        require_folder_access(folder_id, user_from_request(request), db, min_level="ANALYST")
        # 1) Ensure the folder exists
        folder_check_q = text(
            """
            SELECT COUNT(*) AS cnt
            FROM instance01.mtd_folder
            WHERE id = CAST(:folder_id AS uuid)
            """
        )
        folder_res = db.execute(folder_check_q, {"folder_id": folder_id}).fetchone()
        if folder_res.cnt == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Folder with ID {folder_id} not found",
            )

        # 2) Mark the file as DELETED in mtd_file (soft-delete)
        file_delete_q = text(
            """
            UPDATE instance01.mtd_file
            SET status = 'DELETED'
            WHERE id = CAST(:file_id AS uuid)
            """
        )
        db.execute(file_delete_q, {"file_id": file_id})

        # 2b) Remove the file entry from the folder.entities -> files JSON object
        # Get current entities
        get_entities_q = text(
            """
            SELECT entities
            FROM instance01.mtd_folder
            WHERE id = CAST(:folder_id AS uuid)
            """
        )
        entities_res = db.execute(get_entities_q, {"folder_id": folder_id}).fetchone()
        # Handle both dict (JSONB) and string (TEXT) types
        if entities_res and entities_res.entities:
            if isinstance(entities_res.entities, str):
                current_entities = json.loads(entities_res.entities)
            else:
                current_entities = entities_res.entities
        else:
            current_entities = {}

        # Remove file from entities
        if "files" in current_entities and file_id.replace("-", "") in current_entities["files"]:
            del current_entities["files"][file_id.replace("-", "")]
        
        # Update folder entities
        update_folder_q = text(
            """
            UPDATE instance01.mtd_folder
            SET entities = CAST(:entities AS jsonb)
            WHERE id = CAST(:folder_id AS uuid)
            """
        )
        db.execute(update_folder_q, {"folder_id": folder_id, "entities": json.dumps(current_entities)})

        # 3) Fetch all table IDs whose parent_id is the given file ID
        fetch_tables_q = text(
            """
            SELECT id::text AS tid_hex
            FROM instance01.mtd_table
            WHERE parent_id = CAST(:file_id AS uuid)
            """
        )
        table_rows = db.execute(fetch_tables_q, {"file_id": file_id}).fetchall()
        table_ids: List[str] = [row.tid_hex.replace("-", "") for row in table_rows]

        if table_ids:
            # 3a) Mark those tables as DELETED
            update_tables_q = text(
                """
                UPDATE instance01.mtd_table
                SET status = 'DELETED'
                WHERE parent_id = CAST(:file_id AS uuid)
                """
            )
            db.execute(update_tables_q, {"file_id": file_id})

            # 3b) Remove each table entry from the folder.entities->tables JSON object
            # Re-fetch current entities after file removal
            entities_res = db.execute(get_entities_q, {"folder_id": folder_id}).fetchone()
            # Handle both dict (JSONB) and string (TEXT) types
            if entities_res and entities_res.entities:
                if isinstance(entities_res.entities, str):
                    current_entities = json.loads(entities_res.entities)
                else:
                    current_entities = entities_res.entities
            else:
                current_entities = {}

            if "tables" in current_entities:
                for tid in table_ids:
                    if tid in current_entities["tables"]:
                        del current_entities["tables"][tid]
            
            # Update folder entities again
            db.execute(update_folder_q, {"folder_id": folder_id, "entities": json.dumps(current_entities)})

        db.commit()

        return MessageResponse(
            message="File and related tables deleted successfully from folder",
            data={
                "file_id": file_id,
                "deleted_table_ids": table_ids,
                "folder_id": folder_id,
            },
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_file_by_session: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting the file: {str(exc)}",
        )
