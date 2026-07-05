from sqlalchemy.orm import Session
from typing import List, Dict, Any, Union
from database import get_db
from fastapi import Depends, APIRouter
from sqlalchemy import text
from schemas import TableCreate, TableEdit, TableDelete, TableOut, MessageResponse
from datetime import datetime
import uuid

# router = APIRouter(prefix="/api/v1/tables", tags=["tables"])


def _hexify(val):
    """Convert UUID objects and binary data to hex strings for PostgreSQL"""
    if isinstance(val, uuid.UUID):
        return str(val)
    elif isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val


def parse_iso_datetime(iso_string: str) -> datetime:
    """Convert ISO 8601 datetime string to Python datetime object"""
    # Handle both 'Z' suffix and '+00:00' timezone formats
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1] + "+00:00"

    # Parse the datetime string
    return datetime.fromisoformat(iso_string).replace(tzinfo=None)


# @router.post("/createTable", response_model=MessageResponse)
def create_table(
    tables: List[TableCreate], db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Create one or more table records.
    
    **HTTP Method:** POST
    **Path:** /api/v1/tables/createTable
    
    **Parameters:**
    - tables: List[TableCreate] - List of table objects to create
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "sales_data",
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "parent_id": "770e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "type": "CSV"
      }
    ]
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Table(s) created successfully",
      "data": null
    }
    ```
    """
    try:
        insert_stmt = """
            INSERT INTO instance01.mtd_table (
                id, name, created_at, created_by, parent_id, status, type
            )
            VALUES (
                CAST(:id AS uuid), :name, :created_at,
                :created_by,
                CAST(:parent_id AS uuid), :status, :type
            )
        """
        for table in tables:
            db.execute(
                text(insert_stmt),
                {
                    "id": table.id,
                    "name": table.name,
                    "created_at": parse_iso_datetime(table.created_at),
                    "created_by": table.created_by,
                    "parent_id": table.parent_id,
                    "status": table.status,
                    "type": table.type,
                },
            )
        db.commit()
        return MessageResponse(message="Table(s) created successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in create_table: {exc}")
        raise


# @router.put("/editTable", response_model=MessageResponse)
def edit_table(table: TableEdit, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Update table metadata fields.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/tables/editTable
    
    **Parameters:**
    - table: TableEdit - Table object with id and fields to update
    
    **Returns:**
    - MessageResponse with success message
    
    **Example Request:**
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "updated_sales_data",
      "status": "PROCESSING"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Table updated successfully",
      "data": null
    }
    ```
    """
    try:
        payload_dict = table.model_dump(exclude_unset=True)
        update_fields: List[str] = []
        params = {"tid": table.id}
        for key in ("name", "originalName", "status"):
            if key in payload_dict and payload_dict[key] is not None:
                col = "original_name" if key == "originalName" else key
                update_fields.append(f"{col} = :{key}")
                params[key] = payload_dict[key]
        if not update_fields:
            return MessageResponse(message="No valid fields to update", data=None)
        q = text(
            f"UPDATE instance01.mtd_table SET {', '.join(update_fields)} WHERE id = CAST(:tid AS uuid)"
        )
        db.execute(q, params)
        db.commit()
        return MessageResponse(message="Table updated successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in edit_table: {exc}")
        raise


# @router.put("/deleteTable", response_model=MessageResponse)
def delete_table(table: TableDelete, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Soft delete a table by marking it as DELETED.
    
    **HTTP Method:** PUT
    **Path:** /api/v1/tables/deleteTable
    
    **Parameters:**
    - table: TableDelete - Table object with id to delete
    
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
      "message": "Table deleted successfully",
      "data": null
    }
    ```
    """
    try:
        q = text(
            "UPDATE instance01.mtd_table SET status = 'DELETED' WHERE id = CAST(:tid AS uuid)"
        )
        db.execute(q, {"tid": table.id})
        db.commit()
        return MessageResponse(message="Table deleted successfully", data=None)
    except Exception as exc:
        db.rollback()
        print(f"Error in delete_table: {exc}")
        raise


# @router.get("/getTable/{table_id}", response_model=MessageResponse)
def get_table(table_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    """
    Get a single table by ID.
    
    **HTTP Method:** GET
    **Path:** /api/v1/tables/getTable/{table_id}
    
    **Parameters:**
    - table_id: str - UUID of the table
    
    **Returns:**
    - MessageResponse with table data
    
    **Example Request:**
    ```
    GET /api/v1/tables/getTable/550e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "sales_data",
        "created_at": "2024-01-15T10:30:00",
        "created_by": "660e8400-e29b-41d4-a716-446655440000",
        "parent_id": "770e8400-e29b-41d4-a716-446655440000",
        "status": "ACTIVE",
        "type": "CSV"
      }
    }
    ```
    """
    try:
        q = text("SELECT * FROM instance01.mtd_table WHERE id = CAST(:tid AS uuid)")
        res = db.execute(q, {"tid": table_id}).fetchone()
        if not res:
            return MessageResponse(message="Table not found", data=None)
        d = res._asdict() if hasattr(res, "_asdict") else dict(zip(res.keys(), res))
        for k, v in d.items():
            if k == "created_at" and v is not None:
                d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
            else:
                d[k] = _hexify(v)
        return MessageResponse(message="Success", data=d)
    except Exception as exc:
        print(f"Error in get_table: {exc}")
        raise


# @router.get("/getTablesByParentId/{parent_id}", response_model=MessageResponse)
def get_tables_by_parent_id(
    parent_id: str, db: Session = Depends(get_db)
) -> MessageResponse:
    """
    Get all tables belonging to a specific parent (file/folder).
    
    **HTTP Method:** GET
    **Path:** /api/v1/tables/getTablesByParentId/{parent_id}
    
    **Parameters:**
    - parent_id: str - UUID of the parent entity
    
    **Returns:**
    - MessageResponse with list of tables
    
    **Example Request:**
    ```
    GET /api/v1/tables/getTablesByParentId/770e8400-e29b-41d4-a716-446655440000
    ```
    
    **Example Response:**
    ```json
    {
      "message": "Success",
      "data": [
        {
          "id": "550e8400-e29b-41d4-a716-446655440000",
          "name": "sales_data",
          "created_at": "2024-01-15T10:30:00",
          "created_by": "660e8400-e29b-41d4-a716-446655440000",
          "parent_id": "770e8400-e29b-41d4-a716-446655440000",
          "status": "ACTIVE",
          "type": "CSV"
        }
      ]
    }
    ```
    """
    try:
        q = text(
            "SELECT * FROM instance01.mtd_table WHERE parent_id = CAST(:pid AS uuid)"
        )
        rows = db.execute(q, {"pid": parent_id}).fetchall()
        out = []
        for row in rows:
            d = row._asdict() if hasattr(row, "_asdict") else dict(zip(row.keys(), row))
            for k, v in d.items():
                if k == "created_at" and v is not None:
                    d[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
                else:
                    d[k] = _hexify(v)
            out.append(d)
        return MessageResponse(message="Success", data=out)
    except Exception as exc:
        print(f"Error in get_tables_by_parent_id: {exc}")
        raise
