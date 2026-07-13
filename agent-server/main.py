from __future__ import annotations

import logging
import os
import time
import uuid
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from graph.builder import create_general_graph, is_conversation_message
from reports.writer import build_report_file
from streaming.events import sse_json
from tools.postgres import get_folder_status
from llm.client import OPENROUTER_BASE_URL, resolve_model_name
from runtime.model_config import ModelConfigUpdate, apply_model_config_update, config_status_from_effective, load_effective_model_config
from runtime.model_store import load_workspace_model_config, save_workspace_model_config
from security.access import require_admin, require_folder_access
from security.auth import require_user_from_authorization
from shared.workspace_store import (
    WorkspaceStoreError,
    ensure_workspace_schema,
    get_artifact,
    get_workspace_snapshot,
    upsert_artifact,
)

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent / ".env")

def _resolve_artifact_root(configured: str | Path) -> Path:
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


logging.basicConfig(level=os.getenv("AGENT_LOG_LEVEL", "INFO"))
logger = logging.getLogger("eventhorizon.agent_server")

ARTIFACT_ROOT = _resolve_artifact_root(os.getenv("AGENT_ARTIFACT_ROOT", Path(__file__).parent / "artifacts"))
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

graph = create_general_graph()


class AgentStreamRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    folder_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: str = "default_user"
    selected_tables: list[str] = Field(default_factory=list)
    selected_table_id: Optional[str] = None
    selected_table_name: Optional[str] = None
    surface: Optional[str] = None


class DashboardActivateRequest(BaseModel):
    session_id: str
    folder_id: Optional[str] = None
    table_name: Optional[str] = None
    table_id: Optional[str] = None



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
    selected_table_id: Optional[str] = None
    selected_table_name: Optional[str] = None
    surface: Optional[str] = None


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


@app.on_event("startup")
def initialize_workspace_store() -> None:
    ensure_workspace_schema()


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


def _authorized_workspace_context(payload: Any, surface: str, folder_id: str | None = None) -> dict[str, Any]:
    resolved_folder = folder_id or getattr(payload, "folder_id", None)
    if not resolved_folder:
        if surface == "chat":
            return {"workspace": {}, "selected_table": None}
        raise HTTPException(400, "folder_id is required.")
    if not getattr(payload, "session_id", None):
        raise HTTPException(400, "An active session is required.")
    try:
        snapshot = get_workspace_snapshot(
            str(payload.session_id),
            str(resolved_folder),
            str(payload.user_id),
        )
    except WorkspaceStoreError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    selected = snapshot.get("selected_table")
    requested_id = getattr(payload, "selected_table_id", None)
    if requested_id and selected and str(requested_id) != str(selected.get("id")):
        raise HTTPException(409, "The requested prepared table is not selected in this session.")
    if surface in {"dashboard", "report"} and not selected:
        raise HTTPException(409, "Create and select a prepared table in Prepare first.")
    return snapshot


async def _stream_graph(payload: AgentStreamRequest, surface: str, workspace_context: dict[str, Any] | None = None) -> AsyncIterator[str]:
    start = time.time()
    query_id = str(uuid.uuid4())
    session_id = payload.session_id or f"session-{query_id}"

    yield f"data: {sse_json({'type': 'stream_start', 'query_id': query_id, 'session_id': session_id, 'timestamp': _now()})}\n\n"

    context = workspace_context or {"workspace": {}, "selected_table": None}
    selected = context.get("selected_table") or {}
    workspace = context.get("workspace") or {}

    initial_state = {
        "surface": surface,
        "session_id": session_id,
        "folder_id": payload.folder_id,
        "project_id": payload.project_id,
        "user_id": payload.user_id,
        "query_id": query_id,
        "user_message": payload.query,
        "selected_tables": payload.selected_tables or [],
        "selected_table_id": selected.get("id"),
        "selected_table_name": selected.get("name"),
        "transform_revision": int(selected.get("revision") or workspace.get("transform_revision") or 0),
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
    workspace_context = _authorized_workspace_context(payload, "chat")
    return StreamingResponse(
        _stream_graph(payload, "chat", workspace_context),
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
    workspace_context = _authorized_workspace_context(payload, "dashboard")
    return StreamingResponse(
        _stream_graph(payload, "dashboard", workspace_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/report/chat/stream")
async def report_chat_stream(payload: ReportRequest, folder_id: str = Query(...), authorization: str | None = Header(default=None)) -> StreamingResponse:
    user = require_user_from_authorization(authorization)
    payload.user_id = str(user["sub"])
    require_folder_access(folder_id, payload.user_id)
    workspace_context = _authorized_workspace_context(payload, "report", folder_id)
    selected = workspace_context.get("selected_table") or {}
    requested_format = str(payload.format or "pdf").lower()
    supported_formats = ("pdf", "html", "pptx", "docx")
    if requested_format not in supported_formats:
        raise HTTPException(400, "Report format must be PDF, HTML, PPTX, or DOCX.")

    async def generate() -> AsyncIterator[str]:
        start = time.time()
        report_id = str(uuid.uuid4())
        query = payload.query or "Generate a general report."
        conversation_only = is_conversation_message(query)
        if payload.custom_prompt:
            query = f"{query}\n\nAdditional instructions: {payload.custom_prompt}"
        session_id = str(payload.session_id)
        workspace = workspace_context.get("workspace") or {}

        state = {
            "surface": "report",
            "session_id": session_id,
            "folder_id": folder_id,
            "project_id": payload.project_id,
            "user_id": payload.user_id,
            "query_id": report_id,
            "user_message": query,
            "selected_tables": [selected.get("name")] if selected.get("name") else [],
            "selected_table_id": selected.get("id"),
            "selected_table_name": selected.get("name"),
            "transform_revision": int(selected.get("revision") or workspace.get("transform_revision") or 0),
            "available_tables": [],
            "tool_results": [],
            "artifacts": [],
            "intent": "report",
            "final_response": None,
            "errors": [],
        }

        final_text = ""
        stream_error = ""
        successful_evidence_tools: set[str] = set()
        try:
            config = _thread_config(
                surface="report",
                user_id=payload.user_id,
                folder_id=folder_id,
                session_id=session_id,
                project_id=payload.project_id,
            )
            async for event in graph.astream(state, config=config, stream_mode="custom"):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "final_response":
                    final_text = event.get("text") or final_text
                if event.get("type") == "function_response" and event.get("success") is not False:
                    tool_name = str(event.get("tool_name") or "")
                    if tool_name in {"report_get_data_summary", "report_list_charts"}:
                        successful_evidence_tools.add(tool_name)
                if event.get("type") == "error":
                    stream_error = str(event.get("message") or "Report generation failed.")
                    continue
                if event.get("type") == "completion":
                    continue
                yield f"data: {sse_json(event)}\n\n"

            if stream_error:
                raise RuntimeError(stream_error)
            if not final_text:
                final_text = "No grounded report content was generated."
            if conversation_only:
                yield f"data: {sse_json({'type': 'result', 'success': True, 'artifact_created': False, 'report_id': None, 'final_output': final_text, 'llm_response': final_text, 'time_taken': round(time.time() - start, 2), 'timestamp': _now()})}\n\n"
                return

            required_evidence = {"report_get_data_summary", "report_list_charts"}
            missing_evidence = sorted(required_evidence - successful_evidence_tools)
            if missing_evidence:
                raise RuntimeError(
                    "Report generation stopped because required evidence tools did not complete: "
                    + ", ".join(missing_evidence)
                )

            latest_context = get_workspace_snapshot(session_id, folder_id, payload.user_id)
            drafts = latest_context.get("report_drafts") or []
            sections = list((drafts[-1] if drafts else {}).get("sections") or [])
            export_body = final_text
            if sections:
                section_text = []
                for section in sections:
                    title = str(section.get("title") or "Section").strip()
                    content = str(section.get("content") or "").strip()
                    if content:
                        section_text.append(f"{title}\n{content}")
                if section_text:
                    export_body = "\n\n".join(section_text)

            transform_revision = int(selected.get("revision") or 0)
            lineage = (
                "Report metadata\n"
                f"Prepared table: {selected.get('name') or 'Unknown'}\n"
                f"Prepared table ID: {selected.get('id') or 'Unknown'}\n"
                f"Transform revision: {transform_revision}\n"
                f"Session ID: {session_id}"
            )
            export_body = f"{lineage}\n\n{export_body}"

            paths: dict[str, Path] = {}
            download_urls: dict[str, str] = {}
            for file_format in supported_formats:
                paths[file_format] = build_report_file(
                    root=ARTIFACT_ROOT,
                    folder_id=folder_id,
                    report_id=report_id,
                    file_format=file_format,
                    title="EventHorizon Analysis Report",
                    body=export_body,
                )
                download_urls[file_format.upper()] = f"/reports/download/{folder_id}/{report_id}/{file_format}"
            artifact = {
                "id": report_id,
                "artifact_type": "report",
                "type": "report",
                "name": "EventHorizon Analysis Report",
                "status": "ready",
                "format": requested_format.upper(),
                "downloadUrl": download_urls[requested_format.upper()],
                "downloadUrls": download_urls,
                "source_table_id": selected.get("id"),
                "sourceTableId": selected.get("id"),
                "selected_table_name": selected.get("name"),
                "selectedTableName": selected.get("name"),
                "transform_revision": transform_revision,
                "transformRevision": transform_revision,
                "session_id": session_id,
                "sessionId": session_id,
                "sections": sections,
                "body": export_body,
                "createdAt": _now(),
            }
            saved = upsert_artifact(
                session_id,
                folder_id,
                payload.user_id,
                artifact,
                storage_path=str(paths[requested_format]),
            )
            yield f"data: {sse_json({'type': 'artifact', 'artifact_type': 'report', 'data': saved, 'artifact': saved, 'timestamp': _now()})}\n\n"
            yield f"data: {sse_json({'type': 'result', 'success': True, 'report_id': report_id, 'name': artifact['name'], 'format': artifact['format'], 'download_url': artifact['downloadUrl'], 'download_urls': download_urls, 'session_id': session_id, 'selected_table_id': selected.get('id'), 'transform_revision': selected.get('revision', 0), 'final_output': final_text, 'llm_response': final_text, 'time_taken': round(time.time() - start, 2), 'timestamp': _now()})}\n\n"
        except Exception as exc:
            logger.exception("Report stream failed")
            message = _public_error(exc)
            yield f"data: {sse_json({'type': 'error', 'message': message, 'timestamp': _now()})}\n\n"
            yield f"data: {sse_json({'type': 'result', 'success': False, 'error': message, 'final_output': '', 'report_id': report_id, 'time_taken': round(time.time() - start, 2), 'timestamp': _now()})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

@app.get("/reports/download/{folder_id}/{report_id}/{format}")
async def download_report(folder_id: str, report_id: str, format: str, authorization: str | None = Header(default=None)) -> FileResponse:
    user = require_user_from_authorization(authorization)
    user_id = str(user["sub"])
    require_folder_access(folder_id, user_id)
    safe_format = format.lower()
    if safe_format not in {"pdf", "html", "pptx", "docx"}:
        raise HTTPException(400, "Unsupported report format")
    try:
        artifact = get_artifact(report_id, folder_id, user_id)
    except WorkspaceStoreError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if not artifact or artifact.get("artifact_type") != "report":
        raise HTTPException(404, "Report not found")
    snapshot = get_workspace_snapshot(str(artifact.get("session_id")), folder_id, user_id)
    workspace = snapshot.get("workspace") or {}
    if (
        str(artifact.get("source_table_id") or "") != str(workspace.get("selected_table_id") or "")
        or int(artifact.get("transform_revision") or 0) != int(workspace.get("transform_revision") or 0)
    ):
        raise HTTPException(409, "This report is stale because the selected prepared table changed.")
    available = artifact.get("downloadUrls") or artifact.get("download_urls") or {}
    if safe_format.upper() not in available:
        raise HTTPException(404, "This report format is not available")
    path = ARTIFACT_ROOT / _safe_name(folder_id) / f"{_safe_name(report_id)}.{safe_format}"
    root = ARTIFACT_ROOT.resolve()
    resolved = path.resolve()
    if root not in resolved.parents or not resolved.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(str(resolved), filename=resolved.name)

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