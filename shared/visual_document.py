"""Visual Document - the single authoritative schema for agent-driven canvases.

This module is the source of truth for:

* the ``VisualDocument`` data model (elements, layers, groups, viewport, history),
* the operation ("op") format used for *both* agent patches and user undo/redo,
* structural validation and bounds/style-token enforcement.

Both the FastAPI backend and the LangGraph agent server import from here, and the
TypeScript wire types consumed by the frontend are generated from these models by
``shared/visual_schema_export.py``. Nothing else may define a competing schema.

Design rules enforced here:

* Style is expressed with **tokens only** - every model uses ``extra="forbid"`` so
  arbitrary CSS or unknown keys are rejected rather than silently passed through.
* Data-bearing elements (charts, KPIs, tables) must carry ``provenance`` pointing at
  an approved source table, so a visual can never show ungrounded numbers.
* Geometry is validated against a fixed virtual coordinate space. Screen size only
  changes the ``viewport``, never element geometry.
* Every mutation is an op with a computable inverse, so agent edits and user edits
  share one history representation.

Wire format is ``snake_case`` (matching the existing FastAPI payloads); the generated
TypeScript mirrors these names exactly.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "1.0"

# --- virtual coordinate space ------------------------------------------------
CANVAS_MIN = -100_000.0
CANVAS_MAX = 100_000.0
MIN_ELEMENT_SIZE = 8.0
MAX_ELEMENT_SIZE = 20_000.0
MIN_ZOOM = 0.05
MAX_ZOOM = 8.0

# --- document limits ---------------------------------------------------------
MAX_ELEMENTS = 2_000
MAX_LAYERS = 32
MAX_GROUPS = 256
MAX_HISTORY = 200
MAX_PATH_POINTS = 4_000
MAX_TEXT_LENGTH = 8_000
MAX_LABEL_LENGTH = 300

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"


class VisualDocumentError(ValueError):
    """Raised when a document or op is invalid. Safe to surface to the agent."""

    def __init__(self, message: str, *, code: str = "invalid", path: str | None = None):
        self.code = code
        self.path = path
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": str(self), "path": self.path}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class _Base(BaseModel):
    """All Visual Document models reject unknown keys."""

    model_config = ConfigDict(extra="forbid", validate_assignment=False)


# ---------------------------------------------------------------------------
# Style tokens
# ---------------------------------------------------------------------------

FillToken = Literal[
    "transparent",
    "surface",
    "surface-muted",
    "surface-raised",
    "surface-inverted",
    "accent",
    "accent-muted",
    "success",
    "warning",
    "danger",
    "info",
]
StrokeToken = Literal[
    "none",
    "subtle",
    "default",
    "strong",
    "accent",
    "success",
    "warning",
    "danger",
    "info",
]
TextToken = Literal[
    "caption",
    "label",
    "body-sm",
    "body",
    "heading-sm",
    "heading",
    "heading-lg",
    "mono",
]
SwatchToken = Literal[
    "series-1",
    "series-2",
    "series-3",
    "series-4",
    "series-5",
    "series-6",
    "neutral",
    "accent",
    "success",
    "warning",
    "danger",
]


class StyleTokens(_Base):
    """Closed style vocabulary. No raw CSS, colors, or font names allowed."""

    fill: FillToken = "surface"
    stroke: StrokeToken = "default"
    stroke_width: Literal["none", "thin", "regular", "thick"] = "thin"
    stroke_dash: Literal["solid", "dashed", "dotted"] = "solid"
    text: TextToken = "body"
    text_align: Literal["left", "center", "right"] = "left"
    corner: Literal["sharp", "soft", "round", "pill"] = "soft"
    shadow: Literal["none", "soft", "raised"] = "none"
    emphasis: Literal["none", "highlight", "dim", "outline"] = "none"
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


class Point(_Base):
    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def _in_bounds(cls, v: float) -> float:
        if not CANVAS_MIN <= v <= CANVAS_MAX:
            raise ValueError(
                f"coordinate {v} outside canvas bounds [{CANVAS_MIN}, {CANVAS_MAX}]"
            )
        return v


class Rect(_Base):
    x: float
    y: float
    w: float
    h: float

    @field_validator("x", "y")
    @classmethod
    def _pos_in_bounds(cls, v: float) -> float:
        if not CANVAS_MIN <= v <= CANVAS_MAX:
            raise ValueError(
                f"position {v} outside canvas bounds [{CANVAS_MIN}, {CANVAS_MAX}]"
            )
        return v

    @field_validator("w", "h")
    @classmethod
    def _size_in_bounds(cls, v: float) -> float:
        if not MIN_ELEMENT_SIZE <= v <= MAX_ELEMENT_SIZE:
            raise ValueError(
                f"size {v} outside allowed range [{MIN_ELEMENT_SIZE}, {MAX_ELEMENT_SIZE}]"
            )
        return v


# ---------------------------------------------------------------------------
# Data provenance
# ---------------------------------------------------------------------------

FilterOp = Literal[
    "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "between"
]
ScalarValue = Union[str, float, bool, None]


class ProvenanceFilter(_Base):
    field: str = Field(min_length=1, max_length=200)
    op: FilterOp
    value: Union[ScalarValue, list[ScalarValue]] = None


class Provenance(_Base):
    """Where the numbers came from. Required on every data-bearing element."""

    source_table_id: str = Field(min_length=1, max_length=200)
    folder_id: str | None = None
    transform_revision: int | None = None
    columns: list[str] = Field(default_factory=list, max_length=64)
    aggregation: Literal["none", "sum", "avg", "min", "max", "count", "median"] = "none"
    filters: list[ProvenanceFilter] = Field(default_factory=list, max_length=32)
    query_id: str | None = None
    generated_at: str | None = None


class Metric(_Base):
    """A single grounded number rendered inside a semantic element."""

    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    value: Union[float, str]
    unit: str | None = Field(default=None, max_length=32)
    format: Literal["raw", "integer", "decimal", "percent", "currency", "duration"] = "raw"


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------


class ElementMeta(_Base):
    """Server-maintained audit fields. Tools never need to send these."""

    created_at: str | None = None
    created_by: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    revision: int = 0


class _ElementBase(_Base):
    id: str = Field(pattern=ID_PATTERN)
    layer_id: str = Field(pattern=ID_PATTERN)
    group_id: str | None = Field(default=None, pattern=ID_PATTERN)
    z: int = Field(default=0, ge=-10_000, le=10_000)
    locked: bool = False
    hidden: bool = False
    a11y_label: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    style: StyleTokens = Field(default_factory=StyleTokens)
    meta: ElementMeta = Field(default_factory=ElementMeta)

    @property
    def accessible_label(self) -> str:
        """Label exposed to the parallel semantic outline / screen readers."""
        return self.a11y_label or getattr(self, "label", None) or getattr(self, "title", None) or self.id


class _RequiresProvenance(_ElementBase):
    """Mixin marker for elements that must be grounded in approved data."""

    @model_validator(mode="after")
    def _require_a11y(self):
        if not (self.a11y_label and self.a11y_label.strip()):
            raise ValueError(
                f"{type(self).__name__} requires a non-empty a11y_label so the data "
                "has an accessible parallel representation"
            )
        return self


NodeKind = Literal[
    "task",
    "event",
    "gateway",
    "decision",
    "start",
    "end",
    "entity",
    "actor",
    "lane",
    "milestone",
    "annotation",
    "generic",
]


class NodeElement(_ElementBase):
    type: Literal["node"] = "node"
    rect: Rect
    node_kind: NodeKind = "task"
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    sublabel: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    metrics: list[Metric] = Field(default_factory=list, max_length=8)
    provenance: Provenance | None = None
    parent_id: str | None = Field(default=None, pattern=ID_PATTERN)


EdgeKind = Literal[
    "sequence", "conditional", "message", "dependency", "association", "rework"
]


class EdgeElement(_ElementBase):
    """Edges have no rect - geometry is derived from endpoints plus waypoints."""

    type: Literal["edge"] = "edge"
    source_id: str = Field(pattern=ID_PATTERN)
    target_id: str = Field(pattern=ID_PATTERN)
    source_handle: Literal["top", "right", "bottom", "left"] | None = None
    target_handle: Literal["top", "right", "bottom", "left"] | None = None
    edge_kind: EdgeKind = "sequence"
    label: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    marker: Literal["none", "arrow", "arrow-both", "dot"] = "arrow"
    routing: Literal["straight", "smoothstep", "bezier", "orthogonal"] = "smoothstep"
    waypoints: list[Point] = Field(default_factory=list, max_length=64)
    metrics: list[Metric] = Field(default_factory=list, max_length=4)
    provenance: Provenance | None = None


ChartType = Literal[
    "bar",
    "column",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "heatmap",
    "waterfall",
    "funnel",
    "sankey",
    "treemap",
    "radar",
    "boxplot",
]


class ChartDataPoint(_Base):
    label: str = Field(max_length=MAX_LABEL_LENGTH)
    value: float
    series: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)


class ChartElement(_RequiresProvenance):
    type: Literal["chart"] = "chart"
    rect: Rect
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    x_field: str = Field(min_length=1, max_length=200)
    y_fields: list[str] = Field(min_length=1, max_length=12)
    data: list[ChartDataPoint] = Field(default_factory=list, max_length=500)
    series_field: str | None = Field(default=None, max_length=200)
    stacked: bool = False
    show_grid: bool = True
    show_legend: bool = True
    show_tooltip: bool = True
    row_limit: int = Field(default=100, ge=1, le=10_000)
    palette: list[SwatchToken] = Field(default_factory=list, max_length=12)
    provenance: Provenance


class KpiElement(_RequiresProvenance):
    type: Literal["kpi"] = "kpi"
    rect: Rect
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    metric: Metric
    delta: Metric | None = None
    trend: Literal["none", "up", "down", "flat"] = "none"
    provenance: Provenance


class TableColumn(_Base):
    field: str = Field(min_length=1, max_length=200)
    header: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    align: Literal["left", "center", "right"] = "left"
    format: Literal["raw", "integer", "decimal", "percent", "currency", "duration"] = "raw"


class TableElement(_RequiresProvenance):
    type: Literal["table"] = "table"
    rect: Rect
    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    columns: list[TableColumn] = Field(min_length=1, max_length=40)
    page_size: int = Field(default=25, ge=1, le=500)
    provenance: Provenance


class GanttBar(_Base):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    lane: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    start: str = Field(min_length=1, max_length=64)
    end: str = Field(min_length=1, max_length=64)
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    swatch: SwatchToken = "series-1"
    depends_on: list[str] = Field(default_factory=list, max_length=32)


class GanttElement(_RequiresProvenance):
    type: Literal["gantt"] = "gantt"
    rect: Rect
    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    bars: list[GanttBar] = Field(default_factory=list, max_length=500)
    time_unit: Literal["hour", "day", "week", "month", "quarter", "year"] = "day"
    show_dependencies: bool = True
    provenance: Provenance


class TextElement(_ElementBase):
    type: Literal["text"] = "text"
    rect: Rect
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    role: Literal["note", "title", "caption", "callout"] = "note"


ShapeKind = Literal[
    "rect",
    "ellipse",
    "triangle",
    "diamond",
    "arrow",
    "line",
    "star",
    "cloud",
    "callout",
    "bracket",
]


class ShapeElement(_ElementBase):
    type: Literal["shape"] = "shape"
    rect: Rect
    shape: ShapeKind = "rect"
    text: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    rotation: float = Field(default=0.0, ge=-360.0, le=360.0)


class PathElement(_ElementBase):
    """Freeform stroke. Bounding box is derived, never authored."""

    type: Literal["path"] = "path"
    points: list[Point] = Field(min_length=2, max_length=MAX_PATH_POINTS)
    tool: Literal["pen", "marker", "highlighter"] = "pen"
    closed: bool = False
    smoothing: float = Field(default=0.5, ge=0.0, le=1.0)

    @property
    def bbox(self) -> Rect:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return Rect(
            x=min(xs),
            y=min(ys),
            w=max(max(xs) - min(xs), MIN_ELEMENT_SIZE),
            h=max(max(ys) - min(ys), MIN_ELEMENT_SIZE),
        )


class ImageElement(_ElementBase):
    type: Literal["image"] = "image"
    rect: Rect
    asset_id: str = Field(min_length=1, max_length=200)
    origin: Literal["upload", "generated", "export"] = "upload"
    prompt: str | None = Field(default=None, max_length=2_000)
    fit: Literal["contain", "cover", "fill"] = "contain"

    @model_validator(mode="after")
    def _require_a11y(self):
        if not (self.a11y_label and self.a11y_label.strip()):
            raise ValueError("ImageElement requires a non-empty a11y_label (alt text)")
        return self


class LegendEntry(_Base):
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    swatch: SwatchToken = "series-1"
    shape: Literal["square", "line", "dashed-line", "dot"] = "square"


class LegendElement(_ElementBase):
    type: Literal["legend"] = "legend"
    rect: Rect
    title: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    entries: list[LegendEntry] = Field(min_length=1, max_length=32)
    orientation: Literal["vertical", "horizontal"] = "vertical"


Element = Annotated[
    Union[
        NodeElement,
        EdgeElement,
        ChartElement,
        KpiElement,
        TableElement,
        GanttElement,
        TextElement,
        ShapeElement,
        PathElement,
        ImageElement,
        LegendElement,
    ],
    Field(discriminator="type"),
]

GEOMETRIC_TYPES = {
    "node",
    "chart",
    "kpi",
    "table",
    "gantt",
    "text",
    "shape",
    "image",
    "legend",
}
DATA_TYPES = {"chart", "kpi", "table", "gantt"}


# ---------------------------------------------------------------------------
# Layers, groups, viewport, history
# ---------------------------------------------------------------------------


class Layer(_Base):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    index: int = Field(default=0, ge=0, le=MAX_LAYERS)
    visible: bool = True
    locked: bool = False
    kind: Literal["semantic", "data", "freeform", "annotation", "background"] = "semantic"


class Group(_Base):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    element_ids: list[str] = Field(default_factory=list, max_length=MAX_ELEMENTS)
    locked: bool = False


class Viewport(_Base):
    zoom: float = Field(default=1.0, ge=MIN_ZOOM, le=MAX_ZOOM)
    x: float = 0.0
    y: float = 0.0
    selected_ids: list[str] = Field(default_factory=list, max_length=MAX_ELEMENTS)


class DocumentMetadata(_Base):
    id: str = Field(pattern=ID_PATTERN)
    project_id: str = Field(min_length=1, max_length=200)
    folder_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    revision: int = Field(default=0, ge=0)
    created_by: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    updated_by: str | None = None
    source_table_ids: list[str] = Field(default_factory=list, max_length=64)
    source_revision: int | None = None


class Commit(_Base):
    """One applied batch of ops plus the inverse needed to undo it."""

    id: str
    revision: int
    at: str
    author: str
    author_kind: Literal["user", "agent", "system"] = "user"
    label: str = Field(default="edit", max_length=MAX_LABEL_LENGTH)
    ops: list["Op"] = Field(default_factory=list)
    inverse_ops: list["Op"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ops - the shared mutation format for agent patches AND user undo/redo
# ---------------------------------------------------------------------------


class AddElementOp(_Base):
    op: Literal["add_element"] = "add_element"
    element: Element


class RemoveElementOp(_Base):
    op: Literal["remove_element"] = "remove_element"
    element_id: str = Field(pattern=ID_PATTERN)


class UpdateElementOp(_Base):
    """Partial update. The result is re-validated against the element model, so
    immutable fields (``id``, ``type``, ``meta``) are rejected."""

    op: Literal["update_element"] = "update_element"
    element_id: str = Field(pattern=ID_PATTERN)
    patch: dict[str, Any] = Field(default_factory=dict)


class MoveElementsOp(_Base):
    op: Literal["move_elements"] = "move_elements"
    element_ids: list[str] = Field(min_length=1, max_length=MAX_ELEMENTS)
    dx: float = 0.0
    dy: float = 0.0


class ResizeElementOp(_Base):
    op: Literal["resize_element"] = "resize_element"
    element_id: str = Field(pattern=ID_PATTERN)
    rect: Rect


class SetStyleOp(_Base):
    op: Literal["set_style"] = "set_style"
    element_ids: list[str] = Field(min_length=1, max_length=MAX_ELEMENTS)
    style: dict[str, Any] = Field(default_factory=dict)


class SetLayerOp(_Base):
    op: Literal["set_layer"] = "set_layer"
    element_ids: list[str] = Field(min_length=1, max_length=MAX_ELEMENTS)
    layer_id: str = Field(pattern=ID_PATTERN)


class ReorderElementOp(_Base):
    op: Literal["reorder_element"] = "reorder_element"
    element_id: str = Field(pattern=ID_PATTERN)
    z: int = Field(ge=-10_000, le=10_000)


class AddLayerOp(_Base):
    op: Literal["add_layer"] = "add_layer"
    layer: Layer


class UpdateLayerOp(_Base):
    op: Literal["update_layer"] = "update_layer"
    layer_id: str = Field(pattern=ID_PATTERN)
    patch: dict[str, Any] = Field(default_factory=dict)


class RemoveLayerOp(_Base):
    op: Literal["remove_layer"] = "remove_layer"
    layer_id: str = Field(pattern=ID_PATTERN)


class CreateGroupOp(_Base):
    op: Literal["create_group"] = "create_group"
    group: Group


class UngroupOp(_Base):
    op: Literal["ungroup"] = "ungroup"
    group_id: str = Field(pattern=ID_PATTERN)


class SetViewportOp(_Base):
    op: Literal["set_viewport"] = "set_viewport"
    zoom: float | None = Field(default=None, ge=MIN_ZOOM, le=MAX_ZOOM)
    x: float | None = None
    y: float | None = None


class SetSelectionOp(_Base):
    op: Literal["set_selection"] = "set_selection"
    element_ids: list[str] = Field(default_factory=list, max_length=MAX_ELEMENTS)


class SetTitleOp(_Base):
    op: Literal["set_title"] = "set_title"
    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)


Op = Annotated[
    Union[
        AddElementOp,
        RemoveElementOp,
        UpdateElementOp,
        MoveElementsOp,
        ResizeElementOp,
        SetStyleOp,
        SetLayerOp,
        ReorderElementOp,
        AddLayerOp,
        UpdateLayerOp,
        RemoveLayerOp,
        CreateGroupOp,
        UngroupOp,
        SetViewportOp,
        SetSelectionOp,
        SetTitleOp,
    ],
    Field(discriminator="op"),
]


class VisualDocument(_Base):
    metadata: DocumentMetadata
    viewport: Viewport = Field(default_factory=Viewport)
    layers: list[Layer] = Field(default_factory=list, max_length=MAX_LAYERS)
    groups: list[Group] = Field(default_factory=list, max_length=MAX_GROUPS)
    elements: list[Element] = Field(default_factory=list, max_length=MAX_ELEMENTS)
    history: list[Commit] = Field(default_factory=list, max_length=MAX_HISTORY)
    redo_stack: list[Commit] = Field(default_factory=list, max_length=MAX_HISTORY)

    # -- lookups ---------------------------------------------------------
    def element(self, element_id: str) -> Element:
        for el in self.elements:
            if el.id == element_id:
                return el
        raise VisualDocumentError(
            f"unknown element '{element_id}'", code="unknown_element", path=element_id
        )

    def layer(self, layer_id: str) -> Layer:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        raise VisualDocumentError(
            f"unknown layer '{layer_id}'", code="unknown_layer", path=layer_id
        )

    def group(self, group_id: str) -> Group:
        for group in self.groups:
            if group.id == group_id:
                return group
        raise VisualDocumentError(
            f"unknown group '{group_id}'", code="unknown_group", path=group_id
        )

    def has_element(self, element_id: str) -> bool:
        return any(el.id == element_id for el in self.elements)

    @model_validator(mode="after")
    def _integrity(self):
        _check_integrity(self)
        return self

    # -- accessible parallel representation ------------------------------
    def outline(self) -> list[dict[str, Any]]:
        """Semantic outline used for keyboard/screen-reader inspection and for
        the agent's ``inspect_canvas`` tool."""
        rows: list[dict[str, Any]] = []
        for el in sorted(self.elements, key=lambda e: (e.z, e.id)):
            row: dict[str, Any] = {
                "id": el.id,
                "type": el.type,
                "label": el.accessible_label,
                "layer_id": el.layer_id,
                "group_id": el.group_id,
                "hidden": el.hidden,
                "locked": el.locked,
            }
            if isinstance(el, EdgeElement):
                row["from"] = el.source_id
                row["to"] = el.target_id
                row["edge_kind"] = el.edge_kind
            provenance = getattr(el, "provenance", None)
            if provenance is not None:
                row["source_table_id"] = provenance.source_table_id
                row["transform_revision"] = provenance.transform_revision
            rows.append(row)
        return rows


Commit.model_rebuild()
VisualDocument.model_rebuild()


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def _check_integrity(doc: VisualDocument) -> None:
    if len(doc.elements) > MAX_ELEMENTS:
        raise ValueError(f"document exceeds {MAX_ELEMENTS} elements")

    layer_ids = {layer.id for layer in doc.layers}
    if len(layer_ids) != len(doc.layers):
        raise ValueError("duplicate layer id")
    group_ids = {group.id for group in doc.groups}
    if len(group_ids) != len(doc.groups):
        raise ValueError("duplicate group id")

    element_ids: set[str] = set()
    for el in doc.elements:
        if el.id in element_ids:
            raise ValueError(f"duplicate element id '{el.id}'")
        element_ids.add(el.id)
        if el.layer_id not in layer_ids:
            raise ValueError(f"element '{el.id}' references unknown layer '{el.layer_id}'")
        if el.group_id is not None and el.group_id not in group_ids:
            raise ValueError(f"element '{el.id}' references unknown group '{el.group_id}'")

    by_id = {el.id: el for el in doc.elements}
    for el in doc.elements:
        if isinstance(el, EdgeElement):
            for endpoint, ref in (("source_id", el.source_id), ("target_id", el.target_id)):
                target = by_id.get(ref)
                if target is None:
                    raise ValueError(
                        f"edge '{el.id}' {endpoint} references unknown element '{ref}'"
                    )
                if target.type == "edge":
                    raise ValueError(f"edge '{el.id}' {endpoint} may not point at an edge")
        if isinstance(el, NodeElement) and el.parent_id is not None:
            parent = by_id.get(el.parent_id)
            if parent is None or parent.type != "node":
                raise ValueError(
                    f"node '{el.id}' parent_id must reference an existing node"
                )
            if el.parent_id == el.id:
                raise ValueError(f"node '{el.id}' cannot be its own parent")

    for group in doc.groups:
        for member in group.element_ids:
            if member not in element_ids:
                raise ValueError(
                    f"group '{group.id}' references unknown element '{member}'"
                )

    for selected in doc.viewport.selected_ids:
        if selected not in element_ids:
            raise ValueError(f"viewport selection references unknown element '{selected}'")


# ---------------------------------------------------------------------------
# Op application + inversion
# ---------------------------------------------------------------------------

_IMMUTABLE_ELEMENT_FIELDS = {"id", "type", "meta"}
_IMMUTABLE_LAYER_FIELDS = {"id"}


def _element_model(element_type: str) -> type[BaseModel]:
    for model in (
        NodeElement,
        EdgeElement,
        ChartElement,
        KpiElement,
        TableElement,
        GanttElement,
        TextElement,
        ShapeElement,
        PathElement,
        ImageElement,
        LegendElement,
    ):
        if model.model_fields["type"].default == element_type:
            return model
    raise VisualDocumentError(
        f"unknown element type '{element_type}'", code="unknown_element_type"
    )


def _rebuild_element(existing: BaseModel, patch: dict[str, Any]) -> Element:
    illegal = _IMMUTABLE_ELEMENT_FIELDS & set(patch)
    if illegal:
        raise VisualDocumentError(
            f"fields {sorted(illegal)} are immutable", code="immutable_field"
        )
    data = existing.model_dump()
    data.update(patch)
    model = _element_model(data["type"])
    try:
        return model.model_validate(data)  # type: ignore[return-value]
    except ValidationError as exc:
        raise VisualDocumentError(
            f"invalid update for element '{data['id']}': {exc.errors()[0]['msg']}",
            code="invalid_update",
            path=data["id"],
        ) from exc


def _apply_op(doc: VisualDocument, op: Any) -> Any:
    """Mutate ``doc`` in place and return the inverse op."""

    if isinstance(op, AddElementOp):
        if doc.has_element(op.element.id):
            raise VisualDocumentError(
                f"element '{op.element.id}' already exists",
                code="duplicate_element",
                path=op.element.id,
            )
        element = op.element.model_copy(deep=True)
        element.meta = ElementMeta(created_at=_now(), updated_at=_now(), revision=0)
        doc.elements.append(element)
        return RemoveElementOp(element_id=element.id)

    if isinstance(op, RemoveElementOp):
        element = doc.element(op.element_id)
        dependents = [
            el.id
            for el in doc.elements
            if isinstance(el, EdgeElement)
            and op.element_id in (el.source_id, el.target_id)
        ]
        if dependents:
            raise VisualDocumentError(
                f"cannot remove '{op.element_id}' while edges {dependents} attach to it",
                code="element_in_use",
                path=op.element_id,
            )
        if element.locked:
            raise VisualDocumentError(
                f"element '{op.element_id}' is locked", code="locked", path=op.element_id
            )
        doc.elements = [el for el in doc.elements if el.id != op.element_id]
        for group in doc.groups:
            group.element_ids = [m for m in group.element_ids if m != op.element_id]
        doc.viewport.selected_ids = [
            s for s in doc.viewport.selected_ids if s != op.element_id
        ]
        return AddElementOp(element=element)

    if isinstance(op, UpdateElementOp):
        existing = doc.element(op.element_id)
        if existing.locked and "locked" not in op.patch:
            raise VisualDocumentError(
                f"element '{op.element_id}' is locked", code="locked", path=op.element_id
            )
        before = {key: existing.model_dump().get(key) for key in op.patch}
        updated = _rebuild_element(existing, op.patch)
        updated.meta = existing.meta.model_copy(
            update={"updated_at": _now(), "revision": existing.meta.revision + 1}
        )
        doc.elements = [updated if el.id == op.element_id else el for el in doc.elements]
        return UpdateElementOp(element_id=op.element_id, patch=before)

    if isinstance(op, MoveElementsOp):
        for element_id in op.element_ids:
            element = doc.element(element_id)
            if element.locked:
                raise VisualDocumentError(
                    f"element '{element_id}' is locked", code="locked", path=element_id
                )
            if isinstance(element, PathElement):
                moved = [
                    Point(x=p.x + op.dx, y=p.y + op.dy) for p in element.points
                ]
                doc.elements = [
                    element.model_copy(update={"points": moved})
                    if el.id == element_id
                    else el
                    for el in doc.elements
                ]
            elif isinstance(element, EdgeElement):
                moved_waypoints = [
                    Point(x=p.x + op.dx, y=p.y + op.dy) for p in element.waypoints
                ]
                doc.elements = [
                    element.model_copy(update={"waypoints": moved_waypoints})
                    if el.id == element_id
                    else el
                    for el in doc.elements
                ]
            else:
                rect: Rect = element.rect  # type: ignore[attr-defined]
                new_rect = Rect(x=rect.x + op.dx, y=rect.y + op.dy, w=rect.w, h=rect.h)
                doc.elements = [
                    element.model_copy(update={"rect": new_rect})
                    if el.id == element_id
                    else el
                    for el in doc.elements
                ]
        return MoveElementsOp(element_ids=list(op.element_ids), dx=-op.dx, dy=-op.dy)

    if isinstance(op, ResizeElementOp):
        element = doc.element(op.element_id)
        if element.type not in GEOMETRIC_TYPES:
            raise VisualDocumentError(
                f"element type '{element.type}' has no resizable rect",
                code="not_resizable",
                path=op.element_id,
            )
        if element.locked:
            raise VisualDocumentError(
                f"element '{op.element_id}' is locked", code="locked", path=op.element_id
            )
        previous: Rect = element.rect  # type: ignore[attr-defined]
        doc.elements = [
            element.model_copy(update={"rect": op.rect}) if el.id == op.element_id else el
            for el in doc.elements
        ]
        return ResizeElementOp(element_id=op.element_id, rect=previous)

    if isinstance(op, SetStyleOp):
        unknown = set(op.style) - set(StyleTokens.model_fields)
        if unknown:
            raise VisualDocumentError(
                f"unknown style tokens {sorted(unknown)}", code="unknown_style_token"
            )
        inverse_styles: dict[str, dict[str, Any]] = {}
        for element_id in op.element_ids:
            element = doc.element(element_id)
            current = element.style.model_dump()
            inverse_styles[element_id] = {key: current[key] for key in op.style}
            try:
                new_style = StyleTokens.model_validate({**current, **op.style})
            except ValidationError as exc:
                raise VisualDocumentError(
                    f"invalid style value: {exc.errors()[0]['msg']}",
                    code="invalid_style",
                    path=element_id,
                ) from exc
            doc.elements = [
                element.model_copy(update={"style": new_style})
                if el.id == element_id
                else el
                for el in doc.elements
            ]
        # One inverse op per element, since previous values differ.
        if len(inverse_styles) == 1:
            only_id, style = next(iter(inverse_styles.items()))
            return SetStyleOp(element_ids=[only_id], style=style)
        return _MultiOp(
            [SetStyleOp(element_ids=[k], style=v) for k, v in inverse_styles.items()]
        )

    if isinstance(op, SetLayerOp):
        doc.layer(op.layer_id)
        inverse = [
            SetLayerOp(element_ids=[element_id], layer_id=doc.element(element_id).layer_id)
            for element_id in op.element_ids
        ]
        for element_id in op.element_ids:
            element = doc.element(element_id)
            doc.elements = [
                element.model_copy(update={"layer_id": op.layer_id})
                if el.id == element_id
                else el
                for el in doc.elements
            ]
        return inverse[0] if len(inverse) == 1 else _MultiOp(inverse)

    if isinstance(op, ReorderElementOp):
        element = doc.element(op.element_id)
        previous_z = element.z
        doc.elements = [
            element.model_copy(update={"z": op.z}) if el.id == op.element_id else el
            for el in doc.elements
        ]
        return ReorderElementOp(element_id=op.element_id, z=previous_z)

    if isinstance(op, AddLayerOp):
        if any(layer.id == op.layer.id for layer in doc.layers):
            raise VisualDocumentError(
                f"layer '{op.layer.id}' already exists", code="duplicate_layer"
            )
        if len(doc.layers) >= MAX_LAYERS:
            raise VisualDocumentError(
                f"document exceeds {MAX_LAYERS} layers", code="too_many_layers"
            )
        doc.layers.append(op.layer.model_copy(deep=True))
        return RemoveLayerOp(layer_id=op.layer.id)

    if isinstance(op, UpdateLayerOp):
        layer = doc.layer(op.layer_id)
        illegal = _IMMUTABLE_LAYER_FIELDS & set(op.patch)
        if illegal:
            raise VisualDocumentError(
                f"layer fields {sorted(illegal)} are immutable", code="immutable_field"
            )
        before = {key: layer.model_dump().get(key) for key in op.patch}
        try:
            updated = Layer.model_validate({**layer.model_dump(), **op.patch})
        except ValidationError as exc:
            raise VisualDocumentError(
                f"invalid layer update: {exc.errors()[0]['msg']}",
                code="invalid_update",
                path=op.layer_id,
            ) from exc
        doc.layers = [updated if item.id == op.layer_id else item for item in doc.layers]
        return UpdateLayerOp(layer_id=op.layer_id, patch=before)

    if isinstance(op, RemoveLayerOp):
        layer = doc.layer(op.layer_id)
        occupants = [el.id for el in doc.elements if el.layer_id == op.layer_id]
        if occupants:
            raise VisualDocumentError(
                f"cannot remove layer '{op.layer_id}' while it holds {len(occupants)} elements",
                code="layer_in_use",
                path=op.layer_id,
            )
        doc.layers = [item for item in doc.layers if item.id != op.layer_id]
        return AddLayerOp(layer=layer)

    if isinstance(op, CreateGroupOp):
        if any(group.id == op.group.id for group in doc.groups):
            raise VisualDocumentError(
                f"group '{op.group.id}' already exists", code="duplicate_group"
            )
        if len(doc.groups) >= MAX_GROUPS:
            raise VisualDocumentError(
                f"document exceeds {MAX_GROUPS} groups", code="too_many_groups"
            )
        for member in op.group.element_ids:
            doc.element(member)
        doc.groups.append(op.group.model_copy(deep=True))
        for member in op.group.element_ids:
            element = doc.element(member)
            doc.elements = [
                element.model_copy(update={"group_id": op.group.id})
                if el.id == member
                else el
                for el in doc.elements
            ]
        return UngroupOp(group_id=op.group.id)

    if isinstance(op, UngroupOp):
        group = doc.group(op.group_id)
        for member in group.element_ids:
            if doc.has_element(member):
                element = doc.element(member)
                doc.elements = [
                    element.model_copy(update={"group_id": None})
                    if el.id == member
                    else el
                    for el in doc.elements
                ]
        doc.groups = [item for item in doc.groups if item.id != op.group_id]
        return CreateGroupOp(group=group)

    if isinstance(op, SetViewportOp):
        previous = SetViewportOp(
            zoom=doc.viewport.zoom, x=doc.viewport.x, y=doc.viewport.y
        )
        doc.viewport = Viewport(
            zoom=op.zoom if op.zoom is not None else doc.viewport.zoom,
            x=op.x if op.x is not None else doc.viewport.x,
            y=op.y if op.y is not None else doc.viewport.y,
            selected_ids=list(doc.viewport.selected_ids),
        )
        return previous

    if isinstance(op, SetSelectionOp):
        previous_selection = list(doc.viewport.selected_ids)
        for element_id in op.element_ids:
            doc.element(element_id)
        doc.viewport = doc.viewport.model_copy(
            update={"selected_ids": list(op.element_ids)}
        )
        return SetSelectionOp(element_ids=previous_selection)

    if isinstance(op, SetTitleOp):
        previous_title = doc.metadata.title
        doc.metadata = doc.metadata.model_copy(update={"title": op.title})
        return SetTitleOp(title=previous_title)

    raise VisualDocumentError(
        f"unsupported op '{getattr(op, 'op', type(op).__name__)}'", code="unsupported_op"
    )


class _MultiOp:
    """Internal helper so a single op can invert into several ops."""

    def __init__(self, ops: list[Any]):
        self.ops = ops


def _flatten(inverses: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in inverses:
        if isinstance(item, _MultiOp):
            out.extend(item.ops)
        else:
            out.append(item)
    return out


def parse_ops(raw: list[dict[str, Any]] | list[Any]) -> list[Any]:
    """Validate a raw op list coming from an agent tool call or the client."""

    class _OpEnvelope(_Base):
        op: Op

    parsed: list[Any] = []
    for index, item in enumerate(raw):
        if isinstance(item, BaseModel):
            parsed.append(item)
            continue
        try:
            parsed.append(_OpEnvelope.model_validate({"op": item}).op)
        except ValidationError as exc:
            first = exc.errors()[0]
            raise VisualDocumentError(
                f"invalid op at index {index}: {first['msg']}",
                code="invalid_op",
                path=".".join(str(p) for p in first["loc"]),
            ) from exc
    return parsed


def apply_commit(
    doc: VisualDocument,
    ops: list[Any] | list[dict[str, Any]],
    *,
    author: str,
    author_kind: Literal["user", "agent", "system"] = "user",
    label: str = "edit",
) -> tuple[VisualDocument, Commit]:
    """Apply ops atomically as one new revision.

    Returns a new document (the input is never mutated) and the resulting commit,
    which carries the inverse ops so undo/redo and agent revert share one path.
    """

    parsed = parse_ops(list(ops))
    if not parsed:
        raise VisualDocumentError("commit contains no ops", code="empty_commit")

    working = doc.model_copy(deep=True)
    inverses: list[Any] = []
    for op in parsed:
        inverses.append(_apply_op(working, op))

    inverse_ops = list(reversed(_flatten(inverses)))

    commit = Commit(
        id=new_id("cmt"),
        revision=doc.metadata.revision + 1,
        at=_now(),
        author=author,
        author_kind=author_kind,
        label=label,
        ops=parsed,
        inverse_ops=inverse_ops,
    )

    working.metadata = working.metadata.model_copy(
        update={
            "revision": commit.revision,
            "updated_at": commit.at,
            "updated_by": author,
        }
    )
    working.history = (working.history + [commit])[-MAX_HISTORY:]
    working.redo_stack = []

    try:
        validated = VisualDocument.model_validate(working.model_dump())
    except ValidationError as exc:
        first = exc.errors()[0]
        raise VisualDocumentError(
            f"commit rejected: {first['msg']}",
            code="integrity",
            path=".".join(str(p) for p in first["loc"]),
        ) from exc
    return validated, commit


def undo(doc: VisualDocument, *, author: str) -> tuple[VisualDocument, Commit | None]:
    """Undo the most recent commit by applying its inverse ops."""
    if not doc.history:
        return doc, None
    last = doc.history[-1]
    trimmed = doc.model_copy(deep=True)
    trimmed.history = trimmed.history[:-1]
    updated, _ = apply_commit(
        trimmed,
        [op.model_copy(deep=True) for op in last.inverse_ops],
        author=author,
        author_kind="system",
        label=f"undo:{last.label}",
    )
    # The undo itself is not part of the undo stack; it feeds redo instead.
    updated.history = trimmed.history
    updated.redo_stack = (doc.redo_stack + [last])[-MAX_HISTORY:]
    return VisualDocument.model_validate(updated.model_dump()), last


def redo(doc: VisualDocument, *, author: str) -> tuple[VisualDocument, Commit | None]:
    """Re-apply the most recently undone commit."""
    if not doc.redo_stack:
        return doc, None
    entry = doc.redo_stack[-1]
    base = doc.model_copy(deep=True)
    base.redo_stack = base.redo_stack[:-1]
    updated, commit = apply_commit(
        base,
        [op.model_copy(deep=True) for op in entry.ops],
        author=author,
        author_kind="system",
        label=f"redo:{entry.label}",
    )
    updated.redo_stack = base.redo_stack
    return VisualDocument.model_validate(updated.model_dump()), commit


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------

DEFAULT_LAYERS = (
    ("layer_background", "Background", 0, "background"),
    ("layer_semantic", "Diagram", 1, "semantic"),
    ("layer_data", "Data", 2, "data"),
    ("layer_annotation", "Annotations", 3, "annotation"),
    ("layer_freeform", "Freeform", 4, "freeform"),
)


def new_document(
    *,
    project_id: str,
    folder_id: str,
    title: str,
    document_id: str | None = None,
    session_id: str | None = None,
    created_by: str | None = None,
    source_table_ids: list[str] | None = None,
) -> VisualDocument:
    """Create an empty document with the standard layer stack."""
    return VisualDocument(
        metadata=DocumentMetadata(
            id=document_id or new_id("vdoc"),
            project_id=project_id,
            folder_id=folder_id,
            session_id=session_id,
            title=title,
            created_by=created_by,
            source_table_ids=source_table_ids or [],
        ),
        layers=[
            Layer(id=layer_id, name=name, index=index, kind=kind)  # type: ignore[arg-type]
            for layer_id, name, index, kind in DEFAULT_LAYERS
        ],
    )


__all__ = [
    "SCHEMA_VERSION",
    "CANVAS_MIN",
    "CANVAS_MAX",
    "MIN_ELEMENT_SIZE",
    "MAX_ELEMENT_SIZE",
    "MIN_ZOOM",
    "MAX_ZOOM",
    "MAX_ELEMENTS",
    "MAX_HISTORY",
    "VisualDocumentError",
    "StyleTokens",
    "Point",
    "ChartDataPoint",
    "Rect",
    "Provenance",
    "ProvenanceFilter",
    "Metric",
    "ElementMeta",
    "NodeElement",
    "EdgeElement",
    "ChartElement",
    "KpiElement",
    "TableElement",
    "TableColumn",
    "GanttElement",
    "GanttBar",
    "TextElement",
    "ShapeElement",
    "PathElement",
    "ImageElement",
    "LegendElement",
    "LegendEntry",
    "Element",
    "Layer",
    "Group",
    "Viewport",
    "DocumentMetadata",
    "Commit",
    "Op",
    "AddElementOp",
    "RemoveElementOp",
    "UpdateElementOp",
    "MoveElementsOp",
    "ResizeElementOp",
    "SetStyleOp",
    "SetLayerOp",
    "ReorderElementOp",
    "AddLayerOp",
    "UpdateLayerOp",
    "RemoveLayerOp",
    "CreateGroupOp",
    "UngroupOp",
    "SetViewportOp",
    "SetSelectionOp",
    "SetTitleOp",
    "VisualDocument",
    "apply_commit",
    "parse_ops",
    "undo",
    "redo",
    "new_document",
    "new_id",
    "DEFAULT_LAYERS",
    "GEOMETRIC_TYPES",
    "DATA_TYPES",
]
