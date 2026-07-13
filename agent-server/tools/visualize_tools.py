from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from shared.workspace_store import (
    WorkspaceStoreError,
    delete_artifact,
    get_artifact,
    get_workspace_snapshot,
    resolve_transform_table_record,
    upsert_artifact,
)
from tools.postgres import _quote_identifier, describe_tables, execute_select
from tools.spec import ToolSpec


READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
SURFACES = frozenset({"dashboard"})
CHART_TYPES = {"line", "bar", "area", "pie", "radial"}
AGGREGATIONS = {"sum", "avg", "min", "max", "count"}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


FOLDER = {"type": "string", "description": "EventHorizon folder UUID."}
SESSION = {"type": "string", "description": "Active EventHorizon session UUID."}


def _selected(
    folder_id: str | None,
    user_id: str | None,
    session_id: str | None,
    selected_table_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not folder_id or not user_id or not session_id:
        raise WorkspaceStoreError("Visualize requires an active folder session.", code="missing_visualize_context")
    snapshot = get_workspace_snapshot(session_id, folder_id, user_id)
    workspace = snapshot.get("workspace") or {}
    selected_id = selected_table_id or workspace.get("selected_table_id")
    if not selected_id:
        raise WorkspaceStoreError("Create and select a prepared table in Prepare first.", code="missing_transform", status_code=409)
    if workspace.get("selected_table_id") and str(selected_id) != str(workspace.get("selected_table_id")):
        raise WorkspaceStoreError("The requested table is not the session's selected prepared table.", code="selection_mismatch", status_code=403)
    record = resolve_transform_table_record(folder_id, str(selected_id))
    if not record:
        raise WorkspaceStoreError("The selected prepared table no longer exists.", code="transform_not_found", status_code=404)
    return record, snapshot


def _schema(folder_id: str, user_id: str, table_name: str) -> dict[str, Any]:
    described = describe_tables(folder_id, user_id=user_id)
    table = next((item for item in described.get("tables", []) if item.get("name") == table_name), None)
    if not table:
        raise WorkspaceStoreError("The selected prepared table could not be described.", code="transform_schema_missing", status_code=404)
    return table


def _column_map(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(column.get("name") or "").lower(): column for column in table.get("columns", []) if column.get("name")}


def _require_column(columns: dict[str, dict[str, Any]], name: str) -> str:
    column = columns.get(str(name).lower())
    if not column:
        raise WorkspaceStoreError(f"Column '{name}' does not exist in the selected prepared table.", code="column_not_found")
    return str(column["name"])


def get_schema(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    return {"table_id": record["id"], "table_name": record["name"], "revision": record["revision"], "columns": table.get("columns", []), "estimated_row_count": table.get("estimated_row_count", -1)}


def column_stats(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, column: str = "", **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    real = _require_column(_column_map(table), column)
    q = _quote_identifier(real)
    result = execute_select(
        folder_id,
        f"SELECT COUNT(*) AS total, COUNT({q}) AS non_null, COUNT(DISTINCT {q}) AS distinct_count, MIN({q}) AS min, MAX({q}) AS max FROM {_quote_identifier(record['name'])}",
        user_id=user_id,
        max_rows=1,
    )
    return {"table_id": record["id"], "column": real, **result}


def aggregate(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, group_by: str = "", value_field: str = "", aggregation: str = "sum", limit: int = 100, **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    columns = _column_map(table)
    group = _require_column(columns, group_by)
    op = str(aggregation or "sum").lower()
    if op not in AGGREGATIONS:
        raise WorkspaceStoreError(f"Unsupported aggregation '{aggregation}'.", code="invalid_aggregation")
    if op == "count":
        expression = "COUNT(*)"
    else:
        value = _require_column(columns, value_field)
        expression = f"{op.upper()}({_quote_identifier(value)})"
    capped = max(1, min(int(limit or 100), 200))
    query = (
        f"SELECT {_quote_identifier(group)} AS label, {expression} AS value "
        f"FROM {_quote_identifier(record['name'])} "
        f"GROUP BY {_quote_identifier(group)} ORDER BY value DESC LIMIT {capped}"
    )
    result = execute_select(folder_id, query, user_id=user_id, max_rows=capped)
    return {"table_id": record["id"], "table_name": record["name"], "group_by": group, "aggregation": op, **result}


def correlation(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, x_field: str = "", y_field: str = "", **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    columns = _column_map(table)
    x = _require_column(columns, x_field)
    y = _require_column(columns, y_field)
    query = f"SELECT CORR({_quote_identifier(x)}::numeric, {_quote_identifier(y)}::numeric) AS correlation FROM {_quote_identifier(record['name'])}"
    result = execute_select(folder_id, query, user_id=user_id, max_rows=1)
    return {"table_id": record["id"], "x_field": x, "y_field": y, **result}


def time_series(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, time_field: str = "", value_field: str = "", aggregation: str = "sum", granularity: str = "month", limit: int = 200, **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    columns = _column_map(table)
    time_column = _require_column(columns, time_field)
    value_column = _require_column(columns, value_field)
    unit = str(granularity or "month").lower()
    if unit not in {"day", "week", "month", "quarter", "year"}:
        raise WorkspaceStoreError("Granularity must be day, week, month, quarter, or year.", code="invalid_granularity")
    op = str(aggregation or "sum").lower()
    if op not in AGGREGATIONS - {"count"}:
        raise WorkspaceStoreError("Time-series aggregation must be sum, avg, min, or max.", code="invalid_aggregation")
    capped = max(1, min(int(limit or 200), 300))
    bucket = f"DATE_TRUNC('{unit}', {_quote_identifier(time_column)}::timestamp)"
    query = (
        f"SELECT {bucket} AS label, {op.upper()}({_quote_identifier(value_column)}) AS value "
        f"FROM {_quote_identifier(record['name'])} GROUP BY 1 ORDER BY 1 LIMIT {capped}"
    )
    result = execute_select(folder_id, query, user_id=user_id, max_rows=capped)
    return {"table_id": record["id"], "time_field": time_column, "value_field": value_column, "granularity": unit, **result}


def suggest_charts(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    numeric = []
    temporal = []
    categorical = []
    for column in table.get("columns", []):
        name = str(column.get("name") or "")
        data_type = str(column.get("type") or "").lower()
        if any(token in data_type for token in ("int", "numeric", "decimal", "real", "double", "float")):
            numeric.append(name)
        elif any(token in data_type for token in ("date", "time")):
            temporal.append(name)
        else:
            categorical.append(name)
    suggestions = [{"type": "kpi", "aggregation": "count", "reason": "Show the total prepared row count."}]
    if numeric:
        suggestions.append({"type": "kpi", "aggregation": "sum", "y_field": numeric[0], "reason": f"Summarize total {numeric[0]}."})
    if temporal and numeric:
        suggestions.append({"type": "line", "x_field": temporal[0], "y_field": numeric[0], "reason": "Show change over time."})
    if categorical and numeric:
        suggestions.append({"type": "bar", "x_field": categorical[0], "y_field": numeric[0], "reason": "Compare values across categories."})
        suggestions.append({"type": "pie", "x_field": categorical[0], "y_field": numeric[0], "reason": "Show proportional contribution for a small category set."})
    return {"table_id": record["id"], "suggestions": suggestions[:5]}


def create_chart(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, title: str = "", chart_type: str = "bar", x_field: str = "", y_field: str = "", aggregation: str = "sum", limit: int = 100, **_: Any) -> dict[str, Any]:
    record, snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    kind = str(chart_type or "bar").lower()
    if kind not in CHART_TYPES:
        raise WorkspaceStoreError(f"Unsupported chart type '{chart_type}'.", code="unsupported_chart")
    aggregated = aggregate(
        folder_id=folder_id,
        user_id=user_id,
        session_id=session_id,
        selected_table_id=record["id"],
        group_by=x_field,
        value_field=y_field,
        aggregation=aggregation,
        limit=limit,
    )
    if aggregated.get("error"):
        return aggregated
    rows = aggregated.get("rows") or []
    chart_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    artifact = {
        "id": chart_id,
        "artifact_type": "chart",
        "type": kind,
        "name": title or f"{y_field or aggregation} by {x_field}",
        "title": title or f"{y_field or aggregation} by {x_field}",
        "sourceTableId": record["id"],
        "source_table_id": record["id"],
        "xField": x_field,
        "yFields": [y_field] if y_field else [],
        "transformRevision": int(record.get("revision") or 0),
        "transform_revision": int(record.get("revision") or 0),
        "createdAt": now,
        "status": "draft",
        "data": [{"label": str(row.get("label") or ""), "value": float(row.get("value") or 0)} for row in rows],
        "config": {
            "primaryColor": "#F4F4F5",
            "showGrid": True,
            "showLegend": len(rows) > 1,
            "showTooltip": True,
        },
        "position": {"x": 0, "y": len(snapshot.get("charts") or []), "w": 12, "h": 6},
    }
    return {
        "artifact": artifact,
        "row_count": len(rows),
        "persisted": False,
        "message": f"Created a {kind} chart preview. The user can add it to the dashboard from the chat.",
    }


def create_kpi(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, title: str = "", value_field: str = "", aggregation: str = "count", **_: Any) -> dict[str, Any]:
    record, snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    table = _schema(str(folder_id), str(user_id), record["name"])
    op = str(aggregation or "count").lower()
    if op not in AGGREGATIONS:
        raise WorkspaceStoreError(f"Unsupported aggregation '{aggregation}'.", code="invalid_aggregation")
    if op == "count":
        expression = "COUNT(*)"
        default_title = "Total rows"
    else:
        value = _require_column(_column_map(table), value_field)
        expression = f"{op.upper()}({_quote_identifier(value)})"
        default_title = f"{op.title()} {value}"
    query = f"SELECT {expression} AS value FROM {_quote_identifier(record['name'])}"
    result = execute_select(folder_id, query, user_id=user_id, max_rows=1)
    if result.get("error"):
        return result
    rows = result.get("rows") or []
    raw_value = rows[0].get("value") if rows else 0
    try:
        numeric_value = float(raw_value or 0)
    except (TypeError, ValueError):
        numeric_value = 0.0
    chart_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    artifact = {
        "id": chart_id,
        "artifact_type": "chart",
        "type": "kpi",
        "name": title or default_title,
        "title": title or default_title,
        "sourceTableId": record["id"],
        "source_table_id": record["id"],
        "xField": "",
        "yFields": [value_field] if value_field else [],
        "transformRevision": int(record.get("revision") or 0),
        "transform_revision": int(record.get("revision") or 0),
        "createdAt": now,
        "status": "draft",
        "data": [{"label": title or default_title, "value": numeric_value}],
        "config": {
            "primaryColor": "#F4F4F5",
            "showGrid": False,
            "showLegend": False,
            "showTooltip": False,
        },
        "position": {"x": 0, "y": len(snapshot.get("charts") or []), "w": 4, "h": 3},
    }
    return {
        "artifact": artifact,
        "persisted": False,
        "message": "Created a KPI preview. The user can add it to the dashboard from the chat.",
    }


def update_chart(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, chart_id: str = "", title: str | None = None, chart_type: str | None = None, **_: Any) -> dict[str, Any]:
    record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    existing = get_artifact(chart_id, str(folder_id), str(user_id))
    if not existing or existing.get("artifact_type") != "chart" or existing.get("session_id", session_id) != session_id:
        return {"error": "Chart not found in this session."}
    if existing.get("source_table_id") != record["id"]:
        return {"error": "The chart belongs to a different prepared table revision."}
    if chart_type:
        kind = str(chart_type).lower()
        if kind not in CHART_TYPES:
            return {"error": f"Unsupported chart type '{chart_type}'."}
        existing["type"] = kind
    if title:
        existing["title"] = title
        existing["name"] = title
    saved = upsert_artifact(str(session_id), str(folder_id), str(user_id), existing)
    return {"artifact": saved, "message": "Chart updated."}


def remove_chart(folder_id: str | None = None, user_id: str | None = None, session_id: str | None = None, selected_table_id: str | None = None, chart_id: str = "", **_: Any) -> dict[str, Any]:
    _record, _snapshot = _selected(folder_id, user_id, session_id, selected_table_id)
    deleted = delete_artifact(str(session_id), str(folder_id), str(user_id), chart_id)
    return {"deleted": deleted, "artifact_id": chart_id}


VISUALIZE_TOOLS = [
    ToolSpec("viz_get_schema", "Get prepared-table schema", "Return the schema of the session's selected prepared table.", _obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id", "session_id"]), get_schema, READ_ONLY, SURFACES),
    ToolSpec("viz_column_stats", "Profile a prepared-table column", "Compute statistics for one column in the selected prepared table.", _obj({"folder_id": FOLDER, "session_id": SESSION, "column": {"type": "string"}}, ["folder_id", "session_id", "column"]), column_stats, READ_ONLY, SURFACES),
    ToolSpec("viz_aggregate", "Aggregate selected prepared data", "Group and aggregate the selected prepared table.", _obj({"folder_id": FOLDER, "session_id": SESSION, "group_by": {"type": "string"}, "value_field": {"type": "string"}, "aggregation": {"type": "string", "enum": sorted(AGGREGATIONS)}, "limit": {"type": "integer"}}, ["folder_id", "session_id", "group_by", "aggregation"]), aggregate, READ_ONLY, SURFACES),
    ToolSpec("viz_correlation", "Calculate a correlation", "Calculate Pearson correlation between two selected-table columns.", _obj({"folder_id": FOLDER, "session_id": SESSION, "x_field": {"type": "string"}, "y_field": {"type": "string"}}, ["folder_id", "session_id", "x_field", "y_field"]), correlation, READ_ONLY, SURFACES),
    ToolSpec("viz_time_series", "Build time-series data", "Aggregate the selected prepared table into a time series.", _obj({"folder_id": FOLDER, "session_id": SESSION, "time_field": {"type": "string"}, "value_field": {"type": "string"}, "aggregation": {"type": "string"}, "granularity": {"type": "string"}, "limit": {"type": "integer"}}, ["folder_id", "session_id", "time_field", "value_field"]), time_series, READ_ONLY, SURFACES),
    ToolSpec("viz_suggest_charts", "Suggest charts", "Suggest grounded chart configurations from the selected prepared-table schema.", _obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id", "session_id"]), suggest_charts, READ_ONLY, SURFACES),
    ToolSpec("viz_create_chart", "Create a chart preview", "Query the selected prepared table and return a transient ChartSpec preview. The UI persists it only when the user chooses Add to dashboard.", _obj({"folder_id": FOLDER, "session_id": SESSION, "title": {"type": "string"}, "chart_type": {"type": "string", "enum": sorted(CHART_TYPES)}, "x_field": {"type": "string"}, "y_field": {"type": "string"}, "aggregation": {"type": "string", "enum": sorted(AGGREGATIONS)}, "limit": {"type": "integer"}}, ["folder_id", "session_id", "chart_type", "x_field", "aggregation"]), create_chart, READ_ONLY, SURFACES),
    ToolSpec("viz_create_kpi", "Create a KPI preview", "Query one grounded aggregate from the selected prepared table and return a transient KPI preview. The UI persists it only when the user chooses Add to dashboard.", _obj({"folder_id": FOLDER, "session_id": SESSION, "title": {"type": "string"}, "value_field": {"type": "string"}, "aggregation": {"type": "string", "enum": sorted(AGGREGATIONS)}}, ["folder_id", "session_id", "aggregation"]), create_kpi, READ_ONLY, SURFACES),
    ToolSpec("viz_update_chart", "Update a chart", "Update the title or type of a persisted chart in this session.", _obj({"folder_id": FOLDER, "session_id": SESSION, "chart_id": {"type": "string"}, "title": {"type": "string"}, "chart_type": {"type": "string", "enum": sorted(CHART_TYPES)}}, ["folder_id", "session_id", "chart_id"]), update_chart, WRITE, SURFACES),
    ToolSpec("viz_delete_chart", "Delete a chart", "Delete a persisted chart from this session.", _obj({"folder_id": FOLDER, "session_id": SESSION, "chart_id": {"type": "string"}}, ["folder_id", "session_id", "chart_id"]), remove_chart, WRITE, SURFACES),
]
