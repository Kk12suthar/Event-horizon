"""REST API for agent-controlled Visual Documents (the visual canvas).

Every mutation goes through the shared op format in ``shared.visual_document``, so
a user drag, an agent patch, and an undo are all the same kind of commit. Layout
is never hand-rolled here either: the endpoints ask ``shared.visual_layout`` for
ops and commit those, which keeps agent and user edits on one history stack.

Authorization is always resolved from the document's folder - reads need
``VIEWER``, writes need ``ANALYST`` - using the metadata-only store row so an
unauthorized caller never causes the document blob to be loaded.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from security.policy import current_user_id, require_folder_access, require_table_access, user_from_request

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.visual_document import VisualDocument, VisualDocumentError
from shared.visual_document_store import (
    VisualDocumentStoreError,
    commit_ops,
    create_document,
    ensure_visual_document_schema,
    get_document,
    get_document_row,
    list_documents,
    redo_document,
    soft_delete_document,
    undo_document,
)
from shared.visual_layout import (
    LayoutOptions,
    align_ops,
    check_readability,
    layout_ops,
    summarize,
)

router = APIRouter(prefix="/api/v1/visual-documents", tags=["visual-documents"])

AUTHOR_KIND = "user"

# Schema creation is deferred so importing this module never needs a live DB.
_SCHEMA_READY = False


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class VisualDocumentCreate(BaseModel):
    """Payload for creating an empty canvas in a folder."""

    project_id: str
    folder_id: str
    title: str = Field(min_length=1, max_length=300)
    session_id: str | None = None
    source_table_ids: list[str] = Field(default_factory=list, max_length=64)


class VisualCommitRequest(BaseModel):
    """A batch of ops applied as one revision.

    ``base_revision`` is the revision the client last saw; omit it only for
    fire-and-forget edits that may safely overwrite concurrent changes.
    """

    ops: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    base_revision: int | None = Field(default=None, ge=0)
    label: str = Field(default="edit", max_length=300)


class VisualLayoutRequest(BaseModel):
    """Deterministic layout request; geometry is computed server side."""

    algorithm: Literal["layered", "tree", "grid", "timeline", "radial"] = "layered"
    direction: Literal["right", "down", "left", "up"] = "right"
    node_spacing: float = Field(default=56.0, gt=0, le=5_000)
    rank_spacing: float = Field(default=140.0, gt=0, le=5_000)
    columns: int | None = Field(default=None, ge=1, le=64)
    element_ids: list[str] | None = Field(default=None, max_length=2_000)
    base_revision: int | None = Field(default=None, ge=0)


class VisualAlignRequest(BaseModel):
    """Align two or more elements on one edge or axis."""

    element_ids: list[str] = Field(min_length=2, max_length=2_000)
    axis: Literal["left", "right", "top", "bottom", "center-x", "center-y"]
    base_revision: int | None = Field(default=None, ge=0)


class VisualDocumentResponse(BaseModel):
    document: dict[str, Any]


class VisualDocumentListResponse(BaseModel):
    documents: list[dict[str, Any]]


class VisualCommitResponse(BaseModel):
    """``commit`` is ``null`` when the request was a no-op."""

    document: dict[str, Any]
    commit: dict[str, Any] | None = None


class VisualOutlineResponse(BaseModel):
    outline: list[dict[str, Any]]
    summary: dict[str, Any]


class VisualMessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_schema() -> None:
    """Create the persistence tables once per process, on first real use."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_visual_document_schema()
    _SCHEMA_READY = True


@contextmanager
def _translated_errors() -> Iterator[None]:
    """Map document/store failures onto stable HTTP responses."""
    try:
        yield
    except VisualDocumentError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    except VisualDocumentStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=_store_detail(exc)) from exc


def _store_detail(exc: VisualDocumentStoreError) -> dict[str, Any]:
    detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    current_revision = getattr(exc, "current_revision", None)
    if current_revision is not None:
        detail["current_revision"] = current_revision
    return detail


def _authorize_document(
    document_id: str, request: Request, db: Session, min_level: str
) -> dict[str, Any]:
    """Resolve the document's folder and require ``min_level`` access to it."""
    _ensure_schema()
    with _translated_errors():
        row = get_document_row(document_id)
    require_folder_access(row["folder_id"], user_from_request(request), db, min_level=min_level)
    return row


def _author(request: Request) -> str:
    return current_user_id(user_from_request(request))



def _validated_creation_context(
    payload: VisualDocumentCreate, user: dict[str, Any], db: Session
) -> str:
    """Derive project/folder/session/table relationships from trusted rows."""
    folder_project_id = db.execute(
        text(
            "SELECT project_id::text FROM instance01.mtd_folder "
            "WHERE id = CAST(:folder_id AS uuid) AND COALESCE(status, 'ACTIVE') != 'DELETED'"
        ),
        {"folder_id": payload.folder_id},
    ).scalar()
    if not folder_project_id:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if str(folder_project_id).replace("-", "").lower() != payload.project_id.replace("-", "").lower():
        raise HTTPException(status_code=409, detail="The folder does not belong to the requested project.")
    if payload.session_id:
        session_folder_id = db.execute(
            text(
                "SELECT folder_id::text FROM instance01.mtd_session "
                "WHERE id = CAST(:session_id AS uuid) AND COALESCE(status, 'ACTIVE') != 'DELETED'"
            ),
            {"session_id": payload.session_id},
        ).scalar()
        if not session_folder_id:
            raise HTTPException(status_code=404, detail="Session not found.")
        if str(session_folder_id).replace("-", "").lower() != payload.folder_id.replace("-", "").lower():
            raise HTTPException(status_code=409, detail="The session does not belong to this folder.")
    for table_id in payload.source_table_ids:
        require_table_access(table_id, payload.folder_id, user, db, min_level="VIEWER")
    return str(folder_project_id)

def _document_payload(doc: VisualDocument) -> dict[str, Any]:
    return doc.model_dump(mode="json")


def _commit_payload(commit: Any) -> dict[str, Any] | None:
    return commit.model_dump(mode="json") if commit is not None else None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.post("", response_model=VisualDocumentResponse)
def create_visual_document(
    payload: VisualDocumentCreate, request: Request, db: Session = Depends(get_db)
) -> VisualDocumentResponse:
    """
    Create an empty visual document with the standard layer stack.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents

    **Parameters:**
    - payload: VisualDocumentCreate - target project/folder, title, optional session
      and approved source tables

    **Returns:**
    - VisualDocumentResponse with the new document at revision 0
    """
    _ensure_schema()
    user = user_from_request(request)
    require_folder_access(payload.folder_id, user, db, min_level="ANALYST")
    with _translated_errors():
        project_id = _validated_creation_context(payload, user, db)
        doc = create_document(
            project_id,
            payload.folder_id,
            payload.title,
            created_by=current_user_id(user),
            session_id=payload.session_id,
            source_table_ids=payload.source_table_ids,
        )
    return VisualDocumentResponse(document=_document_payload(doc))


@router.get("", response_model=VisualDocumentListResponse)
def list_visual_documents(
    folder_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualDocumentListResponse:
    """
    List active visual documents in a folder, newest change first.

    **HTTP Method:** GET
    **Path:** /api/v1/visual-documents?folder_id=...

    **Returns:**
    - VisualDocumentListResponse with id, title, revision, updated_at, created_by
      and element_count per document
    """
    _ensure_schema()
    require_folder_access(folder_id, user_from_request(request), db, min_level="VIEWER")
    with _translated_errors():
        documents = list_documents(folder_id)
    return VisualDocumentListResponse(documents=documents)


@router.get("/{document_id}", response_model=VisualDocumentResponse)
def get_visual_document(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualDocumentResponse:
    """
    Fetch a full visual document, including history and redo stack.

    **HTTP Method:** GET
    **Path:** /api/v1/visual-documents/{document_id}
    """
    _authorize_document(document_id, request, db, "VIEWER")
    with _translated_errors():
        doc = get_document(document_id)
    return VisualDocumentResponse(document=_document_payload(doc))


@router.get("/{document_id}/outline", response_model=VisualOutlineResponse)
def get_visual_document_outline(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualOutlineResponse:
    """
    Accessible outline plus a compact summary of the canvas.

    **HTTP Method:** GET
    **Path:** /api/v1/visual-documents/{document_id}/outline

    **Returns:**
    - VisualOutlineResponse - the screen-reader/keyboard parallel representation
      and the summary the agent uses to reason about the canvas
    """
    _authorize_document(document_id, request, db, "VIEWER")
    with _translated_errors():
        doc = get_document(document_id)
        return VisualOutlineResponse(outline=doc.outline(), summary=summarize(doc))


@router.get("/{document_id}/readability")
def get_visual_document_readability(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Report overlaps, crowding, out-of-bounds elements, and missing labels.

    **HTTP Method:** GET
    **Path:** /api/v1/visual-documents/{document_id}/readability
    """
    _authorize_document(document_id, request, db, "VIEWER")
    with _translated_errors():
        doc = get_document(document_id)
        return check_readability(doc)


@router.delete("/{document_id}", response_model=VisualMessageResponse)
def delete_visual_document(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualMessageResponse:
    """
    Soft delete a visual document; its revision log is retained for audit.

    **HTTP Method:** DELETE
    **Path:** /api/v1/visual-documents/{document_id}
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        soft_delete_document(document_id)
    return VisualMessageResponse(message="Visual document deleted")


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@router.post("/{document_id}/commit", response_model=VisualCommitResponse)
def commit_visual_document(
    document_id: str,
    payload: VisualCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> VisualCommitResponse:
    """
    Apply a batch of ops as one new revision.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents/{document_id}/commit

    **Parameters:**
    - payload: VisualCommitRequest - ops, the base_revision being edited, label

    **Returns:**
    - VisualCommitResponse with the new document and the commit (including the
      inverse ops that power undo)

    **Errors:**
    - 409 revision_conflict (with current_revision) when base_revision is stale
    - 422 when an op is malformed or would break document integrity
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        doc, commit = commit_ops(
            document_id,
            payload.ops,
            author=_author(request),
            author_kind=AUTHOR_KIND,
            base_revision=payload.base_revision,
            label=payload.label,
        )
    return VisualCommitResponse(
        document=_document_payload(doc), commit=_commit_payload(commit)
    )


@router.post("/{document_id}/undo", response_model=VisualCommitResponse)
def undo_visual_document(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualCommitResponse:
    """
    Undo the newest commit by applying its inverse ops as a new revision.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents/{document_id}/undo

    **Returns:**
    - VisualCommitResponse; ``commit`` is null when there was nothing to undo
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        doc, commit = undo_document(document_id, _author(request))
    return VisualCommitResponse(
        document=_document_payload(doc), commit=_commit_payload(commit)
    )


@router.post("/{document_id}/redo", response_model=VisualCommitResponse)
def redo_visual_document(
    document_id: str, request: Request, db: Session = Depends(get_db)
) -> VisualCommitResponse:
    """
    Re-apply the most recently undone commit.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents/{document_id}/redo

    **Returns:**
    - VisualCommitResponse; ``commit`` is null when the redo stack is empty
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        doc, commit = redo_document(document_id, _author(request))
    return VisualCommitResponse(
        document=_document_payload(doc), commit=_commit_payload(commit)
    )


@router.post("/{document_id}/layout", response_model=VisualCommitResponse)
def layout_visual_document(
    document_id: str,
    payload: VisualLayoutRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> VisualCommitResponse:
    """
    Run a deterministic layout pass and commit the resulting geometry ops.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents/{document_id}/layout

    **Parameters:**
    - payload: VisualLayoutRequest - algorithm, direction, spacing, optional
      columns, optional element_ids subset, base_revision

    **Returns:**
    - VisualCommitResponse; when the canvas is already laid out the document is
      returned unchanged with ``commit`` null
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        doc = get_document(document_id)
        options = LayoutOptions(
            payload.algorithm,
            direction=payload.direction,
            node_spacing=payload.node_spacing,
            rank_spacing=payload.rank_spacing,
            columns=payload.columns,
            element_ids=payload.element_ids,
        )
        ops = layout_ops(doc, options)
        if not ops:
            return VisualCommitResponse(document=_document_payload(doc), commit=None)
        doc, commit = commit_ops(
            document_id,
            ops,
            author=_author(request),
            author_kind=AUTHOR_KIND,
            base_revision=payload.base_revision,
            label=f"layout:{payload.algorithm}",
        )
    return VisualCommitResponse(
        document=_document_payload(doc), commit=_commit_payload(commit)
    )


@router.post("/{document_id}/align", response_model=VisualCommitResponse)
def align_visual_document(
    document_id: str,
    payload: VisualAlignRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> VisualCommitResponse:
    """
    Align the given elements on one edge or axis.

    **HTTP Method:** POST
    **Path:** /api/v1/visual-documents/{document_id}/align

    **Returns:**
    - VisualCommitResponse; already-aligned elements yield ``commit`` null
    """
    _authorize_document(document_id, request, db, "ANALYST")
    with _translated_errors():
        doc = get_document(document_id)
        ops = align_ops(doc, payload.element_ids, payload.axis)
        if not ops:
            return VisualCommitResponse(document=_document_payload(doc), commit=None)
        doc, commit = commit_ops(
            document_id,
            ops,
            author=_author(request),
            author_kind=AUTHOR_KIND,
            base_revision=payload.base_revision,
            label=f"align:{payload.axis}",
        )
    return VisualCommitResponse(
        document=_document_payload(doc), commit=_commit_payload(commit)
    )
