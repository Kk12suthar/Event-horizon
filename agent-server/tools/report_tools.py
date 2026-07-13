from __future__ import annotations

import uuid
from typing import Any

from shared.workspace_store import get_workspace_snapshot, resolve_transform_table_record, upsert_artifact
from tools.postgres import describe_tables, estimated_row_count
from tools.spec import ToolSpec


READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
SURFACES = frozenset({"report"})


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


FOLDER = {"type": "string", "description": "EventHorizon folder UUID."}
SESSION = {"type": "string", "description": "Active EventHorizon session UUID."}


def _context(folder_id: str | None, user_id: str | None, session_id: str | None, selected_table_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not folder_id or not user_id or not session_id:
        raise ValueError("Publish requires an active folder session.")
    snapshot = get_workspace_snapshot(session_id, folder_id, user_id)
    workspace = snapshot.get("workspace") or {}
    selected_id = selected_table_id or workspace.get("selected_table_id")
    if not selected_id:
        raise ValueError("Create and select a prepared table in Prepare first.")
    if workspace.get("selected_table_id") and str(selected_id) != str(workspace.get("selected_table_id")):
        raise ValueError("The requested table is not the session's selected prepared table.")
    record = resolve_transform_table_record(folder_id, str(selected_id))
    if not record:
        raise ValueError("The selected prepared table no longer exists.")
    return record, snapshot


def get_data_summary(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, **_: Any) -> dict[str, Any]:
    record, _snapshot = _context(folder_id, user_id, session_id, selected_table_id)
    described = describe_tables(folder_id, user_id=user_id)
    table = next((item for item in described.get("tables", []) if item.get("name") == record["name"]), {})
    rows = estimated_row_count(folder_id, record["name"], user_id=user_id)
    return {
        "table_id": record["id"],
        "table_name": record["name"],
        "transform_revision": record["revision"],
        "estimated_row_count": rows.get("estimated_row_count", table.get("estimated_row_count", -1)),
        "columns": table.get("columns", []),
        "source_tables": record.get("source_tables", []),
        "recipe": record.get("recipe", []),
    }


def list_charts(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, **_: Any) -> dict[str, Any]:
    record, snapshot = _context(folder_id, user_id, session_id, selected_table_id)
    charts = [
        chart
        for chart in snapshot.get("charts", [])
        if not chart.get("stale") and chart.get("source_table_id") == record["id"]
    ]
    return {"table_id": record["id"], "chart_count": len(charts), "charts": charts}


def create_section(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, title: str = "", content: str = "", chart_ids: list[str] | None = None, **_: Any) -> dict[str, Any]:
    record, snapshot = _context(folder_id, user_id, session_id, selected_table_id)
    draft_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"eventhorizon:report-draft:{session_id}"))
    existing = next((item for item in snapshot.get("report_drafts", []) if item.get("id") == draft_id), None)
    sections = list((existing or {}).get("sections") or [])
    section_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{draft_id}:{title.strip().lower()}"))
    section = {
        "id": section_id,
        "title": title.strip() or "Untitled section",
        "content": content.strip(),
        "chart_ids": chart_ids or [],
        "status": "ready",
        "included": True,
    }
    sections = [item for item in sections if item.get("id") != section_id] + [section]
    artifact = {
        "id": draft_id,
        "artifact_type": "report_draft",
        "name": "Report draft",
        "status": "ready",
        "source_table_id": record["id"],
        "transform_revision": record["revision"],
        "sections": sections,
    }
    saved = upsert_artifact(str(session_id), str(folder_id), str(user_id), artifact)
    return {"artifact": saved, "section": section}


def generate_narrative(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, focus: str = "key findings", **_: Any) -> dict[str, Any]:
    record, snapshot = _context(folder_id, user_id, session_id, selected_table_id)
    return {
        "focus": focus,
        "instruction": "Write the narrative from this evidence only; do not invent values.",
        "data_summary": get_data_summary(folder_id, user_id, session_id, record["id"]),
        "charts": [chart for chart in snapshot.get("charts", []) if not chart.get("stale")],
    }


def finalize(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, title: str = "EventHorizon Analysis Report", **_: Any) -> dict[str, Any]:
    record, snapshot = _context(folder_id, user_id, session_id, selected_table_id)
    drafts = snapshot.get("report_drafts", [])
    sections = list((drafts[-1] if drafts else {}).get("sections") or [])
    return {
        "ready_to_finalize": True,
        "title": title,
        "table_id": record["id"],
        "transform_revision": record["revision"],
        "sections": sections,
        "chart_ids": [chart.get("id") for chart in snapshot.get("charts", []) if not chart.get("stale")],
        "supported_formats": ["pdf", "html", "pptx", "docx"],
    }


REPORT_TOOLS = [
    ToolSpec("report_get_data_summary", "Get report data summary", "Return grounded metadata for the selected prepared table.", _obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id", "session_id"]), get_data_summary, READ_ONLY, SURFACES),
    ToolSpec("report_list_charts", "List report charts", "List persisted, non-stale charts for the selected prepared table.", _obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id", "session_id"]), list_charts, READ_ONLY, SURFACES),
    ToolSpec("report_create_section", "Create or update a report section", "Persist a grounded section in the session report draft.", _obj({"folder_id": FOLDER, "session_id": SESSION, "title": {"type": "string"}, "content": {"type": "string"}, "chart_ids": {"type": "array", "items": {"type": "string"}}}, ["folder_id", "session_id", "title", "content"]), create_section, WRITE, SURFACES),
    ToolSpec("report_generate_narrative", "Gather narrative evidence", "Return the selected table summary and real chart evidence for a report narrative.", _obj({"folder_id": FOLDER, "session_id": SESSION, "focus": {"type": "string"}}, ["folder_id", "session_id"]), generate_narrative, READ_ONLY, SURFACES),
    ToolSpec("report_finalize", "Finalize report plan", "Return the persisted outline, chart references, and validated export context.", _obj({"folder_id": FOLDER, "session_id": SESSION, "title": {"type": "string"}}, ["folder_id", "session_id"]), finalize, READ_ONLY, SURFACES),
]
