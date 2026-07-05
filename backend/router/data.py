from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from databaseCharts import get_db as get_charts_db
from database import get_db as get_metadata_db
from fastapi import Depends, APIRouter, Request
from sqlalchemy import text
from pydantic import BaseModel
from utils.logConfig import logger
from utils.tableViewer import get_data
from fastapi.responses import JSONResponse
import plotly.graph_objs as go
import json
import psycopg2

from security.policy import require_folder_access, require_table_access, user_from_request

import os
from env import load_environment
from pathlib import Path

load_environment()

router = APIRouter(prefix="/api/v1/data", tags=["data"])


class TableRequest(BaseModel):
    tableName: str
    conversationId: str
    userId: str
    pageNo: int
    limitNo: int
    folderId: str = None  # Required for RLS-protected tables (set by MCP agent)


class PlotRequest(BaseModel):
    chartId: str
    folderId: Optional[str] = None
    # conversationId: str
    # projectId: str
    # userId: str


def resolve_physical_table_name(table_name: str, db_config: dict, folder_id: str | None = None) -> str:
    """
    Resolve a friendly table name to its physical name using the table_registry.
    
    Agent-created tables have a friendly name (e.g. 'data_temp') that differs from
    their physical name in the uploads schema (e.g. 'data_temp_a1b2c3d4').
    This function checks the registry to find the correct physical name.
    
    If no match is found, returns the original table_name unchanged
    (uploaded tables use their physical name directly).
    """
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # First resolve friendly names inside the authenticated folder scope.
        if folder_id:
            cursor.execute("""
                SELECT table_name FROM uploads.table_registry
                WHERE (friendly_name = %s OR table_name = %s)
                  AND REPLACE(LOWER(folder_id), '-', '') = %s
                LIMIT 1
            """, (table_name.lower(), table_name, folder_id.replace("-", "").lower()))
            row = cursor.fetchone()
            if row:
                physical_name = row[0]
                cursor.close()
                conn.close()
                return physical_name

        # First check: does the table actually exist in uploads schema with this exact name?
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'uploads' AND table_name = %s
        """, (table_name,))
        
        if cursor.fetchone():
            # Table exists with this exact name - no resolution needed
            cursor.close()
            conn.close()
            return table_name
        
        # No folder-scoped registry match; return exact physical names only.
        cursor.close()
        conn.close()
        return table_name
        
    except Exception as e:
        logger.warning(f"⚠️ Table name resolution failed for '{table_name}': {e}")
        return table_name


@router.post("/getTableData")
def getTableData(table_request: TableRequest, request: Request, metadata_db: Session = Depends(get_metadata_db)):
    """
    Fetch paginated table data from PostgreSQL uploads schema.
    
    **HTTP Method:** POST
    **Path:** /api/v1/data/getTableData
    
    **Parameters:**
    - table_request: TableRequest - Contains table name, pagination, and user info
    
    **Returns:**
    - JSONResponse with table data from uploads schema
    
    **Example Request:**
    ```json
    {
      "tableName": "sales_data",
      "conversationId": "conv-123",
      "userId": "user-456",
      "pageNo": 1,
      "limitNo": 10
    }
    ```
    
    **Example Response:**
    ```json
    {
      "columns": ["col1", "col2"],
      "data": [{"col1": "val1", "col2": "val2"}],
      "total": 100,
      "page": 1,
      "limit": 10
    }
    ```
    """
    table_name = table_request.tableName
    conversation_id = table_request.conversationId
    user = user_from_request(request)
    page_no = table_request.pageNo
    limit_no = table_request.limitNo
    folder_id = table_request.folderId  # Needed to pass RLS set by MCP agent
    require_folder_access(folder_id, user, metadata_db, min_level="VIEWER")
    table_policy_error = None
    try:
        require_table_access(table_name, folder_id, user, metadata_db, min_level="VIEWER")
    except Exception as exc:
        table_policy_error = exc

    # PostgreSQL Config - connects to 'postgres' database
    db_config = {
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST"),
        "dbname": os.getenv("POSTGRES_UPLOAD_DBNAME"),
        "port": os.getenv("POSTGRES_PORT"),
    }

    # Resolve friendly name → physical name for agent-created tables
    physical_table_name = resolve_physical_table_name(table_name, db_config, folder_id=folder_id)
    if table_policy_error is not None and physical_table_name == table_name:
        raise table_policy_error

    return JSONResponse(
        get_data(
            table_name=physical_table_name,
            db_config=db_config,
            page=page_no,
            limit=limit_no,
            schema="uploads",  # Fetch from 'uploads' schema
            folder_id=folder_id,  # SET app.folder_id so MCP RLS policy passes
        )
    )


@router.get("/getAllFolderTables/{folder_id}")
def getAllFolderTables(folder_id: str, request: Request, metadata_db: Session = Depends(get_metadata_db)):
    """
    Get agent-created tables belonging to a folder from the table_registry.
    
    Uploaded tables are already loaded from folder entities - this endpoint
    only supplements them with agent-created tables that aren't in entities.
    
    Returns:
        tables: { friendly_name: friendly_name } - matches tablesDict format
        table_types: { friendly_name: "agent_created" } - for UI tooltip display
    """
    if not folder_id:
        return JSONResponse({"tables": {}, "table_types": {}})
    require_folder_access(folder_id, user_from_request(request), metadata_db, min_level="VIEWER")

    db_config = {
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST"),
        "dbname": os.getenv("POSTGRES_UPLOAD_DBNAME"),
        "port": os.getenv("POSTGRES_PORT"),
    }

    tables = {}
    table_types = {}
    folder_id_no_dash = folder_id.replace("-", "").lower()

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        # Get agent-created tables from uploads.table_registry
        cursor.execute("""
            SELECT table_name, friendly_name
            FROM uploads.table_registry
            WHERE LOWER(REPLACE(folder_id, '-', '')) = %s
              AND table_type = 'agent_created'
            ORDER BY created_at ASC
        """, (folder_id_no_dash,))

        for row in cursor.fetchall():
            physical_name = row[0]
            friendly_name = row[1] or physical_name
            # tablesDict format: key = friendly_name, value = friendly_name (display label)
            tables[friendly_name] = friendly_name
            table_types[friendly_name] = "agent_created"

        cursor.close()
        conn.close()

        logger.info(f"📋 Agent tables for folder {folder_id_no_dash[:8]}: {list(tables.keys())}")

    except Exception as e:
        logger.error(f"❌ Error in getAllFolderTables: {e}")
        return JSONResponse({"tables": {}, "table_types": {}})

    return JSONResponse({"tables": tables, "table_types": table_types})


@router.post("/getChartData")
def getChartData(plot_request: PlotRequest, request: Request, db: Session = Depends(get_charts_db), metadata_db: Session = Depends(get_metadata_db)):
    """
    Retrieve chart data from PostgreSQL charts_storage schema.
    
    **HTTP Method:** POST
    **Path:** /api/v1/data/getChartData
    
    **Parameters:**
    - plot_request: PlotRequest - Contains chart_id
    
    **Returns:**
    - JSON with chart data including type, title, data, config, and metadata
    
    **Example Request:**
    ```json
    {
      "chartId": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Example Response:**
    ```json
    {
      "success": true,
      "chart_id": "550e8400-e29b-41d4-a716-446655440000",
      "chart_type": "bar",
      "title": "Sales by Region",
      "chart_data": {"x": [...], "y": [...]},
      "chart_config": {"layout": {...}},
      "created_at": "2024-01-15T10:30:00"
    }
    ```
    """
    chart_id = plot_request.chartId

    print(
        f"Received chart request for chart_id: {chart_id}",
        flush=True,
    )

    try:
        sql = text("SELECT * FROM charts_storage.chart_storage WHERE chart_id = :chart_id")
        result = db.execute(sql, {"chart_id": chart_id})
        chart = result.fetchone()

        if not chart:
            return {
                "success": False,
                "chart_id": chart_id,
                "error": "Chart not found",
                "message": f"No chart found with ID {chart_id}",
            }

        # Convert chart data to dict
        chart_dict = chart._asdict() if hasattr(chart, "_asdict") else dict(zip(chart.keys(), chart))
        
        chart_folder_id = chart_dict.get("folder_id") or chart_dict.get("folderId") or plot_request.folderId
        if not chart_folder_id:
            return {"success": False, "chart_id": chart_id, "error": "Chart scope missing", "message": "Chart data cannot be returned without folder scope metadata."}
        require_folder_access(chart_folder_id, user_from_request(request), metadata_db, min_level="VIEWER")

        # Parse JSONB fields if they are strings (shouldn't be with PostgreSQL JSONB, but just in case)
        chart_data = chart_dict.get("chart_data")
        if isinstance(chart_data, str):
            chart_data = json.loads(chart_data)
        
        chart_config = chart_dict.get("chart_config")
        if isinstance(chart_config, str):
            chart_config = json.loads(chart_config)
        
        # Format created_at timestamp
        created_at = chart_dict.get("created_at")
        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        # Return comprehensive chart data
        return {
            "success": True,
            "chart_id": chart_id,
            "chart_type": chart_dict.get("chart_type", "scatter"),
            "title": chart_dict.get("chart_title", f"Chart {chart_id}"),
            "chart_data": chart_data,
            "chart_config": chart_config,
            "created_at": created_at,
            "query_hash": chart_dict.get("query_hash"),
        }

    except Exception as e:
        logger.error(f"Error retrieving chart {chart_id}: {str(e)}")
        return {
            "success": False,
            "chart_id": chart_id,
            "error": str(e),
            "message": "Failed to retrieve chart data",
        }
