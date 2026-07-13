from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

from security.access import audit_tool_call, require_folder_access

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.workspace_store import (
    ensure_workspace_schema,
    record_transform_with_cursor,
    validate_session_context,
)

VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
SELECT_PATTERN = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
MUTATING_PATTERN = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do)\b", re.IGNORECASE)
TABLE_REFERENCE_PATTERN = re.compile(r"\b(?:from|join)\s+(?!\()((?:\"[^\"]+\")|[a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
QUALIFIED_REFERENCE_PATTERN = re.compile(r"\b(?:from|join)\s+((?:\"[^\"]+\")|[a-zA-Z_][a-zA-Z0-9_]*)\s*\.", re.IGNORECASE)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str | None
    port: str
    user: str | None
    password: str | None
    database: str | None
    upload_schema: str
    folder_schema_prefix: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DBNAME"),
            upload_schema=os.getenv("POSTGRES_UPLOAD_SCHEMA", "uploads"),
            folder_schema_prefix=os.getenv("AGENT_FOLDER_SCHEMA_PREFIX", "folder"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.database)


def get_folder_status(folder_id: str | None, user_id: str | None = None) -> dict[str, Any]:
    if not folder_id:
        return {"has_data": False, "tables": [], "reason": "missing_folder_id"}
    result = describe_tables(folder_id, user_id=user_id)
    tables = result.get("tables", []) if isinstance(result, dict) else []
    return {"has_data": len(tables) > 0, "tables": [t.get("name") for t in tables], "table_count": len(tables)}


def describe_tables(folder_id: str | None, user_id: str | None = None) -> dict[str, Any]:
    cfg = DatabaseConfig.from_env()
    if not cfg.configured:
        return {"tables": [], "warning": "Postgres environment is not configured."}
    if not folder_id:
        return {"tables": [], "warning": "No folder_id provided."}
    require_folder_access(folder_id, user_id, min_level="VIEWER")
    audit_tool_call(user_id, folder_id, "describe_tables")

    mapping = _get_table_mapping(cfg, folder_id)
    if not mapping:
        return {"tables": []}

    tables = []
    with _connect(cfg) as conn:
        _sync_folder_views(conn, cfg, folder_id, mapping)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for friendly, physical in sorted(mapping.items()):
                columns = _get_columns(cur, cfg.upload_schema, physical)
                sample = _get_sample(cur, cfg.upload_schema, physical)
                estimate = _get_estimated_rows(cur, physical)
                tables.append({
                    "name": friendly,
                    "columns": columns,
                    "estimated_row_count": estimate,
                    "sample_values": sample,
                })
    return {"tables": tables}


def execute_select(folder_id: str | None, query: str, user_id: str | None = None, max_rows: int | None = None) -> dict[str, Any]:
    cfg = DatabaseConfig.from_env()
    if not cfg.configured:
        return {"error": "Postgres environment is not configured.", "rows": []}
    if not folder_id:
        return {"error": "No folder_id provided.", "rows": []}
    require_folder_access(folder_id, user_id, min_level="VIEWER")
    audit_tool_call(user_id, folder_id, "execute_select")

    mapping = _get_table_mapping(cfg, folder_id)
    validation = _validate_select(query, set(mapping.keys()))
    if validation:
        return {"error": validation, "rows": []}

    row_limit = int(max_rows) if max_rows is not None else int(os.getenv("AGENT_SQL_ROW_LIMIT", "30"))
    row_limit = max(1, min(row_limit, int(os.getenv("AGENT_SQL_ROW_HARD_CAP", "500"))))

    with _connect(cfg) as conn:
        _sync_folder_views(conn, cfg, folder_id, mapping)
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            folder_schema = _folder_schema(cfg, folder_id)
            cur.execute(f"SET LOCAL search_path TO {_quote_identifier(folder_schema)}, {_quote_identifier(cfg.upload_schema)}")
            cur.execute("SET LOCAL statement_timeout = %s", (int(os.getenv("AGENT_SQL_TIMEOUT_MS", "30000")),))
            try:
                cur.execute(query)
                rows = cur.fetchmany(row_limit)
                conn.commit()
                return {"rows": [_jsonable(dict(row)) for row in rows], "row_count": len(rows), "truncated": cur.rowcount > len(rows)}
            except Exception as exc:
                conn.rollback()
                return {"error": str(exc), "rows": []}


def resolve_table_name(folder_id: str | None, table_name: str, user_id: str | None = None) -> str | None:
    """Resolve a user-supplied table name to its folder-scoped friendly name.

    Accepts either the friendly name or a case-insensitive match, and returns the
    canonical friendly name safe to embed in a folder-scoped query, or ``None``
    when the table does not belong to the folder.
    """
    cfg = DatabaseConfig.from_env()
    if not cfg.configured or not folder_id or not table_name:
        return None
    require_folder_access(folder_id, user_id, min_level="VIEWER")
    mapping = _get_table_mapping(cfg, folder_id)
    lowered = str(table_name).strip().lower()
    for friendly in mapping:
        if friendly.lower() == lowered:
            return friendly
    return None


def estimated_row_count(folder_id: str | None, table_name: str, user_id: str | None = None) -> dict[str, Any]:
    """Return a fast, scan-free row-count estimate from ``pg_class.reltuples``.

    Designed for very large tables (millions of rows) where an exact ``COUNT(*)``
    would be slow: the planner statistic is returned instantly. Falls back to the
    physical table lookup and never touches user-controlled SQL.
    """
    cfg = DatabaseConfig.from_env()
    if not cfg.configured:
        return {"error": "Postgres environment is not configured."}
    friendly = resolve_table_name(folder_id, table_name, user_id=user_id)
    if not friendly:
        return {"error": f"Table '{table_name}' not found in this folder."}
    audit_tool_call(user_id, folder_id, "estimated_row_count")
    mapping = _get_table_mapping(cfg, folder_id)
    physical = mapping.get(friendly)
    if not physical:
        return {"error": f"Table '{table_name}' not found in this folder."}
    with _connect(cfg) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT reltuples::bigint AS rows FROM pg_class WHERE relname = %s", (physical,))
            row = cur.fetchone()
    estimate = int(row["rows"]) if row and row.get("rows") is not None else -1
    return {"table": friendly, "estimated_row_count": estimate, "exact": False}


def _validate_select(query: str, allowed_tables: set[str] | None = None) -> str | None:
    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        return "Multiple SQL statements are not allowed."
    if not SELECT_PATTERN.match(stripped):
        return "Only direct SELECT queries are allowed in the general analyst tool."
    if MUTATING_PATTERN.search(stripped):
        return "Mutating SQL is blocked in the analyst tool."
    forbidden = ["information_schema", "pg_catalog", "pg_", "current_setting"]
    lowered = stripped.lower()
    if any(token in lowered for token in forbidden):
        return "System catalog access is blocked. Use describe_tables for schema discovery."
    if QUALIFIED_REFERENCE_PATTERN.search(stripped):
        return "Schema-qualified table references are blocked. Use the folder-scoped table names returned by describe_tables."
    if allowed_tables is not None:
        allowed = {table.lower() for table in allowed_tables}
        references = {_unquote_identifier(match.group(1)).lower() for match in TABLE_REFERENCE_PATTERN.finditer(stripped)}
        outside_scope = sorted(ref for ref in references if ref not in allowed)
        if outside_scope:
            return f"Query references tables outside the selected folder scope: {', '.join(outside_scope[:5])}."
    return None

def _get_table_mapping(cfg: DatabaseConfig, folder_id: str) -> dict[str, str]:
    normalized = _normalize_folder_id(folder_id)
    mapping: dict[str, str] = {}
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT LOWER(REPLACE(t.id::text, '-', '')) AS table_uuid,
                       COALESCE(NULLIF(LOWER(t.name), ''), LOWER(f.name), LOWER(f.original_name)) AS friendly
                FROM instance01.mtd_table t
                JOIN instance01.mtd_file f ON t.parent_id = f.id
                WHERE LOWER(REPLACE(f.parent_folder_id::text, '-', '')) = %s
                  AND t.status = 'ACTIVE'
                """,
                (normalized,),
            )
            for physical, friendly in cur.fetchall():
                friendly_name = _sanitize_identifier(friendly or physical)
                if friendly_name and physical:
                    mapping[friendly_name] = physical

            try:
                cur.execute(
                    """
                    SELECT table_name, COALESCE(friendly_name, table_name) AS friendly
                    FROM uploads.table_registry
                    WHERE REPLACE(LOWER(folder_id), '-', '') = %s
                      AND COALESCE((metadata->>'active')::boolean, TRUE)
                    """,
                    (normalized,),
                )
                for physical, friendly in cur.fetchall():
                    friendly_name = _sanitize_identifier(friendly or physical)
                    if friendly_name and physical:
                        mapping[friendly_name] = physical
            except Exception:
                conn.rollback()
    return mapping


def _sync_folder_views(conn, cfg: DatabaseConfig, folder_id: str, mapping: dict[str, str]) -> None:
    folder_schema = _folder_schema(cfg, folder_id)
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote_identifier(folder_schema)}")
        for friendly, physical in mapping.items():
            if not VALID_IDENTIFIER.match(friendly):
                continue
            cur.execute(
                "CREATE OR REPLACE VIEW "
                f"{_quote_identifier(folder_schema)}.{_quote_identifier(friendly)} AS "
                f"SELECT * FROM {_quote_identifier(cfg.upload_schema)}.{_quote_identifier(physical)}"
            )
        conn.commit()


def _get_columns(cur, schema: str, physical: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, physical),
    )
    return [{"name": row["column_name"], "type": row["data_type"], "nullable": row["is_nullable"]} for row in cur.fetchall()]


def _get_sample(cur, schema: str, physical: str) -> list[dict[str, Any]]:
    try:
        cur.execute(f"SELECT * FROM {_quote_identifier(schema)}.{_quote_identifier(physical)} LIMIT 3")
        return [_jsonable(dict(row)) for row in cur.fetchall()]
    except Exception:
        return []


def _get_estimated_rows(cur, physical: str) -> int:
    try:
        cur.execute("SELECT reltuples::bigint AS rows FROM pg_class WHERE relname = %s", (physical,))
        row = cur.fetchone()
        return int(row["rows"]) if row else -1
    except Exception:
        return -1


@contextmanager
def _connect(cfg: DatabaseConfig) -> Iterator[Any]:
    conn = psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        dbname=cfg.database,
    )
    try:
        yield conn
    finally:
        conn.close()


def _folder_schema(cfg: DatabaseConfig, folder_id: str) -> str:
    return f"{cfg.folder_schema_prefix}_{_normalize_folder_id(folder_id)}"


def _normalize_folder_id(folder_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]", "", folder_id.replace("-", "").lower())
    return normalized or "default"


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _unquote_identifier(value: str) -> str:
    value = str(value).strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def _sanitize_identifier(value: str) -> str:
    if not value:
        return ""
    base = os.path.splitext(str(value))[0].lower()
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", base).strip("_")
    if not base or base[0].isdigit():
        base = f"table_{base}"
    return base


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def validate_transform_select(folder_id: str | None, select_sql: str, user_id: str | None = None) -> str | None:
    """Validate a prospective CTAS SELECT against this folder's table map."""
    if not folder_id:
        return "No folder_id provided."
    require_folder_access(folder_id, user_id, min_level="ANALYST")
    cfg = DatabaseConfig.from_env()
    if not cfg.configured:
        return "Postgres environment is not configured."
    mapping = _get_table_mapping(cfg, folder_id)
    if not mapping:
        return "No source tables are available in this folder."
    return _validate_select(select_sql, set(mapping.keys()))


def create_transform_table(
    *,
    folder_id: str | None,
    user_id: str | None,
    session_id: str | None,
    select_sql: str,
    friendly_name: str = "prepared_data",
    source_tables: list[str] | None = None,
    recipe: list[str] | None = None,
) -> dict[str, Any]:
    """Create and register one active prepared-table revision transactionally."""
    if not folder_id or not user_id or not session_id:
        return {"error": "folder_id, user_id, and session_id are required."}
    require_folder_access(folder_id, user_id, min_level="ANALYST")
    validate_session_context(session_id, folder_id, user_id, min_level="ANALYST")
    ensure_workspace_schema()

    cfg = DatabaseConfig.from_env()
    if not cfg.configured:
        return {"error": "Postgres environment is not configured."}
    mapping = _get_table_mapping(cfg, folder_id)
    validation = _validate_select(select_sql, set(mapping.keys()))
    if validation:
        return {"error": validation}

    referenced = {
        _unquote_identifier(match.group(1)).lower()
        for match in TABLE_REFERENCE_PATTERN.finditer(select_sql)
    }
    declared_sources = [str(value) for value in (source_tables or []) if str(value).strip()]
    invalid_declared = [name for name in declared_sources if name.lower() not in {key.lower() for key in mapping}]
    if invalid_declared:
        return {"error": f"Source table(s) are outside this folder: {', '.join(invalid_declared)}."}

    table_id = str(uuid.uuid4())
    session_suffix = _normalize_folder_id(session_id)[:8]
    base_name = _sanitize_identifier(friendly_name or "prepared_data")[:38]
    friendly = f"{base_name}_{session_suffix}"[:55]

    with _connect(cfg) as conn:
        try:
            _sync_folder_views(conn, cfg, folder_id, mapping)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT COALESCE(transform_revision, 0) AS revision FROM instance01.mtd_session_workspace WHERE session_id = %s::uuid",
                    (session_id,),
                )
                revision_row = cur.fetchone()
                revision = int((revision_row or {}).get("revision") or 0) + 1
                physical = f"eh_{_normalize_folder_id(folder_id)[:10]}_{session_suffix}_r{revision}_{uuid.uuid4().hex[:6]}"[:63]

                cur.execute("SET LOCAL statement_timeout = %s", (int(os.getenv("AGENT_SQL_TIMEOUT_MS", "30000")),))
                folder_schema = _folder_schema(cfg, folder_id)
                cur.execute(f"SET LOCAL search_path TO {_quote_identifier(folder_schema)}, {_quote_identifier(cfg.upload_schema)}")
                cur.execute(
                    f"CREATE TABLE {_quote_identifier(cfg.upload_schema)}.{_quote_identifier(physical)} AS {select_sql.strip().rstrip(';')}"
                )
                cur.execute(
                    f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(cfg.upload_schema)}.{_quote_identifier(physical)}"
                )
                row_count = int((cur.fetchone() or {}).get("row_count") or 0)
                columns = _get_columns(cur, cfg.upload_schema, physical)
                if not columns:
                    raise RuntimeError("The prepared table has no columns.")

                created_at = datetime.now(timezone.utc).isoformat()
                metadata = {
                    "table_id": table_id,
                    "active": True,
                    "revision": revision,
                    "row_count": row_count,
                    "columns": columns,
                    "source_tables": declared_sources or sorted(referenced),
                    "recipe": recipe or [],
                    "created_at": created_at,
                }
                cur.execute(
                    """
                    UPDATE uploads.table_registry
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE table_type = 'agent_created'
                      AND REPLACE(LOWER(COALESCE(folder_id, '')), '-', '') = %s
                      AND COALESCE(session_id, '') = %s
                      AND COALESCE((metadata->>'active')::boolean, TRUE)
                    """,
                    (
                        psycopg2.extras.Json({"active": False, "superseded_at": created_at}),
                        _normalize_folder_id(folder_id),
                        session_id,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO uploads.table_registry(
                        table_name, table_type, session_id, folder_id, created_at,
                        created_by, is_protected, metadata, friendly_name
                    ) VALUES (%s, 'agent_created', %s, %s, NOW(), %s, TRUE, %s::jsonb, %s)
                    """,
                    (
                        physical,
                        session_id,
                        folder_id,
                        user_id,
                        psycopg2.extras.Json(metadata),
                        friendly,
                    ),
                )
                cur.execute(
                    f"CREATE OR REPLACE VIEW {_quote_identifier(folder_schema)}.{_quote_identifier(friendly)} AS "
                    f"SELECT * FROM {_quote_identifier(cfg.upload_schema)}.{_quote_identifier(physical)}"
                )
                artifact = {
                    "id": table_id,
                    "artifact_type": "transform_table",
                    "type": "transform_table",
                    "name": friendly,
                    "table_id": table_id,
                    "table_name": friendly,
                    "source": "agent_created",
                    "revision": revision,
                    "transform_revision": revision,
                    "row_count": row_count,
                    "columns": columns,
                    "source_tables": metadata["source_tables"],
                    "recipe": metadata["recipe"],
                    "status": "ready",
                    "created_at": created_at,
                }
                record_transform_with_cursor(
                    cur,
                    session_id=session_id,
                    folder_id=folder_id,
                    artifact=artifact,
                )
            conn.commit()
            audit_tool_call(user_id, folder_id, "create_transform_table")
            return {"artifact": artifact, "validation": {"passed": True, "column_count": len(columns), "row_count": row_count}}
        except Exception as exc:
            conn.rollback()
            return {"error": f"Prepared table creation failed: {exc}"}