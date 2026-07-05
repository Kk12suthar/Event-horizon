from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from graph.builder import create_general_graph
from reports.writer import build_report_file
from streaming.events import sse_json
from tools.postgres import get_folder_status
from llm.client import OPENROUTER_BASE_URL, resolve_model_name
from runtime.model_config import ModelConfigUpdate, apply_model_config_update, config_status_from_effective, load_effective_model_config
from runtime.model_store import load_workspace_model_config, save_workspace_model_config
from security.access import require_admin, require_folder_access
from security.auth import require_user_from_authorization

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=os.getenv("AGENT_LOG_LEVEL", "INFO"))
logger = logging.getLogger("eventhorizon.agent_server")

ARTIFACT_ROOT = Path(os.getenv("AGENT_ARTIFACT_ROOT", Path(__file__).parent / "artifacts"))
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

graph = create_general_graph()


class AgentStreamRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    folder_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: str = "default_user"
    selected_tables: list[str] = Field(default_factory=list)


class DashboardActivateRequest(BaseModel):
    session_id: str
    folder_id: Optional[str] = None
    table_name: Optional[str] = None



class ModelConfigRequest(BaseModel):
    provider: str = "openrouter"
    model: str = "openai/gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    site_url: Optional[str] = None
    app_name: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
class ReportRequest(BaseModel):
    query: str
    mode: str = "specific"
    format: str = "pdf"
    custom_prompt: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: str = "default_user"
    selected_tables: list[str] = Field(default_factory=list)


app = FastAPI(
    title="EventHorizon LangGraph Agent Server",
    version="0.1.0",
    description="General LangGraph agent runtime for EventHorizon.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}



@app.get("/agent/model-config")
async def get_model_config(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_user_from_authorization(authorization)
    return _model_config_status()


@app.put("/agent/model-config")
async def update_model_config(payload: ModelConfigRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user_from_authorization(authorization)
    require_admin(str(user["sub"]))
    try:
        return apply_model_config_update(
            ModelConfigUpdate(**(payload.model_dump() if hasattr(payload, "model_dump") else payload.dict())),
            save_config=lambda config: save_workspace_model_config(config, updated_by=str(user["sub"])),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get("/agent/folder-status/{folder_id}")
async def folder_status(folder_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user_from_authorization(authorization)
    require_folder_access(folder_id, str(user["sub"]))
    return get_folder_status(folder_id, user_id=str(user["sub"]))


@app.post("/agent/dashboard/activate")
async def activate_dashboard(payload: DashboardActivateRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user_from_authorization(authorization)
    if payload.folder_id:
        require_folder_access(payload.folder_id, str(user["sub"]))
    status = get_folder_status(payload.folder_id, user_id=str(user["sub"])) if payload.folder_id else {"has_data": True, "tables": []}
    return {
        "dashboard_activated": True,
        "analysis_ready": True,
        "session_id": payload.session_id,
        "folder_id": payload.folder_id,
        "has_data": status.get("has_data", True),
        "tables": status.get("tables", []),
        "redirect_url": f"/agent/dashboard/{payload.session_id}",
    }


@app.get("/agent/dashboard/exist/{session_id}")
async def dashboard_exists(session_id: str, folder_id: Optional[str] = Query(default=None), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user_from_authorization(authorization)
    if folder_id:
        require_folder_access(folder_id, str(user["sub"]))
    status = get_folder_status(folder_id, user_id=str(user["sub"])) if folder_id else {"has_data": True, "tables": []}
    return {
        "exists": True,
        "session_id": session_id,
        "folder_id": folder_id,
        "has_data": status.get("has_data", True),
        "tables": status.get("tables", []),
    }


async def _stream_graph(payload: AgentStreamRequest, surface: str) -> AsyncIterator[str]:
    start = time.time()
    query_id = str(uuid.uuid4())
    session_id = payload.session_id or f"session-{query_id}"

    yield f"data: {sse_json({'type': 'stream_start', 'message': 'Connected - starting query processing...', 'query_id': query_id, 'session_id': session_id, 'timestamp': _now()})}\n\n"

    initial_state = {
        "surface": surface,
        "session_id": session_id,
        "folder_id": payload.folder_id,
        "project_id": payload.project_id,
        "user_id": payload.user_id,
        "query_id": query_id,
        "user_message": payload.query,
        "selected_tables": payload.selected_tables or [],
        "available_tables": [],
        "tool_results": [],
        "artifacts": [],
        "intent": None,
        "final_response": None,
        "errors": [],
    }

    config = _thread_config(
        surface=surface,
        user_id=payload.user_id,
        folder_id=payload.folder_id,
        session_id=session_id,
        project_id=payload.project_id,
    )
    final_response = ""
    emitted_completion = False

    try:
        async for event in graph.astream(initial_state, config=config, stream_mode="custom"):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "final_response":
                final_response = event.get("text", "") or final_response
            if event.get("type") == "completion":
                emitted_completion = True
            yield f"data: {sse_json(event)}\n\n"

        if not emitted_completion:
            yield f"data: {sse_json({'type': 'completion', 'final_output': final_response, 'time_taken': round(time.time() - start, 2), 'chart_ids': [], 'query_id': query_id, 'query': payload.query, 'timestamp': _now()})}\n\n"
    except Exception as exc:
        logger.exception("Graph stream failed")
        public_error = _public_error(exc)
        yield f"data: {sse_json({'type': 'error', 'message': public_error, 'timestamp': _now()})}\n\n"
        yield f"data: {sse_json({'type': 'completion', 'final_output': '', 'success': False, 'error': public_error, 'time_taken': round(time.time() - start, 2), 'query_id': query_id, 'query': payload.query, 'timestamp': _now()})}\n\n"


@app.post("/agent/chat/stream")
async def chat_stream(payload: AgentStreamRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    user = require_user_from_authorization(authorization)
    payload.user_id = str(user["sub"])
    if payload.folder_id:
        require_folder_access(payload.folder_id, payload.user_id)
    return StreamingResponse(
        _stream_graph(payload, "chat"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/agent/dashboard/stream")
async def dashboard_stream(payload: AgentStreamRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    user = require_user_from_authorization(authorization)
    payload.user_id = str(user["sub"])
    if not payload.folder_id:
        raise HTTPException(400, "folder_id is required for dashboard chat.")
    require_folder_access(payload.folder_id, payload.user_id)
    return StreamingResponse(
        _stream_graph(payload, "dashboard"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/report/chat/stream")
async def report_chat_stream(payload: ReportRequest, folder_id: str = Query(...), authorization: str | None = Header(default=None)) -> StreamingResponse:
    user = require_user_from_authorization(authorization)
    payload.user_id = str(user["sub"])
    require_folder_access(folder_id, payload.user_id)

    async def generate() -> AsyncIterator[str]:
        start = time.time()
        report_id = f"R-{uuid.uuid4().hex[:8]}"
        query = payload.query or "Generate a general report."
        report_format = (payload.format or "pdf").lower()
        session_id = payload.session_id or report_id

        yield f"data: {sse_json({'status': 'stream', 'chunk': 'Preparing folder context...\n\n'})}\n\n"

        state = {
            "surface": "report",
            "session_id": session_id,
            "folder_id": folder_id,
            "project_id": payload.project_id,
            "user_id": payload.user_id,
            "query_id": report_id,
            "user_message": query,
            "selected_tables": payload.selected_tables or [],
            "available_tables": [],
            "tool_results": [],
            "artifacts": [],
            "intent": "report",
            "final_response": None,
            "errors": [],
        }

        final_text = ""
        try:
            config = _thread_config(
                surface="report",
                user_id=payload.user_id,
                folder_id=folder_id,
                session_id=f"{session_id}:{report_id}",
                project_id=payload.project_id,
            )
            async for event in graph.astream(state, config=config, stream_mode="custom"):
                if event.get("type") == "status":
                    yield f"data: {sse_json({'status': 'artifact', 'artifact': {'type': 'context', 'title': event.get('title', 'Agent status'), 'data': event.get('message', '')}})}\n\n"
                if event.get("type") == "final_response":
                    final_text = event.get("text") or final_text
                    yield f"data: {sse_json({'status': 'stream', 'chunk': final_text})}\n\n"

            if not final_text:
                final_text = "No report content was generated."

            build_report_file(
                root=ARTIFACT_ROOT,
                folder_id=folder_id,
                report_id=report_id,
                file_format=report_format,
                title="EventHorizon Analysis Report",
                body=final_text,
            )
            download_url = f"/reports/download/{folder_id}/{report_id}/{report_format}"
            yield f"data: {sse_json({'type': 'result', 'report_id': report_id, 'name': 'EventHorizon Analysis Report', 'format': report_format, 'download_url': download_url, 'llm_response': final_text, 'time_taken': round(time.time() - start, 2)})}\n\n"
        except Exception as exc:
            logger.exception("Report stream failed")
            yield f"data: {sse_json({'status': 'error', 'message': _public_error(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/reports/download/{folder_id}/{report_id}/{format}")
async def download_report(folder_id: str, report_id: str, format: str, authorization: str | None = Header(default=None)) -> FileResponse:
    user = require_user_from_authorization(authorization)
    require_folder_access(folder_id, str(user["sub"]))
    safe_format = format.lower()
    path = ARTIFACT_ROOT / _safe_name(folder_id) / f"{_safe_name(report_id)}.{safe_format}"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(str(path), filename=path.name)



def _model_config_status() -> dict[str, Any]:
    config = load_effective_model_config(load_workspace_model_config)
    return config_status_from_effective(config)


def _provider_from_model(model: str, fallback: str) -> str:
    lowered = model.lower()
    if lowered.startswith("openrouter/"):
        return "openrouter"
    if lowered.startswith("vertex_ai/") or lowered.startswith("vertex/"):
        return "vertex"
    if lowered.startswith("anthropic/") or lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith("google/") or lowered.startswith("gemini"):
        return "google"
    if lowered.startswith("openai/") or lowered.startswith("gpt-") or lowered.startswith("o1") or lowered.startswith("o3"):
        return "openai"
    return fallback


def _normalize_model_provider(provider: str | None) -> str:
    value = str(provider or "openrouter").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"open_router": "openrouter", "gemini": "google", "google_gemini": "google", "vertex_ai": "vertex", "vertexai": "vertex", "google_vertex": "vertex"}
    return aliases.get(value, value or "openrouter")


def _model_provider_key(provider: str) -> str | None:
    return {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }.get(provider)


def _set_if_present(name: str, value: str | None) -> None:
    return None

def _thread_config(*, surface: str, user_id: str | None, folder_id: str | None, session_id: str | None, project_id: str | None = None) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": ":".join([
                "eventhorizon",
                _safe_name(surface or "agent"),
                _safe_name(user_id or "anonymous"),
                _safe_name(project_id or "no_project"),
                _safe_name(folder_id or "no_folder"),
                _safe_name(session_id or "no_session"),
            ])
        }
    }


def _public_error(exc: Exception) -> str:
    if os.getenv("AGENT_EXPOSE_ERRORS", "false").lower() in {"1", "true", "yes"}:
        return str(exc)[:500]
    return "The agent stream failed while processing this request. The server log has the detailed exception."


def _safe_name(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in ("-", "_")) or "artifact"


def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"