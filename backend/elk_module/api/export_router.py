"""
Export API endpoints for graph visualization
"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from typing import Optional
import os
import tempfile
from pathlib import Path

from ..models.graph_models import ExportOptions, GraphLayoutResponse
from ..core.config import settings

router = APIRouter()

@router.post("/svg")
async def export_svg(
    graph_data: GraphLayoutResponse,
    options: Optional[ExportOptions] = None
):
    """
    Export graph as SVG file
    """
    try:
        if not graph_data.svg:
            raise HTTPException(status_code=400, detail="No SVG data provided")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as f:
            f.write(graph_data.svg)
            temp_path = f.name
        
        # Return file response
        return FileResponse(
            temp_path,
            media_type="image/svg+xml",
            filename="process-mining-graph.svg"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.post("/json")
async def export_json(graph_data: GraphLayoutResponse):
    """
    Export graph data as JSON
    """
    try:
        export_data = {
            "graph": graph_data.graph.dict(),
            "layout": graph_data.layout.dict(),
            "statistics": graph_data.statistics,
            "metadata": {
                "export_format": "json",
                "version": "1.0.0"
            }
        }
        
        return Response(
            content=graph_data.json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=process-graph.json"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON export failed: {str(e)}")

@router.get("/formats")
async def get_export_formats():
    """
    Get available export formats
    """
    return {
        "formats": [
            {
                "name": "SVG",
                "extension": "svg",
                "mime_type": "image/svg+xml",
                "description": "Scalable Vector Graphics"
            },
            {
                "name": "JSON", 
                "extension": "json",
                "mime_type": "application/json",
                "description": "Graph data and layout information"
            }
        ]
    }
