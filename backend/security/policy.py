from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text

logger = logging.getLogger(__name__)

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


def normalize_access_level(level: Any) -> str:
    value = str(level or "NONE").strip().upper()
    if value == "":  # defensive, keeps ordering comparisons simple
        return "NONE"
    return value


def current_user_id(user: dict[str, Any] | None) -> str:
    user_id = str((user or {}).get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authenticated user is missing.")
    return user_id


def require_same_user_or_admin(target_user_id: Any, user: dict[str, Any] | None, db: Any) -> str:
    target = str(target_user_id)
    caller = current_user_id(user)
    if _same_id(target, caller):
        return target
    require_admin(user, db)
    return target


def require_admin(user: dict[str, Any] | None, db: Any) -> str:
    caller = current_user_id(user)
    role = _role_for_user(caller, db)
    if normalize_access_level(role) != "ADMIN":
        _deny("admin_required", caller)
    return caller


def require_project_access(
    project_id: Any,
    user: dict[str, Any] | None,
    db: Any,
    min_level: str = "VIEWER",
) -> str:
    caller = current_user_id(user)
    if _is_admin(caller, db):
        return "ADMIN"

    level = db.execute(
        text(
            """
            SELECT level
            FROM instance01.mtd_access
            WHERE entity_id = CAST(:entity_id AS uuid)
              AND entity_type = 'PROJECT'
              AND user_id = :user_id
              AND COALESCE(level, 'NONE') != 'NONE'
              AND (expiration_date IS NULL OR expiration_date > NOW())
            LIMIT 1
            """
        ),
        {"entity_id": str(project_id), "user_id": caller},
    ).scalar()
    _require_level(level, min_level, caller, "project", str(project_id))
    return normalize_access_level(level)


def require_folder_access(
    folder_id: Any,
    user: dict[str, Any] | None,
    db: Any,
    min_level: str = "VIEWER",
) -> str:
    caller = current_user_id(user)
    if _is_admin(caller, db):
        return "ADMIN"

    level = db.execute(
        text(
            """
            SELECT level
            FROM instance01.mtd_access
            WHERE entity_id = CAST(:entity_id AS uuid)
              AND entity_type = 'FOLDER'
              AND user_id = :user_id
              AND COALESCE(level, 'NONE') != 'NONE'
              AND (expiration_date IS NULL OR expiration_date > NOW())
            LIMIT 1
            """
        ),
        {"entity_id": str(folder_id), "user_id": caller},
    ).scalar()
    _require_level(level, min_level, caller, "folder", str(folder_id))
    return normalize_access_level(level)


def require_session_owner_or_folder_access(
    session_id: Any,
    user: dict[str, Any] | None,
    db: Any,
    min_level: str = "VIEWER",
) -> Any:
    caller = current_user_id(user)
    row = db.execute(
        text(
            """
            SELECT created_by, folder_id
            FROM instance01.mtd_session
            WHERE id = CAST(:session_id AS uuid)
              AND COALESCE(status, 'ACTIVE') != 'DELETED'
            LIMIT 1
            """
        ),
        {"session_id": str(session_id)},
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")

    created_by = _row_value(row, "created_by", 0)
    folder_id = _row_value(row, "folder_id", 1)
    if created_by is not None and _same_id(str(created_by), caller):
        return row

    require_folder_access(folder_id, user, db, min_level=min_level)
    return row


def require_table_access(
    table_id_or_name: Any,
    folder_id: Any,
    user: dict[str, Any] | None,
    db: Any,
    min_level: str = "VIEWER",
) -> Any:
    table_ref = str(table_id_or_name)
    row = db.execute(
        text(
            """
            SELECT f.parent_folder_id
            FROM instance01.mtd_table t
            JOIN instance01.mtd_file f ON t.parent_id = f.id
            WHERE (t.id::text = :table_ref OR LOWER(REPLACE(t.id::text, '-', '')) = LOWER(REPLACE(:table_ref, '-', '')) OR t.name = :table_ref)
              AND COALESCE(t.status, 'ACTIVE') != 'DELETED'
              AND COALESCE(f.status, 'ACTIVE') != 'DELETED'
            LIMIT 1
            """
        ),
        {"table_ref": table_ref},
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found.")

    parent_folder_id = _row_value(row, "parent_folder_id", 0)
    if folder_id and not _same_id(str(parent_folder_id), str(folder_id)):
        _deny("table_folder_mismatch", current_user_id(user), folder_id=str(folder_id), table=table_ref)

    require_folder_access(parent_folder_id, user, db, min_level=min_level)
    return row


def user_from_request(request: Any) -> dict[str, Any]:
    user = getattr(getattr(request, "state", None), "user", None)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    return user


def _role_for_user(user_id: str, db: Any) -> str:
    row = db.execute(
        text("SELECT role FROM instance01.mtd_users WHERE id = :user_id"),
        {"user_id": user_id},
    ).fetchone()
    role = _row_value(row, "role", 0) if row is not None else None
    return normalize_access_level(role)


def _is_admin(user_id: str, db: Any) -> bool:
    return _role_for_user(user_id, db) == "ADMIN"


def _require_level(level: Any, min_level: str, user_id: str, entity_type: str, entity_id: str) -> None:
    actual = ACCESS_ORDER.get(normalize_access_level(level), 0)
    required = ACCESS_ORDER.get(normalize_access_level(min_level), 0)
    if actual < required:
        _deny("insufficient_access", user_id, entity_type=entity_type, entity_id=entity_id, level=normalize_access_level(level), min_level=min_level)


def _deny(reason: str, user_id: str, **context: Any) -> None:
    logger.warning("access_denied reason=%s user_id=%s context=%s", reason, user_id, context)
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied.")


def _same_id(left: str, right: str) -> bool:
    return _normalize_id(left) == _normalize_id(right)


def _normalize_id(value: str) -> str:
    return str(value or "").strip().replace("-", "").lower()


def _row_value(row: Any, name: str, index: int) -> Any:
    if row is None:
        return None
    if hasattr(row, name):
        return getattr(row, name)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and name in mapping:
        return mapping[name]
    if isinstance(row, dict):
        return row.get(name)
    try:
        return row[index]
    except Exception:
        return None
