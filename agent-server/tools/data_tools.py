"""Shared EventHorizon data-tool registry.

This module is the **single source of truth** for the folder-scoped data tools.
Both the MCP server (`mcp_server/server.py`) and the in-process agent provider
(`tools/inprocess.py`) build their toolset from :data:`DATA_TOOLS`, so there is
exactly one definition of each tool's schema and behaviour.

Design goals
------------
- **Token-efficient**: tools return schemas, aggregates, statistics, and small
  capped samples - never large row dumps. Every result is row- and size-capped.
- **Big-data safe**: heavy work is pushed into PostgreSQL (server-side GROUP BY,
  aggregate functions, planner row estimates via ``pg_class``), so a 1M-row
  table is summarised without streaming its rows through the model.
- **Read-only + folder-scoped**: all handlers go through the hardened
  ``tools/postgres`` layer, which enforces SELECT-only, folder scoping, a
  statement timeout, and row caps.

Every handler has the signature ``handler(folder_id, user_id, **arguments)`` and
returns a JSON-serialisable ``dict``.
"""

from __future__ import annotations

import copy
from typing import Any

from tools.spec import ToolSpec

from tools.postgres import (
    _quote_identifier,
    describe_tables,
    estimated_row_count,
    execute_select,
    get_folder_status,
    resolve_table_name,
)

# Hard caps applied on top of whatever the model requests, so token usage stays
# bounded regardless of table size.
MAX_QUERY_ROWS = 50
MAX_SAMPLE_ROWS = 20
MAX_AGGREGATE_ROWS = 100
MAX_TOPK = 25
MAX_PROFILE_COLUMNS = 15

_VALID_OPS = {"count", "count_distinct", "sum", "avg", "min", "max"}



def _clamp(value: Any, default: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


def _columns_for(folder_id: str | None, table_name: str, user_id: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    """Return (friendly_name, columns) for a folder table, or (None, []) if absent."""
    friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
    if not friendly:
        return None, []
    described = describe_tables(folder_id, user_id=user_id)
    tables = described.get("tables", []) if isinstance(described, dict) else []
    match = next((t for t in tables if str(t.get("name", "")).lower() == friendly.lower()), None)
    return friendly, (match.get("columns", []) if match else [])


def _is_numeric(sql_type: str) -> bool:
    lowered = str(sql_type or "").lower()
    return any(tok in lowered for tok in ("int", "numeric", "decimal", "real", "double", "float", "money", "serial"))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _list_tables(folder_id: str | None = None, user_id: str | None = None, **_: Any) -> dict[str, Any]:
    status = get_folder_status(folder_id, user_id=user_id)
    names = [t for t in (status.get("tables") or []) if t]
    tables = []
    for name in names:
        est = estimated_row_count(folder_id, name, user_id=user_id)
        tables.append({"name": name, "estimated_row_count": est.get("estimated_row_count", -1)})
    return {
        "folder_id": folder_id,
        "has_data": bool(status.get("has_data")),
        "table_count": len(names),
        "tables": tables,
    }


def _describe(folder_id: str | None = None, user_id: str | None = None, table_name: str | None = None, **_: Any) -> dict[str, Any]:
    result = describe_tables(folder_id, user_id=user_id)
    tables = result.get("tables", []) if isinstance(result, dict) else []
    if table_name:
        friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
        tables = [t for t in tables if friendly and str(t.get("name", "")).lower() == friendly.lower()]
    if not tables:
        return {
            "folder_id": folder_id,
            "tables": [],
            "message": (result.get("warning") if isinstance(result, dict) else None)
            or "No matching tables. Call data_list_tables to see available tables.",
        }
    return {"folder_id": folder_id, "table_count": len(tables), "tables": tables}


def _run_query(folder_id: str | None = None, user_id: str | None = None, sql: str = "", limit: int | None = None, **_: Any) -> dict[str, Any]:
    max_rows = _clamp(limit, MAX_QUERY_ROWS, MAX_QUERY_ROWS) if limit is not None else MAX_QUERY_ROWS
    result = execute_select(folder_id, sql, user_id=user_id, max_rows=max_rows)
    return {
        "folder_id": folder_id,
        "query": sql,
        "row_count": int(result.get("row_count", len(result.get("rows", []) or []))),
        "truncated": bool(result.get("truncated", False)),
        "rows": result.get("rows", []) or [],
        "error": result.get("error"),
    }


def _row_count(folder_id: str | None = None, user_id: str | None = None, table_name: str = "", exact: bool = False, **_: Any) -> dict[str, Any]:
    friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    if not exact:
        return estimated_row_count(folder_id, friendly, user_id=user_id)
    result = execute_select(folder_id, f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(friendly)}", user_id=user_id, max_rows=1)
    if result.get("error"):
        return {"table": friendly, "error": result["error"]}
    rows = result.get("rows", [])
    count = rows[0].get("row_count") if rows else None
    return {"table": friendly, "row_count": count, "exact": True}


def _aggregate(
    folder_id: str | None = None,
    user_id: str | None = None,
    table_name: str = "",
    group_by: list[str] | None = None,
    metrics: list[str] | None = None,
    limit: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    friendly, columns = _columns_for(folder_id, table_name, user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    col_names = {str(c.get("name")).lower(): str(c.get("name")) for c in columns if c.get("name")}

    group_by = group_by or []
    metrics = metrics or ["count"]
    invalid = [g for g in group_by if str(g).lower() not in col_names]
    if invalid:
        return {"error": f"Unknown group_by column(s): {', '.join(invalid)}. Available: {', '.join(col_names.values())}."}

    select_parts: list[str] = [_quote_identifier(col_names[str(g).lower()]) for g in group_by]
    for metric in metrics:
        op, _, column = str(metric).partition(":")
        op = op.strip().lower()
        if op not in _VALID_OPS:
            return {"error": f"Unknown metric op '{op}'. Allowed: {', '.join(sorted(_VALID_OPS))}."}
        if op == "count" and not column:
            select_parts.append("COUNT(*) AS count")
            continue
        if not column or column.lower() not in col_names:
            return {"error": f"Metric '{metric}' needs a valid column. Available: {', '.join(col_names.values())}."}
        real = col_names[column.lower()]
        alias = _quote_identifier(f"{op}_{real}")
        if op == "count_distinct":
            select_parts.append(f"COUNT(DISTINCT {_quote_identifier(real)}) AS {alias}")
        else:
            select_parts.append(f"{op.upper()}({_quote_identifier(real)}) AS {alias}")

    sql = f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(friendly)}"
    if group_by:
        group_cols = ", ".join(_quote_identifier(col_names[str(g).lower()]) for g in group_by)
        sql += f" GROUP BY {group_cols} ORDER BY {group_cols}"
    max_rows = _clamp(limit, MAX_AGGREGATE_ROWS, MAX_AGGREGATE_ROWS) if limit is not None else MAX_AGGREGATE_ROWS
    result = execute_select(folder_id, sql, user_id=user_id, max_rows=max_rows)
    if result.get("error"):
        return {"table": friendly, "query": sql, "error": result["error"]}
    return {"table": friendly, "group_by": group_by, "rows": result.get("rows", []), "row_count": result.get("row_count", 0), "truncated": result.get("truncated", False)}


def _column_stats(folder_id: str | None = None, user_id: str | None = None, table_name: str = "", column: str = "", **_: Any) -> dict[str, Any]:
    friendly, columns = _columns_for(folder_id, table_name, user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    col_map = {str(c.get("name")).lower(): c for c in columns if c.get("name")}
    meta = col_map.get(str(column).lower())
    if not meta:
        return {"error": f"Column '{column}' not found in {friendly}. Available: {', '.join(str(c.get('name')) for c in columns)}."}
    real = str(meta.get("name"))
    q = _quote_identifier(real)
    if _is_numeric(meta.get("type", "")):
        sql = (
            f"SELECT COUNT(*) AS total, COUNT({q}) AS non_null, "
            f"MIN({q}) AS min, MAX({q}) AS max, AVG({q}) AS avg, "
            f"STDDEV({q}) AS stddev, COUNT(DISTINCT {q}) AS distinct_count FROM {_quote_identifier(friendly)}"
        )
        result = execute_select(folder_id, sql, user_id=user_id, max_rows=1)
        if result.get("error"):
            return {"table": friendly, "column": real, "error": result["error"]}
        rows = result.get("rows", [])
        return {"table": friendly, "column": real, "kind": "numeric", "stats": rows[0] if rows else {}}
    # Categorical: distinct count + top-K frequencies (small payload).
    sql = (
        f"SELECT {q} AS value, COUNT(*) AS count FROM {_quote_identifier(friendly)} "
        f"GROUP BY {q} ORDER BY count DESC LIMIT {MAX_TOPK}"
    )
    result = execute_select(folder_id, sql, user_id=user_id, max_rows=MAX_TOPK)
    if result.get("error"):
        return {"table": friendly, "column": real, "error": result["error"]}
    return {"table": friendly, "column": real, "kind": "categorical", "top_values": result.get("rows", [])}


def _sample_rows(folder_id: str | None = None, user_id: str | None = None, table_name: str = "", limit: int | None = None, **_: Any) -> dict[str, Any]:
    friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    max_rows = _clamp(limit, 5, MAX_SAMPLE_ROWS) if limit is not None else 5
    result = execute_select(folder_id, f"SELECT * FROM {_quote_identifier(friendly)} LIMIT {max_rows}", user_id=user_id, max_rows=max_rows)
    if result.get("error"):
        return {"table": friendly, "error": result["error"]}
    return {"table": friendly, "rows": result.get("rows", []), "row_count": result.get("row_count", 0)}


def _search(folder_id: str | None = None, user_id: str | None = None, table_name: str = "", column: str = "", value: str = "", limit: int | None = None, **_: Any) -> dict[str, Any]:
    friendly, columns = _columns_for(folder_id, table_name, user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    col_map = {str(c.get("name")).lower(): str(c.get("name")) for c in columns if c.get("name")}
    real = col_map.get(str(column).lower())
    if not real:
        return {"error": f"Column '{column}' not found in {friendly}."}
    # Escape the search literal for safe embedding in a read-only SELECT.
    literal = "%" + str(value).replace("'", "''") + "%"
    max_rows = _clamp(limit, 20, MAX_SAMPLE_ROWS) if limit is not None else 20
    sql = f"SELECT * FROM {_quote_identifier(friendly)} WHERE CAST({_quote_identifier(real)} AS TEXT) ILIKE '{literal}' LIMIT {max_rows}"
    result = execute_select(folder_id, sql, user_id=user_id, max_rows=max_rows)
    if result.get("error"):
        return {"table": friendly, "error": result["error"]}
    return {"table": friendly, "column": real, "value": value, "rows": result.get("rows", []), "row_count": result.get("row_count", 0), "truncated": result.get("truncated", False)}


def _profile_nulls(folder_id: str | None = None, user_id: str | None = None, table_name: str = "", **_: Any) -> dict[str, Any]:
    friendly, columns = _columns_for(folder_id, table_name, user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    col_names = [str(c.get("name")) for c in columns if c.get("name")][:MAX_PROFILE_COLUMNS]
    if not col_names:
        return {"table": friendly, "error": "Table has no inspectable columns."}
    expressions = ", ".join(
        f"SUM(CASE WHEN {_quote_identifier(col)} IS NULL THEN 1 ELSE 0 END) AS {_quote_identifier(f'{col}_nulls')}"
        for col in col_names
    )
    sql = f"SELECT COUNT(*) AS row_count, {expressions} FROM {_quote_identifier(friendly)}"
    result = execute_select(folder_id, sql, user_id=user_id, max_rows=1)
    if result.get("error"):
        return {"table": friendly, "error": result["error"]}
    rows = result.get("rows", [])
    return {"table": friendly, "columns_profiled": col_names, "profile": rows[0] if rows else {}}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


_FOLDER = {"type": "string", "description": "EventHorizon folder UUID whose data you want to access."}
_TABLE = {"type": "string", "description": "A folder-scoped table name from data_list_tables."}


DATA_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="data_list_tables",
        title="List folder tables",
        description="List the tables in an EventHorizon folder with a fast row-count estimate for each. Start here to discover what data exists before querying.",
        parameters=_obj({"folder_id": _FOLDER}, ["folder_id"]),
        handler=_list_tables,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_describe_tables",
        title="Describe folder tables",
        description="Describe table schemas (columns, types, nullability, estimated rows, and up to 3 sample rows). Pass table_name to describe just one table and save tokens.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": {"type": "string", "description": "Optional single table to describe."}}, ["folder_id"]),
        handler=_describe,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_row_count",
        title="Count rows in a table",
        description="Return the row count of a table. By default returns an instant planner ESTIMATE (safe for millions of rows); set exact=true only when a precise count is essential.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": _TABLE, "exact": {"type": "boolean", "description": "Return an exact COUNT(*) instead of the fast estimate.", "default": False}}, ["folder_id", "table_name"]),
        handler=_row_count,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_aggregate",
        title="Aggregate / group-by a table",
        description="Run a server-side GROUP BY aggregation and return only the small grouped result - the right tool for summarising large tables without reading raw rows. metrics are strings like 'count', 'sum:amount', 'avg:price', 'count_distinct:user_id'.",
        parameters=_obj({
            "folder_id": _FOLDER,
            "table_name": _TABLE,
            "group_by": {"type": "array", "items": {"type": "string"}, "description": "Columns to group by (may be empty for a grand total)."},
            "metrics": {"type": "array", "items": {"type": "string"}, "description": "Aggregations as 'op' or 'op:column'. op in count, count_distinct, sum, avg, min, max."},
            "limit": {"type": "integer", "description": f"Max grouped rows (default/max {MAX_AGGREGATE_ROWS})."},
        }, ["folder_id", "table_name"]),
        handler=_aggregate,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_column_stats",
        title="Profile a single column",
        description="Compute server-side statistics for one column: numeric columns return min/max/avg/stddev/distinct/non-null; text columns return the top values by frequency. Tiny payload, safe on huge tables.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": _TABLE, "column": {"type": "string", "description": "Column name to profile."}}, ["folder_id", "table_name", "column"]),
        handler=_column_stats,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_sample_rows",
        title="Sample a few rows",
        description="Return a handful of example rows (default 5, max 20) to understand a table's shape. Never returns large row sets.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": _TABLE, "limit": {"type": "integer", "description": f"Number of rows (default 5, max {MAX_SAMPLE_ROWS})."}}, ["folder_id", "table_name"]),
        handler=_sample_rows,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_search",
        title="Search a column for a value",
        description="Find rows where a column contains a value (case-insensitive substring match), returning a small capped result. Good for locating specific records in a large table.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": _TABLE, "column": {"type": "string", "description": "Column to search."}, "value": {"type": "string", "description": "Substring to match."}, "limit": {"type": "integer", "description": f"Max rows (default 20, max {MAX_SAMPLE_ROWS})."}}, ["folder_id", "table_name", "column", "value"]),
        handler=_search,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_run_query",
        title="Run a read-only SELECT query",
        description="Run one folder-scoped, read-only SELECT and return capped rows. Prefer data_aggregate / data_column_stats for summaries; use this for custom slices. Only a single SELECT is allowed; mutating SQL, multiple statements, system catalogs, and schema-qualified names are rejected.",
        parameters=_obj({"folder_id": _FOLDER, "sql": {"type": "string", "description": "A single SELECT statement referencing only this folder's tables."}, "limit": {"type": "integer", "description": f"Max rows to return (default/max {MAX_QUERY_ROWS})."}}, ["folder_id", "sql"]),
        handler=_run_query,
        annotations=_READ_ONLY,
    ),
    ToolSpec(
        name="data_profile_nulls",
        title="Profile null values in a table",
        description="Count NULL values per column (first 15 columns) for a quick data-quality check.",
        parameters=_obj({"folder_id": _FOLDER, "table_name": _TABLE}, ["folder_id", "table_name"]),
        handler=_profile_nulls,
        annotations=_READ_ONLY,
    ),
]

from tools.canvas_tools import CANVAS_TOOLS
from tools.prepare_tools import PREPARE_TOOLS
from tools.report_tools import REPORT_TOOLS
from tools.visualize_tools import VISUALIZE_TOOLS

DATA_TOOLS.extend(PREPARE_TOOLS)
DATA_TOOLS.extend(VISUALIZE_TOOLS)
DATA_TOOLS.extend(REPORT_TOOLS)
DATA_TOOLS.extend(CANVAS_TOOLS)

TOOLS_BY_NAME: dict[str, ToolSpec] = {tool.name: tool for tool in DATA_TOOLS}


_CONTEXT_ARGUMENTS = {"folder_id", "session_id", "selected_table_id", "selected_table_name", "user_id"}


def openai_tool_schemas(surface: str | None = None, *, include_context: bool = True) -> list[dict[str, Any]]:
    """Return function schemas filtered to the active workspace surface."""
    selected = [
        tool
        for tool in DATA_TOOLS
        if surface is None or not tool.surfaces or surface in tool.surfaces
    ]
    schemas: list[dict[str, Any]] = []
    for tool in selected:
        parameters = copy.deepcopy(tool.parameters)
        if not include_context:
            properties = parameters.get("properties") or {}
            for key in _CONTEXT_ARGUMENTS:
                properties.pop(key, None)
            parameters["required"] = [
                key for key in (parameters.get("required") or []) if key not in _CONTEXT_ARGUMENTS
            ]
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": parameters,
                },
            }
        )
    return schemas

def run_tool(name: str, folder_id: str | None, user_id: str | None = None, surface: str | None = None, **arguments: Any) -> dict[str, Any]:
    """Dispatch a data tool by name through the shared registry.

    Shared entry point for both the MCP server and any other host: it forces the
    folder scope and trusted user identity into the handler so callers cannot
    accidentally omit them.
    """
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return {"error": f"Unknown tool '{name}'."}
    if surface and spec.surfaces and surface not in spec.surfaces:
        return {"error": f"Tool '{name}' is not available on the {surface} surface."}
    arguments.pop("folder_id", None)
    arguments.pop("user_id", None)
    return spec.handler(folder_id=folder_id, user_id=user_id, **arguments)
