"""EventHorizon Data MCP server.

Exposes the EventHorizon folder-scoped PostgreSQL data layer as Model Context
Protocol (MCP) tools so any MCP client (Claude Desktop, Claude Code, the agent,
the MCP Inspector, ...) can safely explore and query a folder's data.

All tools are READ-ONLY and folder-scoped, and their behaviour is defined once
in the shared registry ``tools/data_tools.py`` - the same registry the agent
uses in-process. This server is a thin MCP surface over that registry: typed
wrappers give MCP clients rich argument schemas while the actual query logic
(server-side aggregation, planner row estimates, capped/token-efficient
results) lives in the shared handlers, so the MCP and the agent never drift.

Transports
----------
- stdio (default): for local clients such as Claude Desktop / Claude Code.
- streamable-http: set ``MCP_TRANSPORT=http`` for a remote/network server.

Run locally:
    python -m mcp_server.server
Run over HTTP:
    set MCP_TRANSPORT=http && python -m mcp_server.server
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import Field
from typing_extensions import Annotated

# Make the agent-server package importable and load shared env (DB credentials).
ROOT = Path(__file__).resolve().parents[1]  # .../agent-server
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT.parent / ".env")
    load_dotenv(ROOT / ".env")
except Exception:  # dotenv is optional at runtime
    pass

from mcp.server.fastmcp import FastMCP

from tools.postgres import DatabaseConfig
from tools.data_tools import DATA_TOOLS, run_tool

INSTRUCTIONS = """EventHorizon Data MCP server.

Use these tools to explore and query the data inside a single EventHorizon
folder. Every tool requires a `folder_id` (the EventHorizon folder UUID) and is
strictly read-only and scoped to that folder.

Recommended workflow:
1. `data_list_tables` - discover tables (with fast row-count estimates).
2. `data_describe_tables` - columns, types, and sample rows (pass table_name for one table).
3. For summaries of large tables, prefer `data_aggregate` (server-side GROUP BY)
   and `data_column_stats` (server-side statistics) instead of reading raw rows.
4. `data_row_count` returns an instant estimate by default (safe for millions of rows).
5. `data_sample_rows` / `data_search` return small capped previews.
6. `data_run_query` runs a custom single SELECT when the above are insufficient.

Only the folder-scoped table names returned by `data_list_tables` /
`data_describe_tables` may be referenced. Schema-qualified names and any
non-SELECT SQL are rejected. Results are capped so responses stay small.
"""

_STATELESS = os.getenv("MCP_TRANSPORT", "stdio").lower() == "http"

mcp = FastMCP(
    "EventHorizon Data",
    instructions=INSTRUCTIONS,
    stateless_http=_STATELESS,
    json_response=_STATELESS,
)

FolderId = Annotated[str, Field(description="EventHorizon folder UUID whose data you want to access.")]
TableName = Annotated[str, Field(description="A folder-scoped table name from data_list_tables.")]

_READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


def _trusted_user_id() -> str | None:
    """Identity of the caller, supplied out-of-band by a trusted host.

    The LLM never chooses *who* it is. When the EventHorizon agent (or another
    trusted host) spawns this server it injects ``EVENTHORIZON_AGENT_USER_ID``
    so the folder-access checks run against the real authenticated user.
    """
    return os.getenv("EVENTHORIZON_AGENT_USER_ID") or None


def _run(name: str, folder_id: str, **arguments: Any) -> dict[str, Any]:
    return run_tool(name, folder_id, user_id=_trusted_user_id(), **arguments)


@mcp.tool(title="List folder tables", annotations=_READ_ONLY)
def data_list_tables(folder_id: FolderId) -> dict[str, Any]:
    """List the tables in a folder with a fast row-count estimate for each.

    Start here to discover what data exists before running any query.
    """
    return _run("data_list_tables", folder_id)


@mcp.tool(title="Describe folder tables", annotations=_READ_ONLY)
def data_describe_tables(
    folder_id: FolderId,
    table_name: Annotated[str | None, Field(description="Optional single table to describe (saves tokens).")] = None,
) -> dict[str, Any]:
    """Describe table schemas: columns, types, nullability, estimated rows, and up to 3 sample rows."""
    return _run("data_describe_tables", folder_id, table_name=table_name)


@mcp.tool(title="Count rows in a table", annotations=_READ_ONLY)
def data_row_count(
    folder_id: FolderId,
    table_name: TableName,
    exact: Annotated[bool, Field(description="Return an exact COUNT(*) instead of the fast estimate.")] = False,
) -> dict[str, Any]:
    """Row count of a table. Returns an instant planner ESTIMATE by default (safe for millions of rows)."""
    return _run("data_row_count", folder_id, table_name=table_name, exact=exact)


@mcp.tool(title="Aggregate / group-by a table", annotations=_READ_ONLY)
def data_aggregate(
    folder_id: FolderId,
    table_name: TableName,
    group_by: Annotated[list[str] | None, Field(description="Columns to group by (empty for a grand total).")] = None,
    metrics: Annotated[list[str] | None, Field(description="Aggregations as 'op' or 'op:column'; op in count, count_distinct, sum, avg, min, max.")] = None,
    limit: Annotated[int | None, Field(description="Max grouped rows returned.")] = None,
) -> dict[str, Any]:
    """Run a server-side GROUP BY aggregation and return only the small grouped result.

    The right tool for summarising large tables without reading raw rows.
    """
    return _run("data_aggregate", folder_id, group_by=group_by, metrics=metrics, limit=limit, table_name=table_name)


@mcp.tool(title="Profile a single column", annotations=_READ_ONLY)
def data_column_stats(
    folder_id: FolderId,
    table_name: TableName,
    column: Annotated[str, Field(description="Column name to profile.")],
) -> dict[str, Any]:
    """Server-side statistics for one column: numeric -> min/max/avg/stddev/distinct; text -> top values."""
    return _run("data_column_stats", folder_id, column=column, table_name=table_name)


@mcp.tool(title="Sample a few rows", annotations=_READ_ONLY)
def data_sample_rows(
    folder_id: FolderId,
    table_name: TableName,
    limit: Annotated[int | None, Field(description="Number of rows (default 5, max 20).")] = None,
) -> dict[str, Any]:
    """Return a handful of example rows to understand a table's shape."""
    return _run("data_sample_rows", folder_id, limit=limit, table_name=table_name)


@mcp.tool(title="Search a column for a value", annotations=_READ_ONLY)
def data_search(
    folder_id: FolderId,
    table_name: TableName,
    column: Annotated[str, Field(description="Column to search.")],
    value: Annotated[str, Field(description="Substring to match (case-insensitive).")],
    limit: Annotated[int | None, Field(description="Max rows (default 20, max 20).")] = None,
) -> dict[str, Any]:
    """Find rows where a column contains a value, returning a small capped result."""
    return _run("data_search", folder_id, column=column, value=value, limit=limit, table_name=table_name)


@mcp.tool(title="Run a read-only SELECT query", annotations=_READ_ONLY)
def data_run_query(
    folder_id: FolderId,
    sql: Annotated[str, Field(description="A single SELECT statement referencing only this folder's tables.")],
    limit: Annotated[int | None, Field(description="Max rows to return.")] = None,
) -> dict[str, Any]:
    """Run one folder-scoped, read-only SELECT and return capped rows.

    Prefer data_aggregate / data_column_stats for summaries. Mutating SQL,
    multiple statements, system catalogs, and schema-qualified names are rejected.
    """
    return _run("data_run_query", folder_id, sql=sql, limit=limit)


@mcp.tool(title="Profile null values in a table", annotations=_READ_ONLY)
def data_profile_nulls(folder_id: FolderId, table_name: TableName) -> dict[str, Any]:
    """Count NULL values per column (first 15 columns) for a quick data-quality check."""
    return _run("data_profile_nulls", folder_id, table_name=table_name)


_MANUAL_TOOLS = {
    "data_list_tables",
    "data_describe_tables",
    "data_row_count",
    "data_aggregate",
    "data_column_stats",
    "data_sample_rows",
    "data_search",
    "data_run_query",
    "data_profile_nulls",
}


def _python_annotation(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "integer":
        return int
    if kind == "number":
        return float
    if kind == "boolean":
        return bool
    if kind == "array":
        return list[str]
    if kind == "object":
        return dict[str, Any]
    return str


def _register_registry_tool(spec: Any) -> None:
    properties = dict(spec.parameters.get("properties") or {})
    required = set(spec.parameters.get("required") or [])

    def dispatch(**arguments: Any) -> dict[str, Any]:
        folder_id = str(arguments.pop("folder_id", "") or "")
        return _run(spec.name, folder_id, **arguments)

    dispatch.__name__ = spec.name
    dispatch.__doc__ = spec.description
    ordered = [key for key in properties if key in required] + [key for key in properties if key not in required]
    parameters = []
    annotations: dict[str, Any] = {}
    for key in ordered:
        annotation = _python_annotation(properties[key])
        annotations[key] = annotation
        parameters.append(
            inspect.Parameter(
                key,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if key in required else None,
                annotation=annotation,
            )
        )
    dispatch.__annotations__ = {**annotations, "return": dict[str, Any]}
    dispatch.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])
    mcp.tool(
        name=spec.name,
        title=spec.title,
        description=spec.description,
        annotations=spec.annotations,
        structured_output=True,
    )(dispatch)


for _spec in DATA_TOOLS:
    if _spec.name not in _MANUAL_TOOLS:
        _register_registry_tool(_spec)

def main() -> None:
    """Entry point. Honors MCP_TRANSPORT (stdio default, 'http' for remote)."""
    if not DatabaseConfig.from_env().configured:
        print(
            "[eventhorizon-data-mcp] WARNING: Postgres env not fully configured "
            "(need POSTGRES_HOST, POSTGRES_USER, POSTGRES_DBNAME).",
            file=sys.stderr,
        )
    if os.getenv("MCP_TRANSPORT", "stdio").lower() == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
