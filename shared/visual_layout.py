"""Deterministic layout and readability passes for Visual Documents.

The agent never guesses coordinates. It calls ``apply_layout`` with an algorithm
name, and this module produces the geometry as a list of ops. Everything here is
pure and deterministic: the same document plus the same options always yields the
same coordinates, which keeps visual regression tests stable.

Algorithms
----------
``layered``   Sugiyama-style layered DAG for flowcharts and process maps. Longest
              path layering, barycentre ordering, median alignment. Handles cycles
              (rework loops) by temporarily reversing back edges.
``tree``      Tidy top-down tree for decision trees and org charts.
``grid``      Row-major grid for dashboards, KPI walls, and unconnected elements.
``timeline``  Single-axis chronological lanes for milestones.
``radial``    Ring layout for dependency/network overviews.

Readability
-----------
``check_readability`` reports overlaps, out-of-bounds elements, crowding, and
disconnected nodes so a commit can be rejected or auto-fixed before it is shown.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Literal

from shared.visual_document import (
    CANVAS_MAX,
    CANVAS_MIN,
    GEOMETRIC_TYPES,
    EdgeElement,
    MoveElementsOp,
    Rect,
    ResizeElementOp,
    UpdateElementOp,
    VisualDocument,
    VisualDocumentError,
)

LayoutName = Literal["layered", "tree", "grid", "timeline", "radial"]
Direction = Literal["right", "down", "left", "up"]

DEFAULT_NODE_W = 200.0
DEFAULT_NODE_H = 76.0
MIN_GAP = 24.0


class LayoutOptions:
    """Layout knobs. Defaults are tuned for readable process maps."""

    __slots__ = (
        "algorithm",
        "direction",
        "node_spacing",
        "rank_spacing",
        "origin_x",
        "origin_y",
        "columns",
        "normalize_size",
        "element_ids",
    )

    def __init__(
        self,
        algorithm: LayoutName = "layered",
        *,
        direction: Direction = "right",
        node_spacing: float = 56.0,
        rank_spacing: float = 140.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        columns: int | None = None,
        normalize_size: bool = True,
        element_ids: list[str] | None = None,
    ):
        if algorithm not in ("layered", "tree", "grid", "timeline", "radial"):
            raise VisualDocumentError(
                f"unknown layout algorithm '{algorithm}'", code="unknown_layout"
            )
        if direction not in ("right", "down", "left", "up"):
            raise VisualDocumentError(
                f"unknown layout direction '{direction}'", code="unknown_direction"
            )
        self.algorithm = algorithm
        self.direction = direction
        self.node_spacing = max(MIN_GAP, float(node_spacing))
        self.rank_spacing = max(MIN_GAP, float(rank_spacing))
        self.origin_x = float(origin_x)
        self.origin_y = float(origin_y)
        self.columns = columns
        self.normalize_size = normalize_size
        self.element_ids = element_ids


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def _laid_out_elements(doc: VisualDocument, options: LayoutOptions) -> list[Any]:
    """Elements eligible for layout: geometric, visible, unlocked."""
    wanted = set(options.element_ids) if options.element_ids else None
    out = []
    for el in doc.elements:
        if el.type not in GEOMETRIC_TYPES:
            continue
        if el.type == "path":
            continue
        if el.locked or el.hidden:
            continue
        if wanted is not None and el.id not in wanted:
            continue
        out.append(el)
    return sorted(out, key=lambda e: e.id)


def _edges(doc: VisualDocument, ids: set[str]) -> list[tuple[str, str]]:
    pairs = []
    for el in doc.elements:
        if isinstance(el, EdgeElement) and el.source_id in ids and el.target_id in ids:
            pairs.append((el.source_id, el.target_id))
    return sorted(set(pairs))


def _break_cycles(nodes: list[str], edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return an acyclic edge set by reversing edges that close a cycle.

    Deterministic: nodes are visited in sorted order via depth-first search, and
    any edge pointing back at a node on the current stack is dropped from the
    layering pass (it is still drawn, e.g. a rework loop).
    """
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)

    state: dict[str, int] = {node: 0 for node in nodes}  # 0 new, 1 open, 2 done
    back_edges: set[tuple[str, str]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        for target in sorted(adjacency.get(node, [])):
            if state.get(target, 0) == 1:
                back_edges.add((node, target))
            elif state.get(target, 0) == 0:
                visit(target)
        state[node] = 2

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            visit(node)

    return [edge for edge in edges if edge not in back_edges]


def _rank_nodes(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Longest-path layering on an acyclic edge set."""
    incoming: dict[str, list[str]] = {node: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target in edges:
        outgoing[source].append(target)
        incoming[target].append(source)

    rank = {node: 0 for node in nodes}
    # Kahn order, then relax forward. Nodes in cycles that survived removal are
    # appended at the end so the loop always terminates.
    pending = [node for node in sorted(nodes) if not incoming[node]]
    remaining = {node: len(incoming[node]) for node in nodes}
    order: list[str] = []
    while pending:
        node = pending.pop(0)
        order.append(node)
        for target in sorted(outgoing[node]):
            remaining[target] -= 1
            if remaining[target] == 0:
                pending.append(target)
    order.extend(node for node in sorted(nodes) if node not in set(order))

    for node in order:
        for target in sorted(outgoing[node]):
            rank[target] = max(rank[target], rank[node] + 1)
    return rank


def _order_within_ranks(
    ranks: dict[str, int], edges: list[tuple[str, str]]
) -> dict[int, list[str]]:
    """Barycentre ordering: two sweeps, deterministic tie-breaks by id."""
    layers: dict[int, list[str]] = defaultdict(list)
    for node, rank in sorted(ranks.items()):
        layers[rank].append(node)

    predecessors: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        predecessors[target].append(source)

    for rank in sorted(layers)[1:]:
        previous_index = {node: i for i, node in enumerate(layers[rank - 1])}

        def barycentre(node: str) -> tuple[float, str]:
            parents = [previous_index[p] for p in predecessors.get(node, []) if p in previous_index]
            return (sum(parents) / len(parents) if parents else math.inf, node)

        layers[rank] = sorted(layers[rank], key=barycentre)
    return layers


# ---------------------------------------------------------------------------
# Algorithms - each returns {element_id: Rect}
# ---------------------------------------------------------------------------


def _size_for(element: Any, options: LayoutOptions) -> tuple[float, float]:
    rect: Rect = element.rect
    if not options.normalize_size:
        return rect.w, rect.h
    if element.type == "node":
        return max(rect.w, DEFAULT_NODE_W), max(rect.h, DEFAULT_NODE_H)
    return rect.w, rect.h


def _layered(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    elements = _laid_out_elements(doc, options)
    if not elements:
        return {}
    by_id = {el.id: el for el in elements}
    ids = set(by_id)
    edges = _edges(doc, ids)
    acyclic = _break_cycles(sorted(ids), edges)
    ranks = _rank_nodes(sorted(ids), acyclic)
    layers = _order_within_ranks(ranks, acyclic)

    horizontal = options.direction in ("right", "left")
    placements: dict[str, Rect] = {}

    # Cross-axis extent per layer, so layers are centred against each other.
    layer_extent: dict[int, float] = {}
    for rank, members in layers.items():
        sizes = [_size_for(by_id[m], options) for m in members]
        cross = [h if horizontal else w for w, h in sizes]
        layer_extent[rank] = sum(cross) + options.node_spacing * (len(members) - 1)
    widest = max(layer_extent.values()) if layer_extent else 0.0

    main_cursor = 0.0
    for rank in sorted(layers):
        members = layers[rank]
        sizes = {m: _size_for(by_id[m], options) for m in members}
        main_extent = max(
            (w if horizontal else h) for w, h in sizes.values()
        )
        cross_cursor = (widest - layer_extent[rank]) / 2.0
        for member in members:
            w, h = sizes[member]
            if horizontal:
                x = main_cursor + (main_extent - w) / 2.0
                y = cross_cursor
                cross_cursor += h + options.node_spacing
            else:
                x = cross_cursor
                y = main_cursor + (main_extent - h) / 2.0
                cross_cursor += w + options.node_spacing
            placements[member] = Rect(x=x, y=y, w=w, h=h)
        main_cursor += main_extent + options.rank_spacing

    return _finalize(placements, options)


def _tree(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    """Tidy tree: leaves packed on the cross axis, parents centred over children."""
    elements = _laid_out_elements(doc, options)
    if not elements:
        return {}
    by_id = {el.id: el for el in elements}
    ids = set(by_id)
    edges = _break_cycles(sorted(ids), _edges(doc, ids))

    children: dict[str, list[str]] = defaultdict(list)
    has_parent: set[str] = set()
    for source, target in edges:
        children[source].append(target)
        has_parent.add(target)
    roots = [node for node in sorted(ids) if node not in has_parent] or sorted(ids)

    horizontal = options.direction in ("right", "left")
    placements: dict[str, Rect] = {}
    cursor = [0.0]
    visited: set[str] = set()

    def place(node: str, depth: int) -> float:
        if node in visited:
            return cursor[0]
        visited.add(node)
        w, h = _size_for(by_id[node], options)
        kids = [k for k in sorted(children.get(node, [])) if k not in visited]
        if not kids:
            centre = cursor[0] + (h if horizontal else w) / 2.0
            cursor[0] += (h if horizontal else w) + options.node_spacing
        else:
            centres = [place(kid, depth + 1) for kid in kids]
            centre = (min(centres) + max(centres)) / 2.0
        main = depth * (options.rank_spacing + (DEFAULT_NODE_W if horizontal else DEFAULT_NODE_H))
        if horizontal:
            placements[node] = Rect(x=main, y=centre - h / 2.0, w=w, h=h)
        else:
            placements[node] = Rect(x=centre - w / 2.0, y=main, w=w, h=h)
        return centre

    for root in roots:
        place(root, 0)
    for orphan in sorted(ids - visited):
        place(orphan, 0)

    return _finalize(placements, options)


def _grid(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    elements = _laid_out_elements(doc, options)
    if not elements:
        return {}
    count = len(elements)
    columns = options.columns or max(1, int(math.ceil(math.sqrt(count))))
    sizes = [_size_for(el, options) for el in elements]
    col_width = max(w for w, _ in sizes)
    row_height = max(h for _, h in sizes)

    placements: dict[str, Rect] = {}
    for index, (element, (w, h)) in enumerate(zip(elements, sizes)):
        row, col = divmod(index, columns)
        x = col * (col_width + options.node_spacing) + (col_width - w) / 2.0
        y = row * (row_height + options.node_spacing) + (row_height - h) / 2.0
        placements[element.id] = Rect(x=x, y=y, w=w, h=h)
    return _finalize(placements, options)


def _timeline(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    """One horizontal axis; alternating cross-axis offsets avoid label collisions."""
    elements = _laid_out_elements(doc, options)
    if not elements:
        return {}
    by_id = {el.id: el for el in elements}
    ids = set(by_id)
    ranks = _rank_nodes(sorted(ids), _break_cycles(sorted(ids), _edges(doc, ids)))
    ordered = sorted(ids, key=lambda i: (ranks.get(i, 0), i))

    placements: dict[str, Rect] = {}
    cursor = 0.0
    for index, element_id in enumerate(ordered):
        w, h = _size_for(by_id[element_id], options)
        offset = 0.0 if index % 2 == 0 else (h + options.node_spacing)
        placements[element_id] = Rect(x=cursor, y=offset, w=w, h=h)
        cursor += w + options.node_spacing
    return _finalize(placements, options)


def _radial(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    elements = _laid_out_elements(doc, options)
    if not elements:
        return {}
    count = len(elements)
    sizes = [_size_for(el, options) for el in elements]
    largest = max(max(w, h) for w, h in sizes)
    radius = max(
        largest * 1.5,
        (count * (largest + options.node_spacing)) / (2 * math.pi),
    )
    placements: dict[str, Rect] = {}
    for index, (element, (w, h)) in enumerate(zip(elements, sizes)):
        angle = (2 * math.pi * index) / count - math.pi / 2
        cx = radius + radius * math.cos(angle)
        cy = radius + radius * math.sin(angle)
        placements[element.id] = Rect(x=cx - w / 2.0, y=cy - h / 2.0, w=w, h=h)
    return _finalize(placements, options)


def _finalize(placements: dict[str, Rect], options: LayoutOptions) -> dict[str, Rect]:
    """Shift to the requested origin and clamp into the virtual coordinate space."""
    if not placements:
        return placements
    min_x = min(rect.x for rect in placements.values())
    min_y = min(rect.y for rect in placements.values())
    shifted: dict[str, Rect] = {}
    for element_id, rect in placements.items():
        x = _clamp(rect.x - min_x + options.origin_x)
        y = _clamp(rect.y - min_y + options.origin_y)
        shifted[element_id] = Rect(x=round(x, 2), y=round(y, 2), w=rect.w, h=rect.h)
    return shifted


def _clamp(value: float) -> float:
    return max(CANVAS_MIN, min(CANVAS_MAX, value))


_ALGORITHMS = {
    "layered": _layered,
    "tree": _tree,
    "grid": _grid,
    "timeline": _timeline,
    "radial": _radial,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_layout(doc: VisualDocument, options: LayoutOptions) -> dict[str, Rect]:
    return _ALGORITHMS[options.algorithm](doc, options)


def layout_ops(doc: VisualDocument, options: LayoutOptions) -> list[Any]:
    """Layout as a list of ops, so it commits through the normal path (and undoes)."""
    placements = compute_layout(doc, options)
    ops: list[Any] = []
    for element_id in sorted(placements):
        target = placements[element_id]
        current: Rect = doc.element(element_id).rect  # type: ignore[attr-defined]
        if (current.w, current.h) != (target.w, target.h):
            ops.append(ResizeElementOp(element_id=element_id, rect=target))
        elif (round(current.x, 2), round(current.y, 2)) != (target.x, target.y):
            ops.append(
                UpdateElementOp(
                    element_id=element_id,
                    patch={"rect": target.model_dump()},
                )
            )
    return ops


def align_ops(
    doc: VisualDocument,
    element_ids: list[str],
    axis: Literal["left", "right", "top", "bottom", "center-x", "center-y"],
) -> list[Any]:
    """Align elements on one edge or axis."""
    rects: dict[str, Rect] = {}
    for element_id in element_ids:
        element = doc.element(element_id)
        if element.type not in GEOMETRIC_TYPES or element.type == "path":
            continue
        rects[element_id] = element.rect  # type: ignore[attr-defined]
    if len(rects) < 2:
        return []

    if axis == "left":
        target = min(r.x for r in rects.values())
        offsets = {i: (target - r.x, 0.0) for i, r in rects.items()}
    elif axis == "right":
        target = max(r.x + r.w for r in rects.values())
        offsets = {i: (target - (r.x + r.w), 0.0) for i, r in rects.items()}
    elif axis == "top":
        target = min(r.y for r in rects.values())
        offsets = {i: (0.0, target - r.y) for i, r in rects.items()}
    elif axis == "bottom":
        target = max(r.y + r.h for r in rects.values())
        offsets = {i: (0.0, target - (r.y + r.h)) for i, r in rects.items()}
    elif axis == "center-x":
        target = sum(r.x + r.w / 2 for r in rects.values()) / len(rects)
        offsets = {i: (target - (r.x + r.w / 2), 0.0) for i, r in rects.items()}
    else:
        target = sum(r.y + r.h / 2 for r in rects.values()) / len(rects)
        offsets = {i: (0.0, target - (r.y + r.h / 2)) for i, r in rects.items()}

    return [
        MoveElementsOp(element_ids=[element_id], dx=round(dx, 2), dy=round(dy, 2))
        for element_id, (dx, dy) in sorted(offsets.items())
        if abs(dx) > 0.01 or abs(dy) > 0.01
    ]


def distribute_ops(
    doc: VisualDocument, element_ids: list[str], axis: Literal["x", "y"]
) -> list[Any]:
    """Even spacing between the first and last element along one axis."""
    rects: dict[str, Rect] = {}
    for element_id in element_ids:
        element = doc.element(element_id)
        if element.type in GEOMETRIC_TYPES and element.type != "path":
            rects[element_id] = element.rect  # type: ignore[attr-defined]
    if len(rects) < 3:
        return []

    key = (lambda item: item[1].x) if axis == "x" else (lambda item: item[1].y)
    ordered = sorted(rects.items(), key=key)
    first, last = ordered[0][1], ordered[-1][1]
    if axis == "x":
        span = (last.x + last.w) - first.x
        used = sum(r.w for _, r in ordered)
    else:
        span = (last.y + last.h) - first.y
        used = sum(r.h for _, r in ordered)
    gap = max(MIN_GAP, (span - used) / (len(ordered) - 1))

    ops: list[Any] = []
    cursor = first.x if axis == "x" else first.y
    for element_id, rect in ordered:
        if axis == "x":
            dx, dy = cursor - rect.x, 0.0
            cursor += rect.w + gap
        else:
            dx, dy = 0.0, cursor - rect.y
            cursor += rect.h + gap
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            ops.append(
                MoveElementsOp(element_ids=[element_id], dx=round(dx, 2), dy=round(dy, 2))
            )
    return ops


# ---------------------------------------------------------------------------
# Readability
# ---------------------------------------------------------------------------


def content_bounds(doc: VisualDocument) -> dict[str, float] | None:
    """Bounding box of all visible content, used by ``fit_view``."""
    xs: list[float] = []
    ys: list[float] = []
    for el in doc.elements:
        if el.hidden:
            continue
        if el.type == "path":
            xs.extend(p.x for p in el.points)
            ys.extend(p.y for p in el.points)
        elif el.type in GEOMETRIC_TYPES:
            rect: Rect = el.rect  # type: ignore[attr-defined]
            xs.extend([rect.x, rect.x + rect.w])
            ys.extend([rect.y, rect.y + rect.h])
    if not xs or not ys:
        return None
    return {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)}


def _overlap_area(a: Rect, b: Rect) -> float:
    dx = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    dy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return dx * dy if dx > 0 and dy > 0 else 0.0


def check_readability(
    doc: VisualDocument, *, min_gap: float = MIN_GAP
) -> dict[str, Any]:
    """Detect overlaps, crowding, and disconnected nodes.

    Returned as data (not an exception) so a tool can decide whether to auto-fix
    with a layout pass or surface the warning in the agent activity trail.
    """
    rects: dict[str, Rect] = {}
    for el in doc.elements:
        if el.hidden or el.type not in GEOMETRIC_TYPES or el.type == "path":
            continue
        rects[el.id] = el.rect  # type: ignore[attr-defined]

    overlaps: list[dict[str, Any]] = []
    crowded: list[dict[str, Any]] = []
    ordered = sorted(rects.items())
    for index, (id_a, rect_a) in enumerate(ordered):
        for id_b, rect_b in ordered[index + 1 :]:
            # Nested subflow children are allowed to sit inside their parent.
            if _is_parent_of(doc, id_a, id_b) or _is_parent_of(doc, id_b, id_a):
                continue
            area = _overlap_area(rect_a, rect_b)
            if area > 1.0:
                overlaps.append(
                    {"a": id_a, "b": id_b, "area": round(area, 2)}
                )
                continue
            gap = _gap_between(rect_a, rect_b)
            if gap is not None and gap < min_gap:
                crowded.append({"a": id_a, "b": id_b, "gap": round(gap, 2)})

    out_of_bounds = [
        element_id
        for element_id, rect in ordered
        if rect.x < CANVAS_MIN
        or rect.y < CANVAS_MIN
        or rect.x + rect.w > CANVAS_MAX
        or rect.y + rect.h > CANVAS_MAX
    ]

    connected: set[str] = set()
    edge_count = 0
    for el in doc.elements:
        if isinstance(el, EdgeElement):
            edge_count += 1
            connected.add(el.source_id)
            connected.add(el.target_id)
    disconnected = sorted(
        el.id
        for el in doc.elements
        if el.type == "node" and el.id not in connected
    ) if edge_count else []

    missing_labels = sorted(
        el.id for el in doc.elements if not el.accessible_label.strip()
    )

    return {
        "ok": not overlaps and not out_of_bounds and not missing_labels,
        "overlaps": overlaps,
        "crowded": crowded,
        "out_of_bounds": out_of_bounds,
        "disconnected_nodes": disconnected,
        "missing_labels": missing_labels,
        "element_count": len(doc.elements),
        "bounds": content_bounds(doc),
    }


def _gap_between(a: Rect, b: Rect) -> float | None:
    """Edge-to-edge gap when two rects share a row or column, else ``None``."""
    horizontal_overlap = min(a.x + a.w, b.x + b.w) - max(a.x, b.x) > 0
    vertical_overlap = min(a.y + a.h, b.y + b.h) - max(a.y, b.y) > 0
    if vertical_overlap:
        return max(a.x, b.x) - min(a.x + a.w, b.x + b.w)
    if horizontal_overlap:
        return max(a.y, b.y) - min(a.y + a.h, b.y + b.h)
    return None


def _is_parent_of(doc: VisualDocument, parent_id: str, child_id: str) -> bool:
    try:
        child = doc.element(child_id)
    except VisualDocumentError:
        return False
    return getattr(child, "parent_id", None) == parent_id


def summarize(doc: VisualDocument) -> dict[str, Any]:
    """Compact description of a canvas for the agent's ``summarize_canvas`` tool."""
    counts: dict[str, int] = defaultdict(int)
    sources: set[str] = set()
    for el in doc.elements:
        counts[el.type] += 1
        provenance = getattr(el, "provenance", None)
        if provenance is not None:
            sources.add(provenance.source_table_id)
    return {
        "document_id": doc.metadata.id,
        "title": doc.metadata.title,
        "revision": doc.metadata.revision,
        "element_counts": dict(sorted(counts.items())),
        "layers": [
            {"id": layer.id, "name": layer.name, "visible": layer.visible}
            for layer in sorted(doc.layers, key=lambda item: item.index)
        ],
        "groups": [{"id": g.id, "name": g.name, "size": len(g.element_ids)} for g in doc.groups],
        "source_tables": sorted(sources),
        "bounds": content_bounds(doc),
        "readability": check_readability(doc),
    }


def iter_layout_names() -> Iterable[str]:
    return tuple(_ALGORITHMS)


__all__ = [
    "LayoutOptions",
    "compute_layout",
    "layout_ops",
    "align_ops",
    "distribute_ops",
    "check_readability",
    "content_bounds",
    "summarize",
    "iter_layout_names",
    "DEFAULT_NODE_W",
    "DEFAULT_NODE_H",
]
