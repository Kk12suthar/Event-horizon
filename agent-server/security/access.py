from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras
from fastapi import HTTPException, status

logger = logging.getLogger("eventhorizon.agent_server.access")

ACCESS_ORDER = {
    "NONE": 0,
    "NO_ACCESS": 0,
    "VIEW": 1,
    "VIEWER": 1,
    "READ": 1,
    "ANALYST": 2,
    "WRITE": 2,
    "EDITOR": 2,
    "ADMIN": 3,
    "OWNER": 4,
}


def require_admin(user_id: str) -> None:
    if _normalize_level(_user_role(user_id)) != "ADMIN":
        _deny(user_id, "admin_required")


def require_folder_access(folder_id: str | None, user_id: str | None, min_level: str = "VIEWER") -> str:
    if not folder_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "folder_id is required.")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authenticated user is required.")
    if _normalize_level(_user_role(user_id)) == "ADMIN":
        return "ADMIN"

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT level
                FROM instance01.mtd_access
                WHERE entity_id = %s::uuid
                  AND entity_type = 'FOLDER'
                  AND user_id = %s
                  AND COALESCE(level, 'NONE') != 'NONE'
                  AND (expiration_date IS NULL OR expiration_date > NOW())
                LIMIT 1
                """,
                (str(folder_id), str(user_id)),
            )
            row = cur.fetchone()

    level = _row_value(row, "level", 0) if row else None
    if ACCESS_ORDER.get(_normalize_level(level), 0) < ACCESS_ORDER.get(_normalize_level(min_level), 0):
        _deny(str(user_id), "folder_access_denied", folder_id=str(folder_id), level=level, min_level=min_level)
    return _normalize_level(level)


def project_id_for_folder(folder_id: str | None) -> str:
    """Return the canonical project for a folder; never trust a model/client value."""
    if not folder_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "folder_id is required.")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT project_id::text FROM instance01.mtd_folder WHERE id = %s::uuid LIMIT 1",
                (str(folder_id),),
            )
            row = cur.fetchone()
    project_id = _row_value(row, "project_id", 0) if row else None
    if not project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found.")
    return str(project_id)


def audit_tool_call(user_id: str | None, folder_id: str | None, tool_name: str) -> None:
    logger.info("agent_tool_call user_id=%s folder_id=%s tool=%s", user_id, folder_id, tool_name)


def _user_role(user_id: str) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM instance01.mtd_users WHERE id = %s", (str(user_id),))
            row = cur.fetchone()
    return _normalize_level(_row_value(row, "role", 0) if row else None)



def _row_value(row: Any, key: str, index: int) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, key):
        return getattr(row, key)
    try:
        return row[index]
    except Exception:
        return None
def _deny(user_id: str, reason: str, **context: Any) -> None:
    logger.warning("access_denied user_id=%s reason=%s context=%s", user_id, reason, context)
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied.")


def _normalize_level(level: Any) -> str:
    return str(level or "NONE").strip().upper() or "NONE"


@contextmanager
def _connect() -> Iterator[Any]:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DBNAME") or os.getenv("POSTGRES_UPLOAD_DBNAME"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()

