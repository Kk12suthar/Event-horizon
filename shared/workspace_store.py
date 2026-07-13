from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import psycopg2
import psycopg2.extras


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

ARTIFACT_TYPES = {"transform_table", "chart", "report", "report_draft"}


class WorkspaceStoreError(RuntimeError):
    def __init__(self, message: str, *, code: str = "workspace_error", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def ensure_workspace_schema() -> None:
    """Create the session workspace tables used by both running services."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instance01.mtd_session_workspace (
                    session_id uuid PRIMARY KEY
                        REFERENCES instance01.mtd_session(id) ON DELETE CASCADE,
                    folder_id uuid NOT NULL
                        REFERENCES instance01.mtd_folder(id) ON DELETE CASCADE,
                    selected_table_id text,
                    selected_table_name text,
                    transform_revision integer NOT NULL DEFAULT 0,
                    transform_status varchar(32) NOT NULL DEFAULT 'EMPTY',
                    created_at timestamptz NOT NULL DEFAULT NOW(),
                    updated_at timestamptz NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instance01.mtd_session_artifact (
                    id uuid PRIMARY KEY,
                    session_id uuid NOT NULL
                        REFERENCES instance01.mtd_session(id) ON DELETE CASCADE,
                    folder_id uuid NOT NULL
                        REFERENCES instance01.mtd_folder(id) ON DELETE CASCADE,
                    artifact_type varchar(32) NOT NULL,
                    status varchar(32) NOT NULL DEFAULT 'ready',
                    name text NOT NULL,
                    source_table_id text,
                    transform_revision integer NOT NULL DEFAULT 0,
                    format varchar(16),
                    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                    storage_path text,
                    created_at timestamptz NOT NULL DEFAULT NOW(),
                    updated_at timestamptz NOT NULL DEFAULT NOW(),
                    CONSTRAINT mtd_session_artifact_type_check
                        CHECK (artifact_type IN ('transform_table', 'chart', 'report', 'report_draft'))
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_artifact_session_type
                ON instance01.mtd_session_artifact(session_id, artifact_type, created_at)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_workspace_folder
                ON instance01.mtd_session_workspace(folder_id)
                """
            )
        conn.commit()


def validate_session_context(
    session_id: str | None,
    folder_id: str | None,
    user_id: str | None,
    *,
    min_level: str = "VIEWER",
) -> dict[str, Any]:
    if not session_id:
        raise WorkspaceStoreError("An active session is required.", code="missing_session", status_code=400)
    if not folder_id:
        raise WorkspaceStoreError("A folder is required.", code="missing_folder", status_code=400)
    if not user_id:
        raise WorkspaceStoreError("An authenticated user is required.", code="missing_user", status_code=401)

    try:
        session_uuid = str(uuid.UUID(str(session_id)))
        folder_uuid = str(uuid.UUID(str(folder_id)))
    except ValueError as exc:
        raise WorkspaceStoreError("The session or folder identifier is invalid.", code="invalid_context", status_code=400) from exc

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, folder_id::text, created_by, status, created_at, app_name
                FROM instance01.mtd_session
                WHERE id = %s::uuid
                LIMIT 1
                """,
                (session_uuid,),
            )
            row = cur.fetchone()
            if not row:
                raise WorkspaceStoreError("Session not found.", code="session_not_found", status_code=404)
            if _normalize_id(row["folder_id"]) != _normalize_id(folder_uuid):
                raise WorkspaceStoreError("The session does not belong to this folder.", code="session_folder_mismatch", status_code=403)
            if str(row.get("status") or "").upper() not in {"ACTIVE", "INITIALIZING"}:
                raise WorkspaceStoreError("The session is no longer active.", code="inactive_session", status_code=409)
            if not _can_access_folder(cur, folder_uuid, str(user_id), str(row.get("created_by") or ""), min_level):
                raise WorkspaceStoreError("Access denied.", code="session_access_denied", status_code=403)
            return _jsonable(dict(row))


def get_workspace_snapshot(session_id: str, folder_id: str, user_id: str) -> dict[str, Any]:
    validate_session_context(session_id, folder_id, user_id)
    ensure_workspace_schema()
    transforms = list_transform_tables(folder_id)

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO instance01.mtd_session_workspace(session_id, folder_id)
                VALUES (%s::uuid, %s::uuid)
                ON CONFLICT (session_id) DO NOTHING
                """,
                (session_id, folder_id),
            )
            cur.execute(
                """
                SELECT session_id::text, folder_id::text, selected_table_id,
                       selected_table_name, transform_revision, transform_status,
                       created_at, updated_at
                FROM instance01.mtd_session_workspace
                WHERE session_id = %s::uuid
                """,
                (session_id,),
            )
            workspace = dict(cur.fetchone() or {})

            selected = _match_transform(transforms, workspace.get("selected_table_id"))
            if selected is None and transforms:
                selected = transforms[0]
                cur.execute(
                    """
                    UPDATE instance01.mtd_session_workspace
                    SET selected_table_id = %s,
                        selected_table_name = %s,
                        transform_revision = %s,
                        transform_status = 'READY',
                        updated_at = NOW()
                    WHERE session_id = %s::uuid
                    """,
                    (selected["id"], selected["name"], selected["revision"], session_id),
                )
                workspace.update(
                    selected_table_id=selected["id"],
                    selected_table_name=selected["name"],
                    transform_revision=selected["revision"],
                    transform_status="READY",
                )

            cur.execute(
                """
                SELECT id::text, artifact_type, status, name, source_table_id,
                       transform_revision, format, payload, created_at, updated_at
                FROM instance01.mtd_session_artifact
                WHERE session_id = %s::uuid
                ORDER BY created_at ASC
                """,
                (session_id,),
            )
            artifacts = [_artifact_from_row(dict(row)) for row in cur.fetchall()]
        conn.commit()

    current_revision = int(workspace.get("transform_revision") or 0)
    current_table_id = workspace.get("selected_table_id")
    for artifact in artifacts:
        if artifact.get("artifact_type") in {"chart", "report", "report_draft"}:
            artifact["stale"] = bool(
                artifact.get("source_table_id") != current_table_id
                or int(artifact.get("transform_revision") or 0) != current_revision
            )

    return {
        "session_id": str(session_id),
        "folder_id": str(folder_id),
        "workspace": _jsonable(workspace),
        "selected_table": selected,
        "transform_tables": transforms,
        "charts": [a for a in artifacts if a.get("artifact_type") == "chart"],
        "reports": [a for a in artifacts if a.get("artifact_type") == "report"],
        "report_drafts": [a for a in artifacts if a.get("artifact_type") == "report_draft"],
    }


def list_transform_tables(folder_id: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    normalized = _normalize_id(folder_id)
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_name, COALESCE(NULLIF(friendly_name, ''), table_name) AS friendly_name,
                       session_id, folder_id, created_at, created_by, metadata
                FROM uploads.table_registry
                WHERE table_type = 'agent_created'
                  AND REPLACE(LOWER(COALESCE(folder_id, '')), '-', '') = %s
                ORDER BY created_at DESC NULLS LAST, table_name DESC
                """,
                (normalized,),
            )
            rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        active = metadata.get("active", True) is not False
        if not include_inactive and not active:
            continue
        table_id = str(metadata.get("table_id") or _stable_table_id(folder_id, row["table_name"]))
        result.append(
            {
                "id": table_id,
                "name": str(row.get("friendly_name") or row["table_name"]),
                "source": "agent_created",
                "revision": int(metadata.get("revision") or 0),
                "row_count": int(metadata.get("row_count") or 0),
                "columns": list(metadata.get("columns") or []),
                "source_tables": list(metadata.get("source_tables") or []),
                "recipe": list(metadata.get("recipe") or []),
                "active": active,
                "session_id": str(row.get("session_id") or ""),
                "created_at": _iso(row.get("created_at")),
            }
        )
    return result


def resolve_transform_table(folder_id: str, table_id_or_name: str | None) -> dict[str, Any] | None:
    transforms = list_transform_tables(folder_id)
    if not table_id_or_name:
        return transforms[0] if len(transforms) == 1 else None
    return _match_transform(transforms, table_id_or_name)


def resolve_transform_table_record(folder_id: str, table_id_or_name: str | None) -> dict[str, Any] | None:
    """Resolve a public transform ID/name to its authorized physical registry row."""
    public = resolve_transform_table(folder_id, table_id_or_name)
    if public is None:
        return None
    normalized = _normalize_id(folder_id)
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_name, COALESCE(NULLIF(friendly_name, ''), table_name) AS friendly_name,
                       session_id, folder_id, created_at, created_by, metadata
                FROM uploads.table_registry
                WHERE table_type = 'agent_created'
                  AND REPLACE(LOWER(COALESCE(folder_id, '')), '-', '') = %s
                """,
                (normalized,),
            )
            for row in cur.fetchall():
                metadata = dict(row.get("metadata") or {})
                candidate_id = str(metadata.get("table_id") or _stable_table_id(folder_id, row["table_name"]))
                if candidate_id == public["id"]:
                    return {**public, "physical_name": row["table_name"], "metadata": metadata}
    return None


def select_transform_table(session_id: str, folder_id: str, user_id: str, table_id: str) -> dict[str, Any]:
    validate_session_context(session_id, folder_id, user_id, min_level="ANALYST")
    ensure_workspace_schema()
    selected = resolve_transform_table(folder_id, table_id)
    if not selected:
        raise WorkspaceStoreError(
            "The selected prepared table does not exist in this folder.",
            code="transform_not_found",
            status_code=404,
        )
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO instance01.mtd_session_workspace(
                    session_id, folder_id, selected_table_id, selected_table_name,
                    transform_revision, transform_status, updated_at
                ) VALUES (%s::uuid, %s::uuid, %s, %s, %s, 'READY', NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    folder_id = EXCLUDED.folder_id,
                    selected_table_id = EXCLUDED.selected_table_id,
                    selected_table_name = EXCLUDED.selected_table_name,
                    transform_revision = EXCLUDED.transform_revision,
                    transform_status = 'READY',
                    updated_at = NOW()
                """,
                (session_id, folder_id, selected["id"], selected["name"], selected["revision"]),
            )
        conn.commit()
    return selected


def upsert_artifact(
    session_id: str,
    folder_id: str,
    user_id: str,
    artifact: dict[str, Any],
    *,
    storage_path: str | None = None,
) -> dict[str, Any]:
    validate_session_context(session_id, folder_id, user_id, min_level="ANALYST")
    ensure_workspace_schema()
    artifact_type = str(artifact.get("artifact_type") or artifact.get("type") or "").strip()
    if artifact_type not in ARTIFACT_TYPES:
        raise WorkspaceStoreError("Unsupported artifact type.", code="unsupported_artifact", status_code=400)

    artifact_id = _coerce_uuid(artifact.get("id"))
    source_table_id = artifact.get("source_table_id") or artifact.get("sourceTableId")
    revision = int(artifact.get("transform_revision") or artifact.get("transformRevision") or 0)
    name = str(artifact.get("name") or artifact.get("title") or artifact_type.replace("_", " ").title())
    status = str(artifact.get("status") or "ready").lower()
    file_format = artifact.get("format")
    payload = _jsonable(dict(artifact))
    payload["id"] = artifact_id
    payload["artifact_type"] = artifact_type

    if artifact_type == "chart":
        chart_type = str(payload.get("type") or "").lower()
        if chart_type not in {"line", "bar", "area", "pie", "radial", "kpi"}:
            raise WorkspaceStoreError("Unsupported chart type.", code="unsupported_chart", status_code=400)
        data = payload.get("data")
        if not isinstance(data, list) or not data or len(data) > 500:
            raise WorkspaceStoreError("A chart must contain between 1 and 500 data points.", code="invalid_chart_data", status_code=400)
        with _connect() as validation_conn:
            with validation_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as validation_cur:
                validation_cur.execute(
                    """
                    SELECT selected_table_id, transform_revision
                    FROM instance01.mtd_session_workspace
                    WHERE session_id = %s::uuid AND folder_id = %s::uuid
                    """,
                    (session_id, folder_id),
                )
                workspace = validation_cur.fetchone()
        if not workspace or not workspace.get("selected_table_id"):
            raise WorkspaceStoreError("Select a prepared table before saving a chart.", code="missing_transform", status_code=409)
        if str(source_table_id or "") != str(workspace["selected_table_id"]):
            raise WorkspaceStoreError("This chart belongs to a different prepared table.", code="chart_table_mismatch", status_code=409)
        if revision != int(workspace.get("transform_revision") or 0):
            raise WorkspaceStoreError("This chart was created from an older prepared-table revision.", code="stale_chart", status_code=409)
        status = "ready"
        payload["status"] = "ready"
        payload["source_table_id"] = str(source_table_id)
        payload["sourceTableId"] = str(source_table_id)
        payload["transform_revision"] = revision
        payload["transformRevision"] = revision
        payload["savedAt"] = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO instance01.mtd_session_artifact(
                    id, session_id, folder_id, artifact_type, status, name,
                    source_table_id, transform_revision, format, payload,
                    storage_path, created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s, %s, %s,
                    %s, %s, %s, %s::jsonb, %s, NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    name = EXCLUDED.name,
                    source_table_id = EXCLUDED.source_table_id,
                    transform_revision = EXCLUDED.transform_revision,
                    format = EXCLUDED.format,
                    payload = EXCLUDED.payload,
                    storage_path = COALESCE(EXCLUDED.storage_path, instance01.mtd_session_artifact.storage_path),
                    updated_at = NOW()
                WHERE instance01.mtd_session_artifact.session_id = EXCLUDED.session_id
                  AND instance01.mtd_session_artifact.folder_id = EXCLUDED.folder_id
                """,
                (
                    artifact_id,
                    session_id,
                    folder_id,
                    artifact_type,
                    status,
                    name,
                    source_table_id,
                    revision,
                    str(file_format).lower() if file_format else None,
                    psycopg2.extras.Json(payload),
                    storage_path,
                ),
            )
        conn.commit()
    return payload


def delete_artifact(session_id: str, folder_id: str, user_id: str, artifact_id: str) -> bool:
    validate_session_context(session_id, folder_id, user_id, min_level="ANALYST")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM instance01.mtd_session_artifact
                WHERE id = %s::uuid AND session_id = %s::uuid AND folder_id = %s::uuid
                """,
                (_coerce_uuid(artifact_id), session_id, folder_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def get_artifact(artifact_id: str, folder_id: str, user_id: str) -> dict[str, Any] | None:
    ensure_workspace_schema()
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id::text, a.session_id::text, a.folder_id::text,
                       a.artifact_type, a.status, a.name, a.source_table_id,
                       a.transform_revision, a.format, a.payload, a.storage_path,
                       a.created_at, a.updated_at
                FROM instance01.mtd_session_artifact a
                WHERE a.id = %s::uuid AND a.folder_id = %s::uuid
                LIMIT 1
                """,
                (_coerce_uuid(artifact_id), folder_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    validate_session_context(row["session_id"], folder_id, user_id, min_level="VIEWER")
    return {**_artifact_from_row(dict(row)), "storage_path": row.get("storage_path")}


def record_transform_with_cursor(
    cur: Any,
    *,
    session_id: str,
    folder_id: str,
    artifact: dict[str, Any],
) -> None:
    """Persist transform selection/artifact inside an existing CTAS transaction."""
    table_id = str(artifact["id"])
    table_name = str(artifact["name"])
    revision = int(artifact.get("revision") or 0)
    cur.execute(
        """
        INSERT INTO instance01.mtd_session_workspace(
            session_id, folder_id, selected_table_id, selected_table_name,
            transform_revision, transform_status, updated_at
        ) VALUES (%s::uuid, %s::uuid, %s, %s, %s, 'READY', NOW())
        ON CONFLICT (session_id) DO UPDATE SET
            folder_id = EXCLUDED.folder_id,
            selected_table_id = EXCLUDED.selected_table_id,
            selected_table_name = EXCLUDED.selected_table_name,
            transform_revision = EXCLUDED.transform_revision,
            transform_status = 'READY',
            updated_at = NOW()
        """,
        (session_id, folder_id, table_id, table_name, revision),
    )
    payload = {**artifact, "artifact_type": "transform_table", "type": "transform_table"}
    cur.execute(
        """
        INSERT INTO instance01.mtd_session_artifact(
            id, session_id, folder_id, artifact_type, status, name,
            source_table_id, transform_revision, payload, created_at, updated_at
        ) VALUES (%s::uuid, %s::uuid, %s::uuid, 'transform_table', 'ready', %s,
                  %s, %s, %s::jsonb, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
        """,
        (table_id, session_id, folder_id, table_name, table_id, revision, psycopg2.extras.Json(payload)),
    )


def _artifact_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload.update(
        id=str(row.get("id") or payload.get("id") or ""),
        session_id=str(row.get("session_id") or payload.get("session_id") or ""),
        folder_id=str(row.get("folder_id") or payload.get("folder_id") or ""),
        artifact_type=str(row.get("artifact_type") or payload.get("artifact_type") or ""),
        status=str(row.get("status") or payload.get("status") or "ready"),
        name=str(row.get("name") or payload.get("name") or payload.get("title") or "Artifact"),
        source_table_id=row.get("source_table_id") or payload.get("source_table_id") or payload.get("sourceTableId"),
        transform_revision=int(row.get("transform_revision") or payload.get("transform_revision") or payload.get("transformRevision") or 0),
        format=row.get("format") or payload.get("format"),
        created_at=_iso(row.get("created_at") or payload.get("created_at")),
        updated_at=_iso(row.get("updated_at") or payload.get("updated_at")),
    )
    return _jsonable(payload)


def _match_transform(transforms: list[dict[str, Any]], value: Any) -> dict[str, Any] | None:
    needle = str(value or "").strip().lower()
    if not needle:
        return None
    for table in transforms:
        if needle in {str(table.get("id") or "").lower(), str(table.get("name") or "").lower()}:
            return table
    return None


def _can_access_folder(cur: Any, folder_id: str, user_id: str, owner_id: str, min_level: str) -> bool:
    if _normalize_id(user_id) == _normalize_id(owner_id):
        return True
    cur.execute("SELECT role FROM instance01.mtd_users WHERE id = %s LIMIT 1", (user_id,))
    role_row = cur.fetchone()
    role = str((role_row or {}).get("role") or "NONE").upper()
    if role == "ADMIN":
        return True
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
        (folder_id, user_id),
    )
    row = cur.fetchone()
    level = str((row or {}).get("level") or "NONE").upper()
    return ACCESS_ORDER.get(level, 0) >= ACCESS_ORDER.get(str(min_level).upper(), 0)


def _coerce_uuid(value: Any) -> str:
    if value:
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            pass
    return str(uuid.uuid4())


def _stable_table_id(folder_id: str, physical_name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eventhorizon:{_normalize_id(folder_id)}:{physical_name}"))


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().replace("-", "").lower()


def _iso(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@contextmanager
def _connect() -> Iterator[Any]:
    database = os.getenv("POSTGRES_DBNAME") or os.getenv("POSTGRES_UPLOAD_DBNAME")
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=database,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()
