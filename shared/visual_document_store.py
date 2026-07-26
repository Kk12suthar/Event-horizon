"""Postgres persistence for Visual Documents.

The document itself is stored as a single ``jsonb`` blob validated by
``shared.visual_document``; every mutation is additionally appended to an
append-only revision log so undo/redo, agent reverts, and point-in-time restore
all replay through the same op format.

Two tables live in ``instance01``:

``mtd_visual_document``
    One row per canvas. ``document`` holds the full validated document, and
    ``revision`` mirrors ``document.metadata.revision`` so optimistic locking can
    be checked without deserialising the blob.
``mtd_visual_document_revision``
    One row per applied commit, keyed ``(document_id, revision)``. Row ``N``
    always contains the ops that turn revision ``N-1`` into revision ``N``, which
    is what makes ``restore_revision`` a deterministic replay.

Writes take ``SELECT ... FOR UPDATE`` on the document row and update the document
plus its revision row inside one transaction, so two concurrent agents can never
interleave commits or skip a revision number.

This module is imported by both the FastAPI backend and the agent server; it owns
storage only and never performs authorization (callers resolve access from the
``folder_id`` returned by :func:`get_document_row`).
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

import psycopg2
import psycopg2.extras
from pydantic import ValidationError

from shared.visual_document import (
    AddElementOp,
    AddLayerOp,
    Commit,
    CreateGroupOp,
    RemoveElementOp,
    RemoveLayerOp,
    SetSelectionOp,
    SetTitleOp,
    SetViewportOp,
    UngroupOp,
    UpdateElementOp,
    UpdateLayerOp,
    VisualDocument,
    VisualDocumentError,
    apply_commit,
    new_document,
    new_id,
    parse_ops,
    redo,
    undo,
)

ACTIVE_STATUS = "ACTIVE"
DELETED_STATUS = "DELETED"

AuthorKind = Literal["user", "agent", "system"]


class VisualDocumentStoreError(RuntimeError):
    """Storage-level failure. ``code``/``status_code`` map straight onto HTTP.

    Revision conflicts additionally carry ``current_revision`` so a client can
    rebase without a second round trip.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "visual_document_error",
        status_code: int = 400,
        current_revision: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.current_revision = current_revision


def ensure_visual_document_schema() -> None:
    """Create the Visual Document tables used by the backend and agent server."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instance01.mtd_visual_document (
                    id uuid PRIMARY KEY,
                    project_id uuid NOT NULL,
                    folder_id uuid NOT NULL
                        REFERENCES instance01.mtd_folder(id) ON DELETE CASCADE,
                    session_id uuid,
                    title text NOT NULL,
                    revision integer NOT NULL DEFAULT 0,
                    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
                    document jsonb NOT NULL,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT NOW(),
                    updated_at timestamptz NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instance01.mtd_visual_document_revision (
                    document_id uuid NOT NULL
                        REFERENCES instance01.mtd_visual_document(id) ON DELETE CASCADE,
                    revision integer NOT NULL,
                    commit jsonb NOT NULL,
                    author text,
                    author_kind varchar(16),
                    created_at timestamptz NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (document_id, revision)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_visual_document_folder_updated
                ON instance01.mtd_visual_document(folder_id, updated_at)
                """
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def create_document(
    project_id: str,
    folder_id: str,
    title: str,
    *,
    created_by: str,
    session_id: str | None = None,
    source_table_ids: list[str] | None = None,
) -> VisualDocument:
    """Insert an empty document with the standard layer stack at revision 0.

    The row id is a uuid4 and is reused verbatim as ``metadata.id`` (uuid text
    satisfies the schema's ``ID_PATTERN``), so the canvas can be addressed by one
    identifier everywhere.
    """
    project_uuid = _require_uuid(project_id, "project_id")
    folder_uuid = _require_uuid(folder_id, "folder_id")
    session_uuid = _require_uuid(session_id, "session_id") if session_id else None
    clean_title = str(title or "").strip()
    if not clean_title:
        raise VisualDocumentStoreError(
            "A visual document title is required.", code="missing_title", status_code=400
        )

    document_id = str(uuid.uuid4())
    try:
        doc = new_document(
            project_id=project_uuid,
            folder_id=folder_uuid,
            title=clean_title,
            document_id=document_id,
            session_id=session_uuid,
            created_by=created_by,
            source_table_ids=list(source_table_ids or []),
        )
    except (ValidationError, ValueError) as exc:
        raise VisualDocumentStoreError(
            f"The visual document could not be created: {exc}",
            code="invalid_document",
            status_code=400,
        ) from exc

    with _connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO instance01.mtd_visual_document(
                        id, project_id, folder_id, session_id, title, revision,
                        status, document, created_by, created_at, updated_at
                    ) VALUES (
                        %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s,
                        %s, %s::jsonb, %s, NOW(), NOW()
                    )
                    """,
                    (
                        document_id,
                        project_uuid,
                        folder_uuid,
                        session_uuid,
                        clean_title,
                        doc.metadata.revision,
                        ACTIVE_STATUS,
                        psycopg2.extras.Json(doc.model_dump(mode="json")),
                        created_by,
                    ),
                )
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            raise VisualDocumentStoreError(
                "The visual document could not be saved.",
                code="write_failed",
                status_code=400,
            ) from exc
    return doc


def get_document(document_id: str) -> VisualDocument:
    """Load and validate a document. Deleted documents are treated as missing."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            row = _select_document(cur, document_id)
    return _document_from_row(row)


def get_document_row(document_id: str) -> dict[str, Any]:
    """Metadata-only row (``folder_id``, ``project_id``, ``status``, ...).

    Used for authorization before the document blob is loaded or validated, so a
    caller without access never pays deserialisation cost.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, project_id::text, folder_id::text, session_id::text,
                       title, revision, status, created_by, created_at, updated_at
                FROM instance01.mtd_visual_document
                WHERE id = %s::uuid
                LIMIT 1
                """,
                (_require_uuid(document_id, "document_id"),),
            )
            row = cur.fetchone()
    if not row or str(row.get("status") or ACTIVE_STATUS).upper() == DELETED_STATUS:
        raise _not_found(document_id)
    return _jsonable(dict(row))


def list_documents(folder_id: str) -> list[dict[str, Any]]:
    """Summaries for every active document in a folder, newest change first."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, title, revision, updated_at, created_by,
                       jsonb_array_length(COALESCE(document -> 'elements', '[]'::jsonb))
                           AS element_count
                FROM instance01.mtd_visual_document
                WHERE folder_id = %s::uuid
                  AND COALESCE(status, 'ACTIVE') != 'DELETED'
                ORDER BY updated_at DESC
                """,
                (_require_uuid(folder_id, "folder_id"),),
            )
            rows = cur.fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "revision": int(row["revision"] or 0),
            "updated_at": _iso(row["updated_at"]),
            "created_by": row["created_by"],
            "element_count": int(row["element_count"] or 0),
        }
        for row in rows
    ]


def list_revisions(document_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """Revision log entries (newest first) without the stored op payloads."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _select_document_meta(cur, document_id)
            cur.execute(
                """
                SELECT revision, author, author_kind, created_at,
                       commit -> 'label' AS label
                FROM instance01.mtd_visual_document_revision
                WHERE document_id = %s::uuid
                ORDER BY revision DESC
                LIMIT %s
                """,
                (str(document_id), max(1, int(limit))),
            )
            rows = cur.fetchall()
    return [
        {
            "revision": int(row["revision"]),
            "author": row["author"],
            "author_kind": row["author_kind"],
            "label": row["label"],
            "created_at": _iso(row["created_at"]),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def commit_ops(
    document_id: str,
    ops: list[Any] | list[dict[str, Any]],
    *,
    author: str,
    author_kind: AuthorKind = "user",
    base_revision: int | None = None,
    label: str = "edit",
) -> tuple[VisualDocument, Commit]:
    """Apply ops as one new revision under optimistic locking.

    ``base_revision`` is the revision the caller believes it is editing. When it
    no longer matches the stored revision the commit is rejected with
    ``revision_conflict`` (HTTP 409) rather than silently clobbering the other
    author's work.
    """
    parsed = parse_ops(list(ops))

    with _connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _lock_document(cur, document_id, base_revision)
                doc = _document_from_row(row)
                updated, commit = apply_commit(
                    doc,
                    parsed,
                    author=author,
                    author_kind=author_kind,
                    label=label,
                )
                _persist_commit(cur, document_id, updated, commit)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return updated, commit


def undo_document(document_id: str, author: str) -> tuple[VisualDocument, Commit | None]:
    """Undo the newest commit, recording the inverse as its own revision.

    Returns ``(document, None)`` when there is nothing left to undo.
    """
    with _connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _lock_document(cur, document_id, None)
                doc = _document_from_row(row)
                updated, undone = undo(doc, author=author)
                if undone is None:
                    conn.rollback()
                    return doc, None
                # ``undo`` keeps the reverted commit out of the history stack, so
                # the revision log gets an explicit entry whose ops are the ones
                # actually applied. That keeps the log replayable.
                record = Commit(
                    id=new_id("cmt"),
                    revision=updated.metadata.revision,
                    at=updated.metadata.updated_at,
                    author=author,
                    author_kind="system",
                    label=f"undo:{undone.label}",
                    ops=[op.model_copy(deep=True) for op in undone.inverse_ops],
                    inverse_ops=[op.model_copy(deep=True) for op in undone.ops],
                )
                _persist_commit(cur, document_id, updated, record)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return updated, record


def redo_document(document_id: str, author: str) -> tuple[VisualDocument, Commit | None]:
    """Re-apply the most recently undone commit as a new revision."""
    with _connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _lock_document(cur, document_id, None)
                doc = _document_from_row(row)
                updated, commit = redo(doc, author=author)
                if commit is None:
                    conn.rollback()
                    return doc, None
                _persist_commit(cur, document_id, updated, commit)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return updated, commit


def restore_revision(
    document_id: str, revision: int, author: str
) -> tuple[VisualDocument, Commit | None]:
    """Restore the state a document had at ``revision``.

    The target state is rebuilt by replaying the stored commits ``1..revision``
    onto a fresh document, and the difference is then committed as a *new*
    revision. History is therefore never rewritten - a restore is just another
    forward commit and can itself be undone.
    """
    target_revision = int(revision)
    if target_revision < 0:
        raise VisualDocumentStoreError(
            "A revision number cannot be negative.",
            code="invalid_revision",
            status_code=400,
        )

    with _connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _lock_document(cur, document_id, None)
                current = _document_from_row(row)
                if target_revision > int(row["revision"] or 0):
                    raise VisualDocumentStoreError(
                        f"Revision {target_revision} does not exist for this document.",
                        code="unknown_revision",
                        status_code=404,
                    )
                cur.execute(
                    """
                    SELECT revision, commit, author, author_kind
                    FROM instance01.mtd_visual_document_revision
                    WHERE document_id = %s::uuid AND revision <= %s
                    ORDER BY revision ASC
                    """,
                    (str(document_id), target_revision),
                )
                history = cur.fetchall()
                target = _replay(current, history)
                ops = _restore_ops(current, target)
                if not ops:
                    conn.rollback()
                    return current, None
                updated, commit = apply_commit(
                    current,
                    ops,
                    author=author,
                    author_kind="user",
                    label=f"restore:r{target_revision}",
                )
                _persist_commit(cur, document_id, updated, commit)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return updated, commit


def soft_delete_document(document_id: str) -> None:
    """Mark a document ``DELETED``; revisions are retained for audit."""
    with _connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                _select_document_meta(cur, document_id)
                cur.execute(
                    """
                    UPDATE instance01.mtd_visual_document
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s::uuid
                    """,
                    (DELETED_STATUS, str(document_id)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _persist_commit(
    cur: Any, document_id: str, doc: VisualDocument, commit: Commit
) -> None:
    """Write the document blob and its revision row inside the caller's txn."""
    cur.execute(
        """
        UPDATE instance01.mtd_visual_document
        SET document = %s::jsonb,
            revision = %s,
            title = %s,
            updated_at = NOW()
        WHERE id = %s::uuid
        """,
        (
            psycopg2.extras.Json(doc.model_dump(mode="json")),
            doc.metadata.revision,
            doc.metadata.title,
            str(document_id),
        ),
    )
    cur.execute(
        """
        INSERT INTO instance01.mtd_visual_document_revision(
            document_id, revision, commit, author, author_kind, created_at
        ) VALUES (%s::uuid, %s, %s::jsonb, %s, %s, NOW())
        ON CONFLICT (document_id, revision) DO NOTHING
        """,
        (
            str(document_id),
            commit.revision,
            psycopg2.extras.Json(commit.model_dump(mode="json")),
            commit.author,
            commit.author_kind,
        ),
    )


def _lock_document(
    cur: Any, document_id: str, base_revision: int | None
) -> dict[str, Any]:
    """``SELECT ... FOR UPDATE`` the row and enforce the optimistic lock."""
    cur.execute(
        """
        SELECT id::text, project_id::text, folder_id::text, session_id::text,
               title, revision, status, document, created_by
        FROM instance01.mtd_visual_document
        WHERE id = %s::uuid
        FOR UPDATE
        """,
        (_require_uuid(document_id, "document_id"),),
    )
    row = cur.fetchone()
    if not row or str(row.get("status") or ACTIVE_STATUS).upper() == DELETED_STATUS:
        raise _not_found(document_id)
    current_revision = int(row["revision"] or 0)
    if base_revision is not None and int(base_revision) != current_revision:
        raise VisualDocumentStoreError(
            "This canvas changed since it was loaded. Reload before editing again.",
            code="revision_conflict",
            status_code=409,
            current_revision=current_revision,
        )
    return dict(row)


def _select_document(cur: Any, document_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id::text, project_id::text, folder_id::text, session_id::text,
               title, revision, status, document, created_by
        FROM instance01.mtd_visual_document
        WHERE id = %s::uuid
        LIMIT 1
        """,
        (_require_uuid(document_id, "document_id"),),
    )
    row = cur.fetchone()
    if not row or str(row.get("status") or ACTIVE_STATUS).upper() == DELETED_STATUS:
        raise _not_found(document_id)
    return dict(row)


def _select_document_meta(cur: Any, document_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id::text, revision, status
        FROM instance01.mtd_visual_document
        WHERE id = %s::uuid
        LIMIT 1
        """,
        (_require_uuid(document_id, "document_id"),),
    )
    row = cur.fetchone()
    if not row or str(row.get("status") or ACTIVE_STATUS).upper() == DELETED_STATUS:
        raise _not_found(document_id)
    return dict(row)


def _document_from_row(row: dict[str, Any]) -> VisualDocument:
    payload = row.get("document")
    if not isinstance(payload, dict):
        raise VisualDocumentStoreError(
            "The stored visual document is unreadable.",
            code="corrupt_document",
            status_code=500,
        )
    try:
        return VisualDocument.model_validate(payload)
    except ValidationError as exc:
        raise VisualDocumentStoreError(
            f"The stored visual document failed validation: {exc.errors()[0]['msg']}",
            code="corrupt_document",
            status_code=500,
        ) from exc


def _replay(current: VisualDocument, history: list[dict[str, Any]]) -> VisualDocument:
    """Rebuild a document by replaying stored commits onto a fresh canvas."""
    metadata = current.metadata
    doc = new_document(
        project_id=metadata.project_id,
        folder_id=metadata.folder_id,
        title=metadata.title,
        document_id=metadata.id,
        session_id=metadata.session_id,
        created_by=metadata.created_by,
        source_table_ids=list(metadata.source_table_ids),
    )
    for entry in history:
        commit = entry.get("commit") or {}
        ops = commit.get("ops") or []
        if not ops:
            continue
        try:
            doc, _ = apply_commit(
                doc,
                parse_ops(list(ops)),
                author=str(entry.get("author") or "system"),
                author_kind="system",
                label=str(commit.get("label") or "replay"),
            )
        except VisualDocumentError as exc:
            raise VisualDocumentStoreError(
                f"Revision {entry.get('revision')} could not be replayed: {exc}",
                code="replay_failed",
                status_code=409,
            ) from exc
    return doc


def _restore_ops(current: VisualDocument, target: VisualDocument) -> list[Any]:
    """Ops that turn ``current`` into ``target``.

    Content is rebuilt rather than diffed field by field: everything currently on
    the canvas is removed and the target content is re-added. That keeps the
    result exactly reproducible (and expressible in the shared op format) at the
    cost of fresh element audit stamps.
    """
    if current.model_dump(
        mode="json", exclude={"metadata", "history", "redo_stack"}
    ) == target.model_dump(mode="json", exclude={"metadata", "history", "redo_stack"}):
        return []

    ops: list[Any] = []
    if current.viewport.selected_ids:
        ops.append(SetSelectionOp(element_ids=[]))
    for element in current.elements:
        if element.locked:
            ops.append(UpdateElementOp(element_id=element.id, patch={"locked": False}))
    # Edges first: a node cannot be removed while an edge still attaches to it.
    for element in sorted(
        current.elements, key=lambda item: 0 if item.type == "edge" else 1
    ):
        ops.append(RemoveElementOp(element_id=element.id))
    for group in current.groups:
        ops.append(UngroupOp(group_id=group.id))

    target_layers = {layer.id: layer for layer in target.layers}
    current_layers = {layer.id: layer for layer in current.layers}
    for layer_id, layer in current_layers.items():
        if layer_id not in target_layers:
            ops.append(RemoveLayerOp(layer_id=layer_id))
        elif layer.model_dump() != target_layers[layer_id].model_dump():
            patch = {
                key: value
                for key, value in target_layers[layer_id].model_dump().items()
                if key != "id"
            }
            ops.append(UpdateLayerOp(layer_id=layer_id, patch=patch))
    for layer_id, layer in target_layers.items():
        if layer_id not in current_layers:
            ops.append(AddLayerOp(layer=layer.model_copy(deep=True)))

    for element in sorted(
        target.elements, key=lambda item: 1 if item.type == "edge" else 0
    ):
        ops.append(AddElementOp(element=element.model_copy(deep=True)))
    for group in target.groups:
        ops.append(CreateGroupOp(group=group.model_copy(deep=True)))

    if current.metadata.title != target.metadata.title:
        ops.append(SetTitleOp(title=target.metadata.title))
    if (current.viewport.zoom, current.viewport.x, current.viewport.y) != (
        target.viewport.zoom,
        target.viewport.x,
        target.viewport.y,
    ):
        ops.append(
            SetViewportOp(
                zoom=target.viewport.zoom, x=target.viewport.x, y=target.viewport.y
            )
        )
    if target.viewport.selected_ids:
        ops.append(SetSelectionOp(element_ids=list(target.viewport.selected_ids)))
    return ops


def _not_found(document_id: Any) -> VisualDocumentStoreError:
    return VisualDocumentStoreError(
        f"Visual document '{document_id}' was not found.",
        code="not_found",
        status_code=404,
    )


def _require_uuid(value: Any, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise VisualDocumentStoreError(
            f"The {field} '{value}' is not a valid identifier.",
            code="invalid_identifier",
            status_code=400,
        ) from exc


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


__all__ = [
    "VisualDocumentStoreError",
    "ensure_visual_document_schema",
    "create_document",
    "get_document",
    "get_document_row",
    "list_documents",
    "list_revisions",
    "commit_ops",
    "undo_document",
    "redo_document",
    "restore_revision",
    "soft_delete_document",
]
