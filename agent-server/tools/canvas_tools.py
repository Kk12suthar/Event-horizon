"""Agent-controlled Visual Canvas tools.

Every tool here mutates a ``VisualDocument`` through the shared, authoritative
schema in ``shared.visual_document`` and the deterministic layout engine in
``shared.visual_layout``:

* elements are built as **typed op objects** (never dicts of guessed geometry),
* geometry for graphs is always produced by ``shared.visual_layout.layout_ops``,
* persistence goes through ``shared.visual_document_store.commit_ops`` so agent
  edits and user undo/redo share one history,
* ``VisualDocumentError`` is returned as ``{"error": code, "message": ...}``
  instead of raised, so the model can read the failure and correct itself.

Required call order for the model: ``canvas_create`` -> add elements
(``canvas_add_node`` / ``canvas_add_edge`` / ``canvas_create_chart`` ...) ->
``canvas_apply_layout`` -> ``canvas_inspect``. The flagship
``canvas_create_process_map`` collapses that into two commits (content, then an
engine-computed layout pass).

Store contract (implemented in ``shared.visual_document_store``)::

    create_document(folder_id=..., user_id=..., session_id=..., title=...) -> VisualDocument
    load_document(document_id, folder_id=..., user_id=...)                 -> VisualDocument
    list_documents(folder_id=..., user_id=..., session_id=...)             -> list
    commit_ops(document_id, ops, author=..., author_kind="agent",
               base_revision=None, label=...)                             -> (VisualDocument, Commit)
    undo_document(document_id, author=...)                                 -> (VisualDocument, Commit | None)

The store module is bound defensively (see ``_bind``) because it is owned by the
backend persistence layer; the bound names stay module-level attributes so tests
can patch them with an in-memory fake.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import re
from typing import Any, get_args, get_type_hints

from pydantic import ValidationError

from shared.visual_document import (
    DEFAULT_LAYERS,
    AddElementOp,
    ChartElement,
    ChartType,
    Commit,
    CreateGroupOp,
    EdgeElement,
    EdgeKind,
    FilterOp,
    GanttBar,
    GanttElement,
    Group,
    KpiElement,
    LegendElement,
    LegendEntry,
    Metric,
    MoveElementsOp,
    NodeElement,
    NodeKind,
    Provenance,
    PathElement,
    Point,
    ProvenanceFilter,
    Rect,
    RemoveElementOp,
    ResizeElementOp,
    SetStyleOp,
    SetTitleOp,
    ShapeElement,
    ShapeKind,
    StyleTokens,
    SwatchToken,
    TextElement,
    VisualDocument,
    VisualDocumentError,
    new_id,
)
from shared.visual_layout import (
    DEFAULT_NODE_H,
    DEFAULT_NODE_W,
    Direction,
    LayoutOptions,
    align_ops,
    check_readability,
    compute_layout,
    content_bounds,
    distribute_ops,
    iter_layout_names,
    layout_ops,
    summarize,
)
from tools.spec import ToolSpec
from shared.workspace_store import WorkspaceStoreError
from tools.visualize_tools import (
    _selected as _selected_prepared_table,
    aggregate as aggregate_prepared_table,
    create_kpi as create_prepared_kpi,
)

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
SURFACES = frozenset({"canvas"})


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


FOLDER = {"type": "string", "description": "EventHorizon folder UUID."}
SESSION = {"type": "string", "description": "Active EventHorizon session UUID."}
DOCUMENT = {"type": "string", "description": "Visual document id returned by canvas_create."}


# ---------------------------------------------------------------------------
# Vocabularies - derived from the schema, never retyped
# ---------------------------------------------------------------------------


def _literals(annotation: Any) -> list[str]:
    return [value for value in get_args(annotation) if isinstance(value, str)]


def _field_literals(model: Any, field: str) -> list[str]:
    return _literals(model.model_fields[field].annotation)


NODE_KINDS = _literals(NodeKind)
EDGE_KINDS = _literals(EdgeKind)
CHART_TYPES = _literals(ChartType)
SHAPE_KINDS = _literals(ShapeKind)
SWATCH_TOKENS = _literals(SwatchToken)
FILTER_OPS = _literals(FilterOp)
EDGE_MARKERS = _field_literals(EdgeElement, "marker")
EDGE_ROUTINGS = _field_literals(EdgeElement, "routing")
TEXT_ROLES = _field_literals(TextElement, "role")
LEGEND_SHAPES = _field_literals(LegendEntry, "shape")
LEGEND_ORIENTATIONS = _field_literals(LegendElement, "orientation")
METRIC_FORMATS = _field_literals(Metric, "format")
AGGREGATIONS = _field_literals(Provenance, "aggregation")
GANTT_TIME_UNITS = _field_literals(GanttElement, "time_unit")
KPI_TRENDS = _field_literals(KpiElement, "trend")
EMPHASIS_TOKENS = _field_literals(StyleTokens, "emphasis")
STROKE_TOKENS = _field_literals(StyleTokens, "stroke")
LAYER_IDS = [layer_id for layer_id, _name, _index, _kind in DEFAULT_LAYERS]
LAYOUT_ALGORITHMS = list(iter_layout_names())
LAYOUT_DIRECTIONS = _literals(Direction)

DEFAULT_NODE_LAYER = "layer_semantic"
DEFAULT_DATA_LAYER = "layer_data"
DEFAULT_ANNOTATION_LAYER = "layer_annotation"
DEFAULT_FREEFORM_LAYER = "layer_freeform"


def _axes(function: Any, fallback: list[str]) -> list[str]:
    try:
        return _literals(get_type_hints(function)["axis"]) or fallback
    except Exception:  # pragma: no cover - typing introspection fallback
        return fallback


ALIGN_AXES = _axes(align_ops, ["left", "right", "top", "bottom", "center-x", "center-y"])
DISTRIBUTE_AXES = _axes(distribute_ops, ["x", "y"])

STYLE_PROPERTIES: dict[str, Any] = {}
for _name, _field in StyleTokens.model_fields.items():
    _values = _literals(_field.annotation)
    STYLE_PROPERTIES[_name] = (
        {"type": "string", "enum": _values}
        if _values
        else {"type": "number", "minimum": 0.0, "maximum": 1.0}
    )
STYLE_SCHEMA = _obj(dict(STYLE_PROPERTIES))

# Default element footprints. Graph geometry is engine-computed; these are only
# the initial boxes handed to the layout pass or to standalone data widgets.
CHART_SIZE = (480.0, 320.0)
KPI_SIZE = (240.0, 140.0)
GANTT_SIZE = (760.0, 360.0)
TEXT_SIZE = (320.0, 96.0)
SHAPE_SIZE = (200.0, 120.0)
LEGEND_WIDTH = 260.0
LEGEND_ROW = 26.0
SLOT_GAP = 64.0

STROKE_SERIES = ["accent", "info", "success", "warning", "danger", "strong"]


# ---------------------------------------------------------------------------
# Visual document store binding
# ---------------------------------------------------------------------------


def _store_stub(name: str):
    def _missing(*_args: Any, **_kwargs: Any) -> Any:
        raise VisualDocumentError(
            f"shared.visual_document_store.{name} is unavailable, so canvases cannot be persisted.",
            code="store_unavailable",
        )

    return _missing


try:  # pragma: no cover - import wiring
    _store = importlib.import_module("shared.visual_document_store")
except Exception:  # pragma: no cover - store not installed yet
    _store = None


def _bind(*candidates: str):
    for name in candidates:
        function = getattr(_store, name, None) if _store is not None else None
        if callable(function):
            return function
    return _store_stub(candidates[0])


create_document = _bind("create_document", "create_canvas", "new_canvas")
load_document = _bind("load_document", "get_document", "read_document")
list_documents = _bind("list_documents", "list_canvases")
commit_ops = _bind("commit_ops", "apply_ops", "commit")
undo_document = _bind("undo_document", "undo", "undo_commit")

redo_document = _bind("redo_document", "redo", "redo_commit")

def _call_store(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a store function, dropping keyword arguments it does not declare."""
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):  # builtins / mocks
        return function(*args, **kwargs)
    if any(parameter.kind is parameter.VAR_KEYWORD for parameter in parameters.values()):
        return function(*args, **kwargs)
    allowed = {key: value for key, value in kwargs.items() if key in parameters}
    return function(*args, **allowed)


def _split(result: Any) -> tuple[Any, Any]:
    """Normalise a store return value into ``(document_like, commit_like)``."""
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        return result[0], result[1]
    if isinstance(result, VisualDocument):
        return result, None
    if isinstance(result, dict):
        document = result.get("document") or result.get("doc") or result
        return document, result.get("commit")
    document = getattr(result, "document", None)
    if document is not None:
        return document, getattr(result, "commit", None)
    return result, None


def _as_document(value: Any) -> VisualDocument:
    if isinstance(value, VisualDocument):
        return value
    if isinstance(value, dict):
        try:
            return VisualDocument.model_validate(value)
        except ValidationError as exc:
            raise VisualDocumentError(
                f"the visual document store returned an invalid document: {exc.errors()[0]['msg']}",
                code="store_contract",
            ) from exc
    raise VisualDocumentError(
        "the visual document store did not return a visual document.", code="store_contract"
    )


def _as_commit(value: Any) -> Commit | None:
    if value is None:
        return None
    if isinstance(value, Commit):
        return value
    if isinstance(value, dict):
        try:
            return Commit.model_validate(value)
        except ValidationError:  # pragma: no cover - tolerated store shape
            return None
    return None


def _load(document_id: Any, folder_id: str | None, user_id: str | None) -> VisualDocument:
    if not document_id or not str(document_id).strip():
        raise VisualDocumentError(
            "document_id is required. Call canvas_create first, or canvas_list to find an existing canvas.",
            code="missing_document_id",
        )
    result = _call_store(
        load_document, str(document_id), folder_id=folder_id, user_id=user_id
    )
    document = _as_document(_split(result)[0])
    if folder_id and str(document.metadata.folder_id) != str(folder_id):
        raise VisualDocumentError(
            "the requested canvas does not belong to the active folder.",
            code="canvas_scope_mismatch",
            path=str(document_id),
        )
    return document


def _commit(
    document_id: Any,
    ops: list[Any],
    user_id: str | None,
    label: str,
    base_revision: int | None = None,
) -> tuple[VisualDocument, Commit]:
    if not ops:
        raise VisualDocumentError("commit contains no ops", code="empty_commit")
    result = _call_store(
        commit_ops,
        str(document_id),
        ops,
        author=user_id or "agent",
        author_kind="agent",
        base_revision=base_revision,
        label=label,
    )
    document_like, commit_like = _split(result)
    document = _as_document(document_like)
    commit = _as_commit(commit_like) or (document.history[-1] if document.history else None)
    if commit is None:
        raise VisualDocumentError(
            "the visual document store did not return a commit.", code="store_contract"
        )
    return document, commit


# ---------------------------------------------------------------------------
# Result shaping
# ---------------------------------------------------------------------------


def _patch_result(
    document: VisualDocument,
    commits: list[Commit],
    label: str,
    element_ids: list[str],
    **extra: Any,
) -> dict[str, Any]:
    latest = commits[-1]
    artifact: dict[str, Any] = {
        "artifact_type": "visual_patch",
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "commit": latest.model_dump(mode="json"),
        "label": label,
    }
    if len(commits) > 1:
        artifact["commits"] = [commit.model_dump(mode="json") for commit in commits]
    payload = {
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "element_ids": list(element_ids),
        "artifact": artifact,
        "readability": check_readability(document),
    }
    payload.update(extra)
    return payload


def _noop_result(document: VisualDocument, label: str, message: str) -> dict[str, Any]:
    return {
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "element_ids": [],
        "changed": False,
        "label": label,
        "message": message,
        "readability": check_readability(document),
    }


def _guarded(handler: Any) -> Any:
    """Return schema/layout failures as data so the model can self-correct."""

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except VisualDocumentError as exc:
            return exc.to_dict()
        except ValidationError as exc:
            first = exc.errors()[0]
            path = ".".join(str(part) for part in first["loc"])
            return {
                "error": "invalid_element",
                "message": f"{first['msg']}{f' at {path}' if path else ''}",
                "path": path or None,
            }

    return wrapper


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("_", str(value or "")).strip("_").lower()
    slug = slug[:60]
    if not slug or not slug[0].isalnum():
        slug = f"n_{slug}".strip("_")[:60]
    return slug or "node"


def _unique_id(seed: str, used: set[str]) -> str:
    base = _slugify(seed)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"[:64]
        suffix += 1
    used.add(candidate)
    return candidate


def _text(value: Any, field: str, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if not text and required:
        raise VisualDocumentError(f"{field} is required and must not be empty.", code="missing_field", path=field)
    return text


def _layer(document: VisualDocument, layer_id: Any, default: str) -> str:
    resolved = str(layer_id or default)
    document.layer(resolved)
    return resolved


def _metrics(raw: Any) -> list[Metric]:
    metrics: list[Metric] = []
    for item in list(raw or []):
        if not isinstance(item, dict):
            raise VisualDocumentError(
                "each metric must be an object with label and value.", code="invalid_metric"
            )
        metrics.append(
            Metric(
                label=_text(item.get("label"), "metric.label"),
                value=item.get("value") if item.get("value") is not None else 0,
                unit=item.get("unit"),
                format=str(item.get("format") or "raw"),  # type: ignore[arg-type]
            )
        )
    return metrics


def _provenance(
    source_table_id: Any,
    *,
    folder_id: str | None = None,
    transform_revision: Any = None,
    columns: Any = None,
    aggregation: Any = None,
    filters: Any = None,
) -> Provenance:
    table_id = str(source_table_id or "").strip()
    if not table_id:
        raise VisualDocumentError(
            "source_table_id is required: data elements must be grounded in an approved "
            "prepared table. Run a data tool first, then pass its table id.",
            code="missing_provenance",
            path="source_table_id",
        )
    parsed_filters: list[ProvenanceFilter] = []
    for item in list(filters or []):
        if not isinstance(item, dict):
            raise VisualDocumentError(
                "each filter must be an object with field, op, and value.", code="invalid_filter"
            )
        parsed_filters.append(ProvenanceFilter.model_validate(item))
    return Provenance(
        source_table_id=table_id,
        folder_id=folder_id,
        transform_revision=int(transform_revision) if transform_revision is not None else None,
        columns=[str(column) for column in (columns or [])],
        aggregation=str(aggregation or "none"),  # type: ignore[arg-type]
        filters=parsed_filters,
    )


def _trusted_prepared_source(
    folder_id: str | None,
    user_id: str | None,
    session_id: str | None,
    selected_table_id: str | None,
    requested_source_table_id: str | None,
) -> dict[str, Any]:
    """Resolve provenance from server-owned session state, never model input."""

    try:
        record, _snapshot = _selected_prepared_table(
            folder_id, user_id, session_id, selected_table_id
        )
    except WorkspaceStoreError as exc:
        raise VisualDocumentError(
            str(exc),
            code=str(getattr(exc, "code", None) or "prepared_data_unavailable"),
        ) from exc
    requested = str(requested_source_table_id or "").strip()
    resolved = str(record.get("id") or "").strip()
    if requested and requested != resolved:
        raise VisualDocumentError(
            "source_table_id must match the prepared table selected in this session.",
            code="selection_mismatch",
            path="source_table_id",
        )
    return record


def _a11y(value: Any, element: str) -> str:
    label = str(value or "").strip()
    if not label:
        raise VisualDocumentError(
            f"a11y_label is required for a {element}: grounded data needs an accessible "
            "text equivalent describing what the numbers show.",
            code="missing_a11y_label",
            path="a11y_label",
        )
    return label


def _style(raw: Any) -> StyleTokens | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise VisualDocumentError("style must be an object of style tokens.", code="invalid_style")
    unknown = set(raw) - set(StyleTokens.model_fields)
    if unknown:
        raise VisualDocumentError(
            f"unknown style tokens {sorted(unknown)}. Style is tokens only - allowed keys: "
            f"{sorted(StyleTokens.model_fields)}.",
            code="unknown_style_token",
        )
    try:
        return StyleTokens.model_validate(raw)
    except ValidationError as exc:
        raise VisualDocumentError(
            f"invalid style value: {exc.errors()[0]['msg']}", code="invalid_style"
        ) from exc


def _slot(
    document: VisualDocument,
    size: tuple[float, float],
    x: Any = None,
    y: Any = None,
) -> Rect:
    """Place a standalone widget below existing content unless told otherwise."""
    width, height = size
    if x is not None and y is not None:
        return Rect(x=float(x), y=float(y), w=width, h=height)
    bounds = content_bounds(document)
    if bounds is None:
        return Rect(x=0.0, y=0.0, w=width, h=height)
    return Rect(
        x=float(x) if x is not None else round(bounds["x"], 2),
        y=float(y) if y is not None else round(bounds["y"] + bounds["h"] + SLOT_GAP, 2),
        w=width,
        h=height,
    )


def _side_slot(document: VisualDocument, size: tuple[float, float]) -> Rect:
    """Place a widget to the right of existing content (used for legends)."""
    width, height = size
    bounds = content_bounds(document)
    if bounds is None:
        return Rect(x=0.0, y=0.0, w=width, h=height)
    return Rect(
        x=round(bounds["x"] + bounds["w"] + SLOT_GAP, 2),
        y=round(bounds["y"], 2),
        w=width,
        h=height,
    )


def _free_origin(document: VisualDocument, exclude_ids: set[str]) -> tuple[float, float]:
    """Origin for a layout pass so new geometry clears untouched content."""
    xs: list[float] = []
    bottoms: list[float] = []
    for element in document.elements:
        if element.id in exclude_ids or element.hidden:
            continue
        rect = getattr(element, "rect", None)
        if rect is None:
            continue
        xs.append(rect.x)
        bottoms.append(rect.y + rect.h)
    if not xs:
        return 0.0, 0.0
    return round(min(xs), 2), round(max(bottoms) + SLOT_GAP, 2)


def _layout_options(
    algorithm: Any,
    direction: Any = None,
    node_spacing: Any = None,
    rank_spacing: Any = None,
    columns: Any = None,
    element_ids: Any = None,
    origin: tuple[float, float] = (0.0, 0.0),
) -> LayoutOptions:
    kwargs: dict[str, Any] = {"origin_x": origin[0], "origin_y": origin[1]}
    if direction:
        kwargs["direction"] = str(direction)
    if node_spacing is not None:
        kwargs["node_spacing"] = float(node_spacing)
    if rank_spacing is not None:
        kwargs["rank_spacing"] = float(rank_spacing)
    if columns is not None:
        kwargs["columns"] = max(1, int(columns))
    if element_ids:
        kwargs["element_ids"] = [str(item) for item in element_ids]
    return LayoutOptions(str(algorithm or "layered"), **kwargs)  # type: ignore[arg-type]


def _node_ops(
    document: VisualDocument,
    nodes: Any,
    layer_id: str,
    used: set[str],
) -> tuple[list[Any], list[str], dict[str, str]]:
    """Build AddElementOps for a batch of nodes at the layout origin."""
    specs = list(nodes or [])
    if not specs:
        raise VisualDocumentError(
            "nodes must contain at least one {label, kind?} object.", code="empty_nodes"
        )
    ops: list[Any] = []
    node_ids: list[str] = []
    by_ref: dict[str, str] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            raise VisualDocumentError(
                "each node must be an object like {\"label\": \"Approve order\", \"kind\": \"task\"}.",
                code="invalid_node",
            )
        label = _text(spec.get("label"), "node.label")
        element_id = _unique_id(str(spec.get("id") or label), used)
        ops.append(
            AddElementOp(
                element=NodeElement(
                    id=element_id,
                    layer_id=layer_id,
                    node_kind=str(spec.get("kind") or spec.get("node_kind") or "task"),  # type: ignore[arg-type]
                    label=label,
                    sublabel=spec.get("sublabel"),
                    metrics=_metrics(spec.get("metrics")),
                    a11y_label=spec.get("a11y_label"),
                    rect=Rect(x=0.0, y=0.0, w=DEFAULT_NODE_W, h=DEFAULT_NODE_H),
                )
            )
        )
        node_ids.append(element_id)
        for ref in (spec.get("id"), label, _slugify(label)):
            if ref:
                by_ref.setdefault(str(ref), element_id)
    return ops, node_ids, by_ref


def _resolve_ref(ref: Any, by_ref: dict[str, str], document: VisualDocument) -> str:
    key = str(ref or "").strip()
    if not key:
        raise VisualDocumentError(
            "edge source and target are required.", code="invalid_edge", path="source"
        )
    if key in by_ref:
        return by_ref[key]
    slug = _slugify(key)
    if slug in by_ref:
        return by_ref[slug]
    if document.has_element(key):
        return key
    raise VisualDocumentError(
        f"edge endpoint '{key}' does not match any node label, node id, or existing element.",
        code="unknown_node_ref",
        path=key,
    )


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@_guarded
def create_canvas(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    title: str = "",
    project_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    canvas_title = _text(title, "title")
    result = _call_store(
        create_document,
        folder_id=folder_id,
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        title=canvas_title,
        author=user_id,
        created_by=user_id,
    )
    document = _as_document(_split(result)[0])
    return {
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "title": document.metadata.title,
        "element_ids": [],
        "layers": [{"id": layer.id, "name": layer.name, "kind": layer.kind} for layer in document.layers],
        "artifact": {
            "artifact_type": "visual_document",
            "document_id": document.metadata.id,
            "revision": document.metadata.revision,
            "title": document.metadata.title,
            "label": "canvas_create",
        },
        "readability": check_readability(document),
        "message": "Empty canvas created. Add elements, then call canvas_apply_layout before canvas_inspect.",
    }


def _document_row(item: Any) -> dict[str, Any]:
    if isinstance(item, VisualDocument):
        return {
            "document_id": item.metadata.id,
            "title": item.metadata.title,
            "revision": item.metadata.revision,
            "session_id": item.metadata.session_id,
            "updated_at": item.metadata.updated_at,
            "element_count": len(item.elements),
        }
    if isinstance(item, dict):
        return {
            "document_id": item.get("document_id") or item.get("id"),
            "title": item.get("title"),
            "revision": item.get("revision"),
            "session_id": item.get("session_id"),
            "updated_at": item.get("updated_at"),
            "element_count": item.get("element_count"),
        }
    return {"document_id": str(item)}


@_guarded
def list_canvases(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    result = _call_store(
        list_documents, folder_id=folder_id, user_id=user_id, session_id=session_id
    )
    items = result.get("documents") if isinstance(result, dict) else result
    rows = [_document_row(item) for item in list(items or [])]
    return {"folder_id": folder_id, "documents": rows, "count": len(rows)}


@_guarded
def inspect_canvas(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    return {
        "document_id": document.metadata.id,
        "title": document.metadata.title,
        "revision": document.metadata.revision,
        "outline": document.outline(),
        "layers": [
            {
                "id": layer.id,
                "name": layer.name,
                "kind": layer.kind,
                "index": layer.index,
                "visible": layer.visible,
                "locked": layer.locked,
            }
            for layer in sorted(document.layers, key=lambda item: item.index)
        ],
        "groups": [
            {"id": group.id, "name": group.name, "element_ids": list(group.element_ids)}
            for group in document.groups
        ],
        "selected_ids": list(document.viewport.selected_ids),
        "bounds": content_bounds(document),
        "readability": check_readability(document),
    }


@_guarded
def summarize_canvas(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    return summarize(document)


@_guarded
def find_overlaps(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    return {"document_id": document.metadata.id, "revision": document.metadata.revision, **check_readability(document)}


# ---------------------------------------------------------------------------
# Element tools
# ---------------------------------------------------------------------------


@_guarded
def add_node(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    node_kind: str = "task",
    label: str = "",
    sublabel: str | None = None,
    metrics: Any = None,
    layer_id: str | None = None,
    element_id: str | None = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_NODE_LAYER)
    used = {element.id for element in document.elements}
    node_label = _text(label, "label")
    node_id = _unique_id(str(element_id or node_label), used)
    node_style = _style(style)
    node = NodeElement(
        id=node_id,
        layer_id=layer,
        node_kind=str(node_kind or "task"),  # type: ignore[arg-type]
        label=node_label,
        sublabel=sublabel,
        metrics=_metrics(metrics),
        rect=Rect(x=0.0, y=0.0, w=DEFAULT_NODE_W, h=DEFAULT_NODE_H),
        **({"style": node_style} if node_style else {}),
    )
    document, commit = _commit(document_id, [AddElementOp(element=node)], user_id, "canvas_add_node")
    return _patch_result(
        document,
        [commit],
        "canvas_add_node",
        [node_id],
        message="Node added at (0,0). Call canvas_apply_layout to compute readable geometry.",
    )


@_guarded
def add_edge(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    source_id: str = "",
    target_id: str = "",
    edge_kind: str = "sequence",
    label: str | None = None,
    marker: str = "arrow",
    routing: str | None = None,
    layer_id: str | None = None,
    metrics: Any = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_NODE_LAYER)
    source = _text(source_id, "source_id")
    target = _text(target_id, "target_id")
    document.element(source)
    document.element(target)
    edge_style = _style(style)
    edge = EdgeElement(
        id=new_id("edge"),
        layer_id=layer,
        source_id=source,
        target_id=target,
        edge_kind=str(edge_kind or "sequence"),  # type: ignore[arg-type]
        label=label,
        marker=str(marker or "arrow"),  # type: ignore[arg-type]
        metrics=_metrics(metrics),
        **({"routing": str(routing)} if routing else {}),
        **({"style": edge_style} if edge_style else {}),
    )
    document, commit = _commit(document_id, [AddElementOp(element=edge)], user_id, "canvas_add_edge")
    return _patch_result(document, [commit], "canvas_add_edge", [edge.id])


@_guarded
def add_text(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    text: str = "",
    role: str = "note",
    x: Any = None,
    y: Any = None,
    width: Any = None,
    height: Any = None,
    layer_id: str | None = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_ANNOTATION_LAYER)
    body = _text(text, "text")
    size = (float(width or TEXT_SIZE[0]), float(height or TEXT_SIZE[1]))
    element_style = _style(style)
    element = TextElement(
        id=new_id("text"),
        layer_id=layer,
        text=body,
        role=str(role or "note"),  # type: ignore[arg-type]
        rect=_slot(document, size, x, y),
        **({"style": element_style} if element_style else {}),
    )
    document, commit = _commit(document_id, [AddElementOp(element=element)], user_id, "canvas_add_text")
    return _patch_result(document, [commit], "canvas_add_text", [element.id])


@_guarded
def add_shape(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    shape: str = "rect",
    text: str | None = None,
    x: Any = None,
    y: Any = None,
    width: Any = None,
    height: Any = None,
    layer_id: str | None = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_NODE_LAYER)
    size = (float(width or SHAPE_SIZE[0]), float(height or SHAPE_SIZE[1]))
    element_style = _style(style)
    element = ShapeElement(
        id=new_id("shape"),
        layer_id=layer,
        shape=str(shape or "rect"),  # type: ignore[arg-type]
        text=text,
        rect=_slot(document, size, x, y),
        **({"style": element_style} if element_style else {}),
    )
    document, commit = _commit(document_id, [AddElementOp(element=element)], user_id, "canvas_add_shape")
    return _patch_result(document, [commit], "canvas_add_shape", [element.id])


def _legend_entries(raw: Any) -> list[LegendEntry]:
    entries: list[LegendEntry] = []
    for index, item in enumerate(list(raw or [])):
        if not isinstance(item, dict):
            raise VisualDocumentError(
                "each legend entry must be an object like {\"label\": \"Happy path\", \"swatch\": \"series-1\"}.",
                code="invalid_legend_entry",
            )
        entries.append(
            LegendEntry(
                label=_text(item.get("label"), "entry.label"),
                swatch=str(item.get("swatch") or SWATCH_TOKENS[index % len(SWATCH_TOKENS)]),  # type: ignore[arg-type]
                shape=str(item.get("shape") or "square"),  # type: ignore[arg-type]
            )
        )
    if not entries:
        raise VisualDocumentError(
            "entries must contain at least one legend entry.", code="empty_legend"
        )
    return entries


@_guarded
def add_path(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    points: Any = None,
    tool: str = "pen",
    closed: bool = False,
    smoothing: Any = 0.5,
    layer_id: str | None = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_FREEFORM_LAYER)
    parsed: list[Point] = []
    for item in list(points or []):
        if isinstance(item, dict):
            raw_x, raw_y = item.get("x"), item.get("y")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            raw_x, raw_y = item
        else:
            raise VisualDocumentError(
                "Each path point must be {x, y} or a two-number array.",
                code="invalid_path_point",
                path="points",
            )
        try:
            parsed.append(Point(x=float(raw_x), y=float(raw_y)))
        except (TypeError, ValueError, ValidationError) as exc:
            raise VisualDocumentError(
                "Path coordinates must be finite numbers inside the canvas bounds.",
                code="invalid_path_point",
                path="points",
            ) from exc
    if len(parsed) < 2:
        raise VisualDocumentError(
            "A path needs at least two points.", code="path_too_short", path="points"
        )
    element = PathElement(
        id=new_id("path"),
        layer_id=layer,
        points=parsed,
        tool=str(tool or "pen"),  # type: ignore[arg-type]
        closed=bool(closed),
        smoothing=float(smoothing if smoothing is not None else 0.5),
        style=_style(style) or StyleTokens(),
    )
    document, commit = _commit(
        document_id, [AddElementOp(element=element)], user_id, "canvas_add_path"
    )
    return _patch_result(
        document, [commit], "canvas_add_path", [element.id], bounds=element.bbox.model_dump()
    )


@_guarded
def add_legend(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    entries: Any = None,
    title: str | None = None,
    orientation: str = "vertical",
    x: Any = None,
    y: Any = None,
    layer_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_ANNOTATION_LAYER)
    parsed = _legend_entries(entries)
    height = max(48.0, LEGEND_ROW * len(parsed) + 40.0)
    element = LegendElement(
        id=new_id("legend"),
        layer_id=layer,
        title=title,
        entries=parsed,
        orientation=str(orientation or "vertical"),  # type: ignore[arg-type]
        rect=_slot(document, (LEGEND_WIDTH, height), x, y) if (x is not None and y is not None) else _side_slot(document, (LEGEND_WIDTH, height)),
    )
    document, commit = _commit(document_id, [AddElementOp(element=element)], user_id, "canvas_add_legend")
    return _patch_result(document, [commit], "canvas_add_legend", [element.id])


# ---------------------------------------------------------------------------
# Flagship composite tools
# ---------------------------------------------------------------------------


@_guarded
def create_process_map(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    nodes: Any = None,
    edges: Any = None,
    title: str | None = None,
    direction: str = "right",
    layout: str = "layered",
    node_spacing: Any = None,
    rank_spacing: Any = None,
    layer_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_NODE_LAYER)
    used = {element.id for element in document.elements}
    ops, node_ids, by_ref = _node_ops(document, nodes, layer, used)

    edge_ids: list[str] = []
    for spec in list(edges or []):
        if not isinstance(spec, dict):
            raise VisualDocumentError(
                "each edge must be an object like {\"source\": \"Intake\", \"target\": \"Review\"}.",
                code="invalid_edge",
            )
        edge = EdgeElement(
            id=new_id("edge"),
            layer_id=layer,
            source_id=_resolve_ref(spec.get("source") or spec.get("source_id"), by_ref, document),
            target_id=_resolve_ref(spec.get("target") or spec.get("target_id"), by_ref, document),
            edge_kind=str(spec.get("kind") or spec.get("edge_kind") or "sequence"),  # type: ignore[arg-type]
            label=spec.get("label"),
            marker=str(spec.get("marker") or "arrow"),  # type: ignore[arg-type]
            metrics=_metrics(spec.get("metrics")),
        )
        ops.append(AddElementOp(element=edge))
        edge_ids.append(edge.id)

    if title:
        ops.append(SetTitleOp(title=_text(title, "title")))

    document, content_commit = _commit(document_id, ops, user_id, "canvas_create_process_map")
    commits = [content_commit]

    options = _layout_options(
        layout or "layered",
        direction=direction,
        node_spacing=node_spacing,
        rank_spacing=rank_spacing,
        element_ids=node_ids,
        origin=_free_origin(document, set(node_ids)),
    )
    geometry = layout_ops(document, options)
    if geometry:
        document, layout_commit = _commit(
            document_id, geometry, user_id, "canvas_create_process_map:layout"
        )
        commits.append(layout_commit)

    return _patch_result(
        document,
        commits,
        "canvas_create_process_map",
        node_ids + edge_ids,
        node_ids=node_ids,
        edge_ids=edge_ids,
        layout={"algorithm": options.algorithm, "direction": options.direction},
    )


@_guarded
def create_variant_paths(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    nodes: Any = None,
    variants: Any = None,
    title: str | None = None,
    direction: str = "right",
    layout: str = "layered",
    legend_title: str | None = None,
    layer_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_NODE_LAYER)
    used = {element.id for element in document.elements}
    ops, node_ids, by_ref = _node_ops(document, nodes, layer, used)

    variant_specs = list(variants or [])
    if not variant_specs:
        raise VisualDocumentError(
            "variants must contain at least one {label, path: [node refs], case_count?, percentage?} object.",
            code="empty_variants",
        )

    edge_ids: list[str] = []
    legend_rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for index, spec in enumerate(variant_specs):
        if not isinstance(spec, dict):
            raise VisualDocumentError(
                "each variant must be an object with a label and a path of node references.",
                code="invalid_variant",
            )
        variant_label = _text(spec.get("label"), "variant.label")
        path = [str(item) for item in list(spec.get("path") or [])]
        if len(path) < 2:
            raise VisualDocumentError(
                f"variant '{variant_label}' needs a path of at least two node references.",
                code="invalid_variant_path",
            )
        case_count = spec.get("case_count")
        percentage = spec.get("percentage")
        emphasis = str(spec.get("emphasis") or ("highlight" if index == 0 else "none"))
        if emphasis not in EMPHASIS_TOKENS:
            raise VisualDocumentError(
                f"emphasis must be one of {EMPHASIS_TOKENS}.", code="invalid_style", path="emphasis"
            )
        stroke = STROKE_SERIES[index % len(STROKE_SERIES)]
        dash = "solid" if index == 0 else "dashed"
        detail = variant_label
        if case_count is not None:
            detail = f"{detail} - {case_count} cases"
        if percentage is not None:
            detail = f"{detail} ({percentage}%)"

        variant_edges: list[str] = []
        for position in range(len(path) - 1):
            edge = EdgeElement(
                id=new_id("edge"),
                layer_id=layer,
                source_id=_resolve_ref(path[position], by_ref, document),
                target_id=_resolve_ref(path[position + 1], by_ref, document),
                edge_kind=str(spec.get("kind") or spec.get("edge_kind") or "sequence"),  # type: ignore[arg-type]
                label=detail if position == 0 else None,
                marker="arrow",
                style=StyleTokens(emphasis=emphasis, stroke=stroke, stroke_dash=dash),  # type: ignore[arg-type]
                metrics=_metrics(
                    [{"label": "cases", "value": case_count, "format": "integer"}]
                    if case_count is not None
                    else None
                ),
            )
            ops.append(AddElementOp(element=edge))
            variant_edges.append(edge.id)
        edge_ids.extend(variant_edges)
        legend_rows.append(
            {
                "label": detail,
                "swatch": str(spec.get("swatch") or SWATCH_TOKENS[index % len(SWATCH_TOKENS)]),
                "shape": "line" if index == 0 else "dashed-line",
            }
        )
        summary.append(
            {
                "label": variant_label,
                "path": path,
                "case_count": case_count,
                "percentage": percentage,
                "emphasis": emphasis,
                "edge_ids": variant_edges,
            }
        )

    if title:
        ops.append(SetTitleOp(title=_text(title, "title")))

    document, content_commit = _commit(document_id, ops, user_id, "canvas_create_variant_paths")
    commits = [content_commit]

    options = _layout_options(
        layout or "layered",
        direction=direction,
        element_ids=node_ids,
        origin=_free_origin(document, set(node_ids)),
    )
    geometry = layout_ops(document, options)
    if geometry:
        document, layout_commit = _commit(
            document_id, geometry, user_id, "canvas_create_variant_paths:layout"
        )
        commits.append(layout_commit)

    entries = _legend_entries(legend_rows)
    legend = LegendElement(
        id=new_id("legend"),
        layer_id=DEFAULT_ANNOTATION_LAYER,
        title=legend_title or "Variants",
        entries=entries,
        orientation="vertical",
        rect=_side_slot(document, (LEGEND_WIDTH, max(48.0, LEGEND_ROW * len(entries) + 40.0))),
    )
    group_ops: list[Any] = [AddElementOp(element=legend)]
    document, legend_commit = _commit(
        document_id, group_ops, user_id, "canvas_create_variant_paths:legend"
    )
    commits.append(legend_commit)

    return _patch_result(
        document,
        commits,
        "canvas_create_variant_paths",
        node_ids + edge_ids + [legend.id],
        node_ids=node_ids,
        edge_ids=edge_ids,
        legend_id=legend.id,
        variants=summary,
    )


@_guarded
def highlight_path(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    emphasis: str = "highlight",
    dim_others: bool = False,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if not ids:
        raise VisualDocumentError(
            "element_ids must list the elements to emphasise. Use canvas_inspect to read ids.",
            code="empty_selection",
        )
    token = str(emphasis or "highlight")
    if token not in EMPHASIS_TOKENS:
        raise VisualDocumentError(
            f"emphasis must be one of {EMPHASIS_TOKENS}.", code="invalid_style", path="emphasis"
        )
    for element_id in ids:
        document.element(element_id)
    ops: list[Any] = [SetStyleOp(element_ids=ids, style={"emphasis": token})]
    if dim_others:
        selected = set(ids)
        others = [element.id for element in document.elements if element.id not in selected]
        if others:
            ops.append(SetStyleOp(element_ids=others, style={"emphasis": "dim"}))
    document, commit = _commit(document_id, ops, user_id, "canvas_highlight_path")
    return _patch_result(document, [commit], "canvas_highlight_path", ids, emphasis=token)


# ---------------------------------------------------------------------------
# Grounded data elements
# ---------------------------------------------------------------------------


@_guarded
def create_chart(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    chart_type: str = "bar",
    title: str = "",
    x_field: str = "",
    y_fields: Any = None,
    source_table_id: str = "",
    transform_revision: Any = None,
    aggregation: str | None = None,
    filters: Any = None,
    a11y_label: str = "",
    series_field: str | None = None,
    stacked: bool = False,
    row_limit: Any = None,
    x: Any = None,
    y: Any = None,
    width: Any = None,
    height: Any = None,
    layer_id: str | None = None,
    selected_table_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_DATA_LAYER)
    fields = [str(field) for field in list(y_fields or []) if str(field).strip()]
    if not fields:
        raise VisualDocumentError(
            "y_fields must list at least one measure column.", code="missing_y_fields", path="y_fields"
        )

    resolved_source = source_table_id
    resolved_revision = transform_revision
    resolved_aggregation = str(aggregation or "sum").lower()
    chart_data: list[dict[str, Any]] = []
    if selected_table_id:
        record = _trusted_prepared_source(
            folder_id, user_id, session_id, selected_table_id, source_table_id
        )
        if filters:
            raise VisualDocumentError(
                "Apply filters in Prepare before visualizing so the stored table revision "
                "exactly matches the displayed rows.",
                code="filters_require_prepared_table",
                path="filters",
            )
        capped = max(1, min(int(row_limit or 100), 200))
        for field in fields:
            try:
                aggregated = aggregate_prepared_table(
                    folder_id=folder_id,
                    user_id=user_id,
                    session_id=session_id,
                    selected_table_id=str(record["id"]),
                    group_by=str(x_field),
                    value_field=field,
                    aggregation=resolved_aggregation,
                    limit=capped,
                )
            except WorkspaceStoreError as exc:
                raise VisualDocumentError(
                    str(exc),
                    code=str(getattr(exc, "code", None) or "chart_query_failed"),
                ) from exc
            if aggregated.get("error"):
                raise VisualDocumentError(str(aggregated["error"]), code="chart_query_failed")
            for row in list(aggregated.get("rows") or []):
                try:
                    numeric_value = float(row.get("value") or 0)
                except (TypeError, ValueError) as exc:
                    raise VisualDocumentError(
                        "The prepared query returned a non-numeric chart value.",
                        code="chart_query_failed",
                    ) from exc
                chart_data.append(
                    {
                        "label": str(row.get("label") or ""),
                        "value": numeric_value,
                        "series": field if len(fields) > 1 else None,
                    }
                )
        resolved_source = str(record["id"])
        resolved_revision = int(record.get("revision") or 0)

    provenance = _provenance(
        resolved_source,
        folder_id=folder_id,
        transform_revision=resolved_revision,
        columns=[str(x_field)] + fields if x_field else fields,
        aggregation=resolved_aggregation,
        filters=filters,
    )
    size = (float(width or CHART_SIZE[0]), float(height or CHART_SIZE[1]))
    element = ChartElement(
        id=new_id("chart"),
        layer_id=layer,
        chart_type=str(chart_type or "bar"),  # type: ignore[arg-type]
        title=_text(title, "title"),
        x_field=_text(x_field, "x_field"),
        y_fields=fields,
        data=chart_data,
        series_field=series_field,
        stacked=bool(stacked),
        a11y_label=_a11y(a11y_label, "chart"),
        provenance=provenance,
        rect=_slot(document, size, x, y),
        **({"row_limit": max(1, int(row_limit))} if row_limit is not None else {}),
    )
    document, commit = _commit(
        document_id, [AddElementOp(element=element)], user_id, "canvas_create_chart"
    )
    return _patch_result(
        document,
        [commit],
        "canvas_create_chart",
        [element.id],
        source_table_id=provenance.source_table_id,
    )

@_guarded
def create_kpi(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    label: str = "",
    value: Any = None,
    value_field: str = "",
    unit: str | None = None,
    format: str = "raw",
    source_table_id: str = "",
    transform_revision: Any = None,
    aggregation: str | None = None,
    filters: Any = None,
    a11y_label: str = "",
    delta: Any = None,
    trend: str = "none",
    x: Any = None,
    y: Any = None,
    layer_id: str | None = None,
    selected_table_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_DATA_LAYER)
    kpi_label = _text(label, "label")
    accessible_label = _a11y(a11y_label, "KPI")
    resolved_source = source_table_id
    resolved_revision = transform_revision
    resolved_value = value
    resolved_aggregation = str(aggregation or "count").lower()

    if selected_table_id:
        record = _trusted_prepared_source(
            folder_id, user_id, session_id, selected_table_id, source_table_id
        )
        if filters or delta is not None:
            raise VisualDocumentError(
                "Filtered or comparison KPIs must first be materialized as a prepared table, "
                "then selected before adding the KPI.",
                code="kpi_requires_prepared_table",
            )
        try:
            preview = create_prepared_kpi(
                folder_id=folder_id,
                user_id=user_id,
                session_id=session_id,
                selected_table_id=str(record["id"]),
                title=kpi_label,
                value_field=str(value_field or ""),
                aggregation=resolved_aggregation,
            )
        except WorkspaceStoreError as exc:
            raise VisualDocumentError(
                str(exc),
                code=str(getattr(exc, "code", None) or "kpi_query_failed"),
            ) from exc
        if preview.get("error"):
            raise VisualDocumentError(str(preview["error"]), code="kpi_query_failed")
        points = ((preview.get("artifact") or {}).get("data") or [])
        resolved_value = points[0].get("value") if points else 0
        resolved_source = str(record["id"])
        resolved_revision = int(record.get("revision") or 0)
        trend = "none"

    if resolved_value is None:
        raise VisualDocumentError(
            "value is required: a KPI must show a number computed from the source table.",
            code="missing_value",
            path="value",
        )
    provenance = _provenance(
        resolved_source,
        folder_id=folder_id,
        transform_revision=resolved_revision,
        columns=[value_field] if value_field else [],
        aggregation=resolved_aggregation,
        filters=filters,
    )
    metric = Metric(
        label=kpi_label,
        value=resolved_value,
        unit=unit,
        format=str(format or "raw"),  # type: ignore[arg-type]
    )
    delta_metric = _metrics([delta])[0] if isinstance(delta, dict) else None
    element = KpiElement(
        id=new_id("kpi"),
        layer_id=layer,
        label=kpi_label,
        metric=metric,
        delta=delta_metric,
        trend=str(trend or "none"),  # type: ignore[arg-type]
        a11y_label=accessible_label,
        provenance=provenance,
        rect=_slot(document, KPI_SIZE, x, y),
    )
    document, commit = _commit(
        document_id, [AddElementOp(element=element)], user_id, "canvas_create_kpi"
    )
    return _patch_result(
        document,
        [commit],
        "canvas_create_kpi",
        [element.id],
        source_table_id=provenance.source_table_id,
    )

@_guarded
def create_gantt(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    title: str = "",
    bars: Any = None,
    source_table_id: str = "",
    transform_revision: Any = None,
    aggregation: str | None = None,
    filters: Any = None,
    a11y_label: str = "",
    time_unit: str = "day",
    x: Any = None,
    y: Any = None,
    width: Any = None,
    height: Any = None,
    layer_id: str | None = None,
    selected_table_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    layer = _layer(document, layer_id, DEFAULT_DATA_LAYER)
    specs = list(bars or [])
    if not specs:
        raise VisualDocumentError(
            "bars must contain at least one {label, lane, start, end} object.",
            code="empty_bars",
            path="bars",
        )
    used_bar_ids: set[str] = set()
    parsed: list[GanttBar] = []
    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise VisualDocumentError(
                "each bar must be an object like {\"label\": \"Design\", \"lane\": \"Team A\", "
                "\"start\": \"2026-01-05\", \"end\": \"2026-01-19\"}.",
                code="invalid_bar",
            )
        bar_label = _text(spec.get("label"), "bar.label")
        parsed.append(
            GanttBar(
                id=_unique_id(str(spec.get("id") or bar_label), used_bar_ids),
                label=bar_label,
                lane=_text(spec.get("lane"), "bar.lane"),
                start=_text(spec.get("start"), "bar.start"),
                end=_text(spec.get("end"), "bar.end"),
                progress=float(spec["progress"]) if spec.get("progress") is not None else None,
                swatch=str(spec.get("swatch") or SWATCH_TOKENS[index % len(SWATCH_TOKENS)]),  # type: ignore[arg-type]
                depends_on=[str(item) for item in list(spec.get("depends_on") or [])],
            )
        )
    if selected_table_id:
        record = _trusted_prepared_source(
            folder_id, user_id, session_id, selected_table_id, source_table_id
        )
        source_table_id = str(record["id"])
        transform_revision = int(record.get("revision") or 0)

    provenance = _provenance(
        source_table_id,
        folder_id=folder_id,
        transform_revision=transform_revision,
        aggregation=aggregation,
        filters=filters,
    )
    size = (float(width or GANTT_SIZE[0]), float(height or GANTT_SIZE[1]))
    element = GanttElement(
        id=new_id("gantt"),
        layer_id=layer,
        title=_text(title, "title"),
        bars=parsed,
        time_unit=str(time_unit or "day"),  # type: ignore[arg-type]
        a11y_label=_a11y(a11y_label, "gantt chart"),
        provenance=provenance,
        rect=_slot(document, size, x, y),
    )
    document, commit = _commit(document_id, [AddElementOp(element=element)], user_id, "canvas_create_gantt")
    return _patch_result(
        document,
        [commit],
        "canvas_create_gantt",
        [element.id],
        source_table_id=provenance.source_table_id,
    )


# ---------------------------------------------------------------------------
# Geometry tools - all geometry comes from shared.visual_layout
# ---------------------------------------------------------------------------


@_guarded
def apply_layout(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    algorithm: str = "layered",
    direction: str | None = None,
    node_spacing: Any = None,
    rank_spacing: Any = None,
    columns: Any = None,
    element_ids: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    options = _layout_options(
        algorithm,
        direction=direction,
        node_spacing=node_spacing,
        rank_spacing=rank_spacing,
        columns=columns,
        element_ids=element_ids,
    )
    ops = layout_ops(document, options)
    if not ops:
        return _noop_result(document, "canvas_apply_layout", "Layout already matches the engine output.")
    document, commit = _commit(document_id, ops, user_id, "canvas_apply_layout")
    laid_out = sorted(compute_layout(document, options))
    return _patch_result(
        document,
        [commit],
        "canvas_apply_layout",
        laid_out,
        layout={"algorithm": options.algorithm, "direction": options.direction},
    )


@_guarded
def align_elements(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    axis: str = "left",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if len(ids) < 2:
        raise VisualDocumentError(
            "align needs at least two element_ids.", code="not_enough_elements", path="element_ids"
        )
    if axis not in ALIGN_AXES:
        raise VisualDocumentError(
            f"axis must be one of {ALIGN_AXES}.", code="unknown_axis", path="axis"
        )
    ops = align_ops(document, ids, axis)  # type: ignore[arg-type]
    if not ops:
        return _noop_result(document, "canvas_align", "Elements are already aligned.")
    document, commit = _commit(document_id, ops, user_id, "canvas_align")
    return _patch_result(document, [commit], "canvas_align", ids, axis=axis)


@_guarded
def distribute_elements(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    axis: str = "x",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if len(ids) < 3:
        raise VisualDocumentError(
            "distribute needs at least three element_ids.",
            code="not_enough_elements",
            path="element_ids",
        )
    if axis not in DISTRIBUTE_AXES:
        raise VisualDocumentError(
            f"axis must be one of {DISTRIBUTE_AXES}.", code="unknown_axis", path="axis"
        )
    ops = distribute_ops(document, ids, axis)  # type: ignore[arg-type]
    if not ops:
        return _noop_result(document, "canvas_distribute", "Elements are already evenly spaced.")
    document, commit = _commit(document_id, ops, user_id, "canvas_distribute")
    return _patch_result(document, [commit], "canvas_distribute", ids, axis=axis)


@_guarded
def move_elements(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    dx: Any = 0.0,
    dy: Any = 0.0,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if not ids:
        raise VisualDocumentError(
            "element_ids must not be empty.", code="empty_selection", path="element_ids"
        )
    op = MoveElementsOp(element_ids=ids, dx=float(dx or 0.0), dy=float(dy or 0.0))
    document, commit = _commit(document_id, [op], user_id, "canvas_move_elements")
    return _patch_result(document, [commit], "canvas_move_elements", ids)


@_guarded
def resize_element(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_id: str = "",
    width: Any = None,
    height: Any = None,
    x: Any = None,
    y: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    target = document.element(_text(element_id, "element_id"))
    current = getattr(target, "rect", None)
    if current is None:
        raise VisualDocumentError(
            f"element type '{target.type}' has no resizable rect.",
            code="not_resizable",
            path=target.id,
        )
    rect = Rect(
        x=float(x) if x is not None else current.x,
        y=float(y) if y is not None else current.y,
        w=float(width) if width is not None else current.w,
        h=float(height) if height is not None else current.h,
    )
    op = ResizeElementOp(element_id=target.id, rect=rect)
    document, commit = _commit(document_id, [op], user_id, "canvas_resize_element")
    return _patch_result(document, [commit], "canvas_resize_element", [target.id])


@_guarded
def update_style(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    style: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if not ids:
        raise VisualDocumentError(
            "element_ids must not be empty.", code="empty_selection", path="element_ids"
        )
    if not isinstance(style, dict) or not style:
        raise VisualDocumentError(
            f"style must be a non-empty object of style tokens ({sorted(StyleTokens.model_fields)}).",
            code="invalid_style",
            path="style",
        )
    op = SetStyleOp(element_ids=ids, style=dict(style))
    document, commit = _commit(document_id, [op], user_id, "canvas_update_style")
    return _patch_result(document, [commit], "canvas_update_style", ids)


@_guarded
def delete_elements(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if not ids:
        raise VisualDocumentError(
            "element_ids must not be empty.", code="empty_selection", path="element_ids"
        )
    for element_id in ids:
        document.element(element_id)
    # Edges first, so removing a node never trips the element_in_use guard.
    ordered = sorted(ids, key=lambda item: (0 if document.element(item).type == "edge" else 1, item))
    ops = [RemoveElementOp(element_id=element_id) for element_id in ordered]
    document, commit = _commit(document_id, ops, user_id, "canvas_delete_elements")
    return _patch_result(document, [commit], "canvas_delete_elements", ordered)


@_guarded
def group_elements(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    element_ids: Any = None,
    name: str = "",
    **_: Any,
) -> dict[str, Any]:
    document = _load(document_id, folder_id, user_id)
    ids = [str(item) for item in list(element_ids or [])]
    if len(ids) < 2:
        raise VisualDocumentError(
            "grouping needs at least two element_ids.", code="not_enough_elements", path="element_ids"
        )
    for element_id in ids:
        document.element(element_id)
    group = Group(id=new_id("grp"), name=_text(name, "name"), element_ids=ids)
    document, commit = _commit(
        document_id, [CreateGroupOp(group=group)], user_id, "canvas_group_elements"
    )
    return _patch_result(document, [commit], "canvas_group_elements", ids, group_id=group.id)


@_guarded
def undo_canvas(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    if not document_id or not str(document_id).strip():
        raise VisualDocumentError("document_id is required.", code="missing_document_id")
    _load(document_id, folder_id, user_id)
    result = _call_store(
        undo_document,
        str(document_id),
        author=user_id or "agent",
        folder_id=folder_id,
        user_id=user_id,
    )
    document_like, commit_like = _split(result)
    document = _as_document(document_like)
    commit = _as_commit(commit_like)
    if commit is None:
        return _noop_result(document, "canvas_undo", "There is nothing left to undo on this canvas.")
    return {
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "element_ids": [],
        "undone": commit.label,
        "artifact": {
            "artifact_type": "visual_patch",
            "document_id": document.metadata.id,
            "revision": document.metadata.revision,
            "commit": commit.model_dump(mode="json"),
            "label": "canvas_undo",
        },
        "readability": check_readability(document),
    }


@_guarded
def redo_canvas(
    folder_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    document_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    if not document_id or not str(document_id).strip():
        raise VisualDocumentError("document_id is required.", code="missing_document_id")
    _load(document_id, folder_id, user_id)
    result = _call_store(
        redo_document,
        str(document_id),
        author=user_id or "agent",
        folder_id=folder_id,
        user_id=user_id,
    )
    document_like, commit_like = _split(result)
    document = _as_document(document_like)
    commit = _as_commit(commit_like)
    if commit is None:
        return _noop_result(document, "canvas_redo", "There is nothing left to redo on this canvas.")
    return {
        "document_id": document.metadata.id,
        "revision": document.metadata.revision,
        "element_ids": [],
        "redone": commit.label,
        "artifact": {
            "artifact_type": "visual_patch",
            "document_id": document.metadata.id,
            "revision": document.metadata.revision,
            "commit": commit.model_dump(mode="json"),
            "label": "canvas_redo",
        },
        "readability": check_readability(document),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ORDER = (
    "Call order: canvas_create -> add elements (canvas_add_node / canvas_add_edge / "
    "canvas_create_chart / ...) -> canvas_apply_layout -> canvas_inspect."
)

_NODE_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Optional stable id; slugified from label when omitted."},
        "label": {"type": "string", "description": "Visible node label."},
        "kind": {"type": "string", "enum": NODE_KINDS, "description": "Semantic node kind."},
        "sublabel": {"type": "string"},
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": ["string", "number"]},
                    "unit": {"type": "string"},
                    "format": {"type": "string", "enum": METRIC_FORMATS},
                },
                "required": ["label", "value"],
            },
        },
    },
    "required": ["label"],
}

_EDGE_ITEM = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Node id or label from nodes, or an existing element id."},
        "target": {"type": "string", "description": "Node id or label from nodes, or an existing element id."},
        "label": {"type": "string"},
        "kind": {"type": "string", "enum": EDGE_KINDS},
        "marker": {"type": "string", "enum": EDGE_MARKERS},
    },
    "required": ["source", "target"],
}

_VARIANT_ITEM = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Variant name, e.g. 'Happy path'."},
        "path": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered node ids/labels traversed by this variant (at least two).",
        },
        "case_count": {"type": "integer", "description": "Cases that followed this variant."},
        "percentage": {"type": "number", "description": "Share of cases, 0-100."},
        "emphasis": {"type": "string", "enum": EMPHASIS_TOKENS, "description": "Defaults to highlight for the first variant."},
        "swatch": {"type": "string", "enum": SWATCH_TOKENS, "description": "Legend swatch token."},
        "kind": {"type": "string", "enum": EDGE_KINDS},
    },
    "required": ["label", "path"],
}

_LEGEND_ITEM = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "swatch": {"type": "string", "enum": SWATCH_TOKENS},
        "shape": {"type": "string", "enum": LEGEND_SHAPES},
    },
    "required": ["label"],
}

_FILTERS = {
    "type": "array",
    "description": "Provenance filters describing exactly which rows the visual covers.",
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "op": {"type": "string", "enum": FILTER_OPS},
            "value": {},
        },
        "required": ["field", "op"],
    },
}

_METRIC_LIST = {
    "type": "array",
    "description": "Grounded numbers rendered inside the element.",
    "items": {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "value": {"type": ["string", "number"]},
            "unit": {"type": "string"},
            "format": {"type": "string", "enum": METRIC_FORMATS},
        },
        "required": ["label", "value"],
    },
}

_LAYER = {"type": "string", "enum": LAYER_IDS, "description": "Target layer id."}
_ELEMENT_IDS = {"type": "array", "items": {"type": "string"}, "description": "Element ids from canvas_inspect."}

CANVAS_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "canvas_create",
        "Create a visual canvas",
        "Create an empty visual document for this folder/session and return its document_id and revision. "
        "Always the first canvas call; every other canvas tool needs the document_id. " + _ORDER,
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "title": {"type": "string", "description": "Canvas title shown to the user."},
            },
            ["folder_id", "session_id", "title"],
        ),
        create_canvas,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_list",
        "List visual canvases",
        "List the visual documents that already exist in this folder (id, title, revision, element count). "
        "Use it to reuse a canvas instead of creating a duplicate.",
        _obj({"folder_id": FOLDER, "session_id": SESSION}, ["folder_id"]),
        list_canvases,
        READ_ONLY,
        SURFACES,
    ),
    ToolSpec(
        "canvas_inspect",
        "Inspect a canvas",
        "Read-before-write tool: return the full semantic outline (every element id, type, label, and data source), "
        "the layer stack, groups, current selection, content bounds, revision, and readability report. "
        "Call this before editing existing elements so you use real ids instead of guesses.",
        _obj({"folder_id": FOLDER, "session_id": SESSION, "document_id": DOCUMENT}, ["folder_id", "document_id"]),
        inspect_canvas,
        READ_ONLY,
        SURFACES,
    ),
    ToolSpec(
        "canvas_summarize",
        "Summarize a canvas",
        "Compact canvas summary: element counts by type, layers, groups, source tables, bounds, and readability. "
        "Cheaper than canvas_inspect when you only need to know what the canvas contains.",
        _obj({"folder_id": FOLDER, "session_id": SESSION, "document_id": DOCUMENT}, ["folder_id", "document_id"]),
        summarize_canvas,
        READ_ONLY,
        SURFACES,
    ),
    ToolSpec(
        "canvas_find_overlaps",
        "Check canvas readability",
        "Report overlapping elements, crowded pairs, out-of-bounds elements, disconnected nodes, and missing accessible "
        "labels. Run it after edits; fix any overlaps by calling canvas_apply_layout rather than moving elements by hand.",
        _obj({"folder_id": FOLDER, "session_id": SESSION, "document_id": DOCUMENT}, ["folder_id", "document_id"]),
        find_overlaps,
        READ_ONLY,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_node",
        "Add a node",
        "Add one node (task, event, gateway, decision, start, end, ...) to the canvas. The node is created at position "
        "(0,0) with the engine's default size: you MUST call canvas_apply_layout afterwards so geometry is computed by "
        "the layout engine, otherwise nodes stack on top of each other. For a whole diagram prefer "
        "canvas_create_process_map, which batches nodes, edges, and the layout pass.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "node_kind": {"type": "string", "enum": NODE_KINDS, "description": "Semantic node kind."},
                "label": {"type": "string", "description": "Visible node label."},
                "sublabel": {"type": "string", "description": "Optional secondary line."},
                "metrics": _METRIC_LIST,
                "layer_id": _LAYER,
                "element_id": {"type": "string", "description": "Optional id; slugified from label when omitted."},
            },
            ["folder_id", "document_id", "label", "node_kind"],
        ),
        add_node,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_edge",
        "Connect two elements",
        "Connect two existing elements with a typed edge. Edge geometry is derived from the endpoints, so no coordinates "
        "are needed; run canvas_apply_layout after adding nodes and edges. Use canvas_inspect to get valid ids.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "source_id": {"type": "string", "description": "Existing source element id."},
                "target_id": {"type": "string", "description": "Existing target element id."},
                "edge_kind": {"type": "string", "enum": EDGE_KINDS, "description": "sequence for normal flow, rework for loops back."},
                "label": {"type": "string", "description": "Optional edge label, e.g. a condition or case count."},
                "marker": {"type": "string", "enum": EDGE_MARKERS},
                "routing": {"type": "string", "enum": EDGE_ROUTINGS},
                "metrics": _METRIC_LIST,
            },
            ["folder_id", "document_id", "source_id", "target_id", "edge_kind"],
        ),
        add_edge,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_text",
        "Add a text note",
        "Add a note, title, caption, or callout. Placed below existing content unless x and y are given; text is never "
        "part of the graph layout, so no layout call is required.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "text": {"type": "string", "description": "Text body."},
                "role": {"type": "string", "enum": TEXT_ROLES},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "layer_id": _LAYER,
                "style": STYLE_SCHEMA,
            },
            ["folder_id", "document_id", "text"],
        ),
        add_text,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_shape",
        "Add a shape",
        "Add a decorative or structural shape (rect, ellipse, diamond, arrow, ...) with optional inline text. "
        "Placed below existing content unless x and y are given.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "shape": {"type": "string", "enum": SHAPE_KINDS},
                "text": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "layer_id": _LAYER,
                "style": STYLE_SCHEMA,
            },
            ["folder_id", "document_id", "shape"],
        ),
        add_shape,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_path",
        "Draw a freeform path",
        "Add a deterministic vector stroke from ordered points. Use it for hand-drawn annotations, custom symbols, "
        "simple sketches, and diagram marks that are not covered by semantic nodes or shapes.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "points": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4096,
                    "items": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                        },
                        "required": ["x", "y"],
                    },
                },
                "tool": {"type": "string", "enum": ["pen", "marker", "highlighter"]},
                "closed": {"type": "boolean"},
                "smoothing": {"type": "number", "minimum": 0, "maximum": 1},
                "layer_id": _LAYER,
                "style": STYLE_SCHEMA,
            },
            ["folder_id", "document_id", "points"],
        ),
        add_path,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_add_legend",
        "Add a legend",
        "Add a legend explaining the swatches or line styles used on the canvas. Placed to the right of existing content "
        "unless x and y are given.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "entries": {"type": "array", "items": _LEGEND_ITEM, "description": "One entry per series or variant."},
                "title": {"type": "string"},
                "orientation": {"type": "string", "enum": LEGEND_ORIENTATIONS},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "layer_id": _LAYER,
            },
            ["folder_id", "document_id", "entries"],
        ),
        add_legend,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_create_process_map",
        "Create a process map in one call",
        "Preferred way to draw a flow, process map, or dependency diagram: creates every node and edge in ONE commit and "
        "then runs a layered layout pass in a SECOND commit, so all geometry is engine-computed and readable. Node ids "
        "are slugified from labels when omitted, and edges reference nodes by id or label. Cycles (rework loops) are "
        "handled by the layout engine. After this call, use canvas_inspect to read the resulting ids; no manual layout "
        "or coordinates are needed.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "nodes": {"type": "array", "items": _NODE_ITEM, "description": "All process steps, in reading order."},
                "edges": {"type": "array", "items": _EDGE_ITEM, "description": "Flow between steps."},
                "title": {"type": "string", "description": "Optional new canvas title."},
                "direction": {"type": "string", "enum": LAYOUT_DIRECTIONS, "description": "Flow direction (default right)."},
                "layout": {"type": "string", "enum": LAYOUT_ALGORITHMS, "description": "Layout algorithm (default layered)."},
                "node_spacing": {"type": "number", "description": "Gap between nodes in the same rank."},
                "rank_spacing": {"type": "number", "description": "Gap between ranks."},
            },
            ["folder_id", "document_id", "nodes"],
        ),
        create_process_map,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_create_variant_paths",
        "Create a variant path map",
        "Draw process variants: the shared process nodes plus one styled edge path per variant, each carrying its case "
        "count/percentage, followed by an engine-computed layout pass and a legend listing every variant. Use it for "
        "process-mining style 'how do cases actually flow' answers. Emphasis defaults to highlight for the first variant.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "nodes": {"type": "array", "items": _NODE_ITEM, "description": "Process steps shared by all variants."},
                "variants": {"type": "array", "items": _VARIANT_ITEM, "description": "One entry per variant path."},
                "title": {"type": "string"},
                "direction": {"type": "string", "enum": LAYOUT_DIRECTIONS},
                "layout": {"type": "string", "enum": LAYOUT_ALGORITHMS},
                "legend_title": {"type": "string", "description": "Legend title (default 'Variants')."},
            },
            ["folder_id", "document_id", "nodes", "variants"],
        ),
        create_variant_paths,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_highlight_path",
        "Emphasise elements",
        "Emphasise a set of elements using style tokens only (highlight, dim, or outline) - geometry and labels are never "
        "touched. Set dim_others to true to fade everything else so one path stands out. Get ids from canvas_inspect.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "emphasis": {"type": "string", "enum": EMPHASIS_TOKENS, "description": "highlight, dim, outline, or none."},
                "dim_others": {"type": "boolean", "description": "Dim every element outside element_ids."},
            },
            ["folder_id", "document_id", "element_ids", "emphasis"],
        ),
        highlight_path,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_create_chart",
        "Add a grounded chart",
        "Query the selected prepared table, add a chart with the returned values, and record the server-resolved table "
        "revision as provenance. The model chooses the fields and visual form; it never supplies the numeric payload. "
        "Use Prepare first for filtered charts.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "chart_type": {"type": "string", "enum": CHART_TYPES},
                "title": {"type": "string"},
                "x_field": {"type": "string", "description": "Category/time column."},
                "y_fields": {"type": "array", "items": {"type": "string"}, "description": "One or more measure columns."},
                "source_table_id": {"type": "string", "description": "Required id of the approved prepared table."},
                "transform_revision": {"type": "integer", "description": "Revision of that prepared table."},
                "aggregation": {"type": "string", "enum": ["sum", "avg", "min", "max", "count"]},
                "filters": _FILTERS,
                "a11y_label": {"type": "string", "description": "Required sentence describing what the chart shows."},
                "series_field": {"type": "string"},
                "stacked": {"type": "boolean"},
                "row_limit": {"type": "integer"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"},
            },
            ["folder_id", "document_id", "chart_type", "title", "x_field", "y_fields", "source_table_id", "a11y_label"],
        ),
        create_chart,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_create_kpi",
        "Add a grounded KPI",
        "Query a single aggregate from the selected prepared table and add it as a KPI. The backend computes the value "
        "and records the exact table revision; the model only chooses the field, aggregation, label, and format.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "label": {"type": "string", "description": "KPI caption."},
                "value_field": {"type": "string", "description": "Numeric field; omit only when aggregation is count."},
                "value": {"type": ["string", "number"], "description": "Legacy direct-call value; ignored in agent sessions."},
                "unit": {"type": "string"},
                "format": {"type": "string", "enum": METRIC_FORMATS},
                "source_table_id": {"type": "string", "description": "Required id of the approved prepared table."},
                "transform_revision": {"type": "integer"},
                "aggregation": {"type": "string", "enum": ["sum", "avg", "min", "max", "count"]},
                "filters": _FILTERS,
                "a11y_label": {"type": "string", "description": "Required sentence describing the KPI."},
                "delta": {
                    "type": "object",
                    "description": "Optional comparison metric.",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": ["string", "number"]},
                        "unit": {"type": "string"},
                        "format": {"type": "string", "enum": METRIC_FORMATS},
                    },
                    "required": ["label", "value"],
                },
                "trend": {"type": "string", "enum": KPI_TRENDS},
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            ["folder_id", "document_id", "label", "source_table_id", "aggregation", "a11y_label"],
        ),
        create_kpi,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_create_gantt",
        "Add a grounded gantt chart",
        "Add a gantt/timeline element from bars with label, lane, start, and end (ISO dates). source_table_id and "
        "a11y_label are mandatory, and progress is a 0-1 fraction.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "title": {"type": "string"},
                "bars": {
                    "type": "array",
                    "description": "One bar per scheduled item.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                            "lane": {"type": "string", "description": "Row/swimlane the bar belongs to."},
                            "start": {"type": "string", "description": "ISO date or datetime."},
                            "end": {"type": "string", "description": "ISO date or datetime."},
                            "progress": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "swatch": {"type": "string", "enum": SWATCH_TOKENS},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["label", "lane", "start", "end"],
                    },
                },
                "source_table_id": {"type": "string", "description": "Required id of the approved prepared table."},
                "transform_revision": {"type": "integer"},
                "aggregation": {"type": "string", "enum": AGGREGATIONS},
                "filters": _FILTERS,
                "a11y_label": {"type": "string", "description": "Required sentence describing the schedule."},
                "time_unit": {"type": "string", "enum": GANTT_TIME_UNITS},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"},
            },
            ["folder_id", "document_id", "title", "bars", "source_table_id", "a11y_label"],
        ),
        create_gantt,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_apply_layout",
        "Lay out the canvas",
        "Recompute geometry with the deterministic layout engine and commit it as ops. This is the ONLY correct way to "
        "position nodes: call it after adding nodes/edges and whenever canvas_find_overlaps reports overlaps. "
        "layered suits flows and process maps, tree suits decision trees and org charts, grid suits KPI/chart walls, "
        "timeline suits milestones, radial suits dependency networks. Restrict the pass with element_ids when only part "
        "of the canvas should move.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "algorithm": {"type": "string", "enum": LAYOUT_ALGORITHMS},
                "direction": {"type": "string", "enum": LAYOUT_DIRECTIONS},
                "node_spacing": {"type": "number", "description": "Gap within a rank (default 56)."},
                "rank_spacing": {"type": "number", "description": "Gap between ranks (default 140)."},
                "columns": {"type": "integer", "description": "Columns for the grid algorithm."},
                "element_ids": _ELEMENT_IDS,
            },
            ["folder_id", "document_id", "algorithm"],
        ),
        apply_layout,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_align",
        "Align elements",
        "Align two or more elements on one edge or axis using engine-computed offsets. Use canvas_apply_layout for whole "
        "diagrams; use this for small manual tidy-ups the user asks for.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "axis": {"type": "string", "enum": ALIGN_AXES},
            },
            ["folder_id", "document_id", "element_ids", "axis"],
        ),
        align_elements,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_distribute",
        "Distribute elements evenly",
        "Space three or more elements evenly along the x or y axis, keeping the first and last in place.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "axis": {"type": "string", "enum": DISTRIBUTE_AXES},
            },
            ["folder_id", "document_id", "element_ids", "axis"],
        ),
        distribute_elements,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_move_elements",
        "Move elements",
        "Translate elements by a relative offset. Prefer canvas_apply_layout for diagram geometry; use this only for an "
        "explicit user nudge.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "dx": {"type": "number", "description": "Horizontal offset."},
                "dy": {"type": "number", "description": "Vertical offset."},
            },
            ["folder_id", "document_id", "element_ids"],
        ),
        move_elements,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_resize_element",
        "Resize an element",
        "Set the size (and optionally the position) of one element. Omitted values keep their current value.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_id": {"type": "string"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            ["folder_id", "document_id", "element_id"],
        ),
        resize_element,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_update_style",
        "Restyle elements",
        "Apply style tokens to elements. Only the closed token vocabulary is accepted - raw colors, CSS, or font names "
        "are rejected with an error you should correct rather than retry verbatim.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "style": STYLE_SCHEMA,
            },
            ["folder_id", "document_id", "element_ids", "style"],
        ),
        update_style,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_group_elements",
        "Group elements",
        "Group elements under a named group so the user can move or collapse them together.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
                "name": {"type": "string", "description": "Group name."},
            },
            ["folder_id", "document_id", "element_ids", "name"],
        ),
        group_elements,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_delete_elements",
        "Delete elements",
        "Delete elements from the canvas. Edges are removed before their endpoints, so deleting a node and its edges in "
        "one call works. The commit is undoable with canvas_undo.",
        _obj(
            {
                "folder_id": FOLDER,
                "session_id": SESSION,
                "document_id": DOCUMENT,
                "element_ids": _ELEMENT_IDS,
            },
            ["folder_id", "document_id", "element_ids"],
        ),
        delete_elements,
        DESTRUCTIVE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_undo",
        "Undo the last canvas commit",
        "Revert the most recent commit on this canvas through the shared history, the same path the user's undo uses. "
        "Use it to back out an edit you just made instead of hand-reversing it.",
        _obj({"folder_id": FOLDER, "session_id": SESSION, "document_id": DOCUMENT}, ["folder_id", "document_id"]),
        undo_canvas,
        WRITE,
        SURFACES,
    ),
    ToolSpec(
        "canvas_redo",
        "Redo the last undone canvas commit",
        "Reapply the most recently undone canvas commit through the shared history.",
        _obj(
            {"folder_id": FOLDER, "session_id": SESSION, "document_id": DOCUMENT},
            ["folder_id", "document_id"],
        ),
        redo_canvas,
        WRITE,
        SURFACES,
    ),
]

__all__ = ["CANVAS_TOOLS"]
