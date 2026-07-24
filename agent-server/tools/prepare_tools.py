from __future__ import annotations

from typing import Any

from tools.postgres import (
    _quote_identifier,
    create_transform_table,
    describe_tables,
    execute_select,
    resolve_table_name,
    validate_transform_select,
)
from tools.spec import ToolSpec


READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
SURFACES = frozenset({"chat"})


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


FOLDER = {"type": "string", "description": "EventHorizon folder UUID."}
SESSION = {"type": "string", "description": "Active EventHorizon session UUID."}
TABLE = {"type": "string", "description": "Folder-scoped source table name."}


def detect_quality_issues(
    folder_id: str | None = None,
    user_id: str | None = None,
    table_name: str = "",
    **_: Any,
) -> dict[str, Any]:
    friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' was not found in this folder."}
    described = describe_tables(folder_id, user_id=user_id)
    table = next((t for t in described.get("tables", []) if t.get("name") == friendly), None)
    columns = [c.get("name") for c in (table or {}).get("columns", []) if c.get("name")][:20]
    if not columns:
        return {"table": friendly, "issues": [{"severity": "error", "message": "The table has no inspectable columns."}]}

    expressions = ", ".join(
        f"SUM(CASE WHEN {_quote_identifier(column)} IS NULL THEN 1 ELSE 0 END) AS {_quote_identifier(column + '_nulls')}"
        for column in columns
    )
    result = execute_select(
        folder_id,
        f"SELECT COUNT(*) AS row_count, {expressions} FROM {_quote_identifier(friendly)}",
        user_id=user_id,
        max_rows=1,
    )
    if result.get("error"):
        return {"table": friendly, "error": result["error"]}
    profile = (result.get("rows") or [{}])[0]
    row_count = int(profile.get("row_count") or 0)
    issues = []
    for column in columns:
        null_count = int(profile.get(column + "_nulls") or 0)
        if null_count:
            issues.append(
                {
                    "dimension": "completeness",
                    "column": column,
                    "severity": "warning",
                    "count": null_count,
                    "ratio": round(null_count / row_count, 4) if row_count else 0,
                    "message": f"{column} contains {null_count} null value(s).",
                }
            )
    return {
        "table": friendly,
        "row_count": row_count,
        "columns_profiled": columns,
        "issues": issues,
        "quality_score": round(max(0.0, 1.0 - sum(i.get("ratio", 0) for i in issues) / max(1, len(columns))) * 100, 2),
    }


def plan_transform(
    folder_id: str | None = None,
    user_id: str | None = None,
    select_sql: str = "",
    source_tables: list[str] | None = None,
    recipe: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    validation = validate_transform_select(folder_id, select_sql, user_id=user_id)
    if validation:
        return {"valid": False, "error": validation}
    return {
        "valid": True,
        "source_tables": source_tables or [],
        "recipe": recipe or ["Create the prepared table from the validated SELECT."],
        "write_behavior": "Creates a new agent-owned table; uploaded source tables remain unchanged.",
    }


def build_transform(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    select_sql: str = "",
    friendly_name: str = "prepared_data",
    source_tables: list[str] | None = None,
    recipe: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    return create_transform_table(
        folder_id=folder_id,
        user_id=user_id,
        session_id=session_id,
        select_sql=select_sql,
        friendly_name=friendly_name,
        source_tables=source_tables or [],
        recipe=recipe or [],
    )


def validate_transform(
    folder_id: str | None = None,
    user_id: str | None = None,
    selected_table_name: str | None = None,
    table_name: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return detect_quality_issues(
        folder_id=folder_id,
        user_id=user_id,
        table_name=table_name or selected_table_name or "",
    )


def get_transform_summary(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    if not folder_id or not user_id or not session_id:
        return {"error": "folder_id, user_id, and session_id are required."}
    from shared.workspace_store import get_workspace_snapshot

    snapshot = get_workspace_snapshot(session_id, folder_id, user_id)
    return {
        "selected_table": snapshot.get("selected_table"),
        "available_prepared_tables": snapshot.get("transform_tables", []),
        "transform_status": (snapshot.get("workspace") or {}).get("transform_status"),
    }


PREPARE_TOOLS = [
    ToolSpec(
        name="prepare_detect_quality_issues",
        title="Detect data-quality issues",
        description="Profile nulls and completeness for a source or prepared table without changing it.",
        parameters=_obj({"folder_id": FOLDER, "session_id": SESSION, "table_name": TABLE}, ["folder_id", "session_id", "table_name"]),
        handler=detect_quality_issues,
        annotations=READ_ONLY,
        surfaces=SURFACES,
    ),
    ToolSpec(
        name="prepare_plan_transform",
        title="Validate a transformation plan",
        description="Validate one folder-scoped SELECT and return a non-destructive transformation plan before creating a table.",
        parameters=_obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "select_sql": {"type": "string", "description": "A single SELECT over folder-scoped tables."},
                "source_tables": {"type": "array", "items": {"type": "string"}},
                "recipe": {"type": "array", "items": {"type": "string"}},
            },
            ["folder_id", "session_id", "select_sql"],
        ),
        handler=plan_transform,
        annotations=READ_ONLY,
        surfaces=SURFACES,
    ),
    ToolSpec(
        name="prepare_build_transform",
        title="Build the prepared table",
        description="Create the account's single allowed prepared table from a validated SELECT. Source tables are never modified.",
        parameters=_obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "select_sql": {"type": "string", "description": "A single validated SELECT over folder-scoped tables."},
                "friendly_name": {"type": "string", "description": "Short display name for the prepared table."},
                "source_tables": {"type": "array", "items": {"type": "string"}},
                "recipe": {"type": "array", "items": {"type": "string"}},
            },
            ["folder_id", "session_id", "select_sql"],
        ),
        handler=build_transform,
        annotations=WRITE,
        surfaces=SURFACES,
    ),
    ToolSpec(
        name="prepare_validate_transform",
        title="Validate the prepared table",
        description="Run completeness checks on the current prepared table.",
        parameters=_obj({"folder_id": FOLDER, "session_id": SESSION, "table_name": TABLE}, ["folder_id", "session_id"]),
        handler=validate_transform,
        annotations=READ_ONLY,
        surfaces=SURFACES,
    ),
    ToolSpec(
        name="prepare_get_transform_summary",
        title="Get prepared-table summary",
        description="Return the session's selected prepared table, revision, and transform status.",
        parameters=_obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id", "session_id"]),
        handler=get_transform_summary,
        annotations=READ_ONLY,
        surfaces=SURFACES,
    ),
]
