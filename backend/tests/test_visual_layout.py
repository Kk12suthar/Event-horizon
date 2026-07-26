"""Tests for the deterministic layout engine and readability passes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.visual_document import (  # noqa: E402
    AddElementOp,
    EdgeElement,
    NodeElement,
    Rect,
    VisualDocument,
    apply_commit,
    new_document,
)
from shared.visual_layout import (  # noqa: E402
    LayoutOptions,
    align_ops,
    check_readability,
    compute_layout,
    content_bounds,
    distribute_ops,
    layout_ops,
    summarize,
)

SEMANTIC = "layer_semantic"


def build(nodes: list[str], edges: list[tuple[str, str]]) -> VisualDocument:
    doc = new_document(
        project_id="p", folder_id="f", title="Layout", document_id="vdoc_layout"
    )
    ops: list = []
    for index, node_id in enumerate(nodes):
        ops.append(
            AddElementOp(
                element=NodeElement(
                    id=node_id,
                    layer_id=SEMANTIC,
                    rect=Rect(x=float(index * 5), y=0.0, w=200, h=76),
                    label=node_id,
                )
            )
        )
    for source, target in edges:
        ops.append(
            AddElementOp(
                element=EdgeElement(
                    id=f"edge_{source}_{target}",
                    layer_id=SEMANTIC,
                    source_id=source,
                    target_id=target,
                )
            )
        )
    doc, _ = apply_commit(doc, ops, author="test")
    return doc


class TestLayeredLayout(unittest.TestCase):
    def test_ranks_follow_edge_direction(self):
        doc = build(["a", "b", "c"], [("a", "b"), ("b", "c")])
        placed = compute_layout(doc, LayoutOptions("layered", direction="right"))
        self.assertLess(placed["a"].x, placed["b"].x)
        self.assertLess(placed["b"].x, placed["c"].x)

    def test_siblings_share_a_rank_and_do_not_overlap(self):
        doc = build(["root", "b", "c"], [("root", "b"), ("root", "c")])
        placed = compute_layout(doc, LayoutOptions("layered"))
        self.assertAlmostEqual(placed["b"].x, placed["c"].x, places=2)
        gap = abs(placed["b"].y - placed["c"].y)
        self.assertGreaterEqual(gap, 76.0)

    def test_rework_loop_does_not_break_layering(self):
        # a -> b -> c -> b is a rework loop; layering must still terminate.
        doc = build(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "b")])
        placed = compute_layout(doc, LayoutOptions("layered"))
        self.assertEqual(len(placed), 3)
        self.assertLess(placed["a"].x, placed["c"].x)

    def test_layout_is_deterministic(self):
        doc = build(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
        first = compute_layout(doc, LayoutOptions("layered"))
        second = compute_layout(doc, LayoutOptions("layered"))
        self.assertEqual(
            {k: v.model_dump() for k, v in first.items()},
            {k: v.model_dump() for k, v in second.items()},
        )

    def test_down_direction_stacks_ranks_vertically(self):
        doc = build(["a", "b"], [("a", "b")])
        placed = compute_layout(doc, LayoutOptions("layered", direction="down"))
        self.assertLess(placed["a"].y, placed["b"].y)
        self.assertAlmostEqual(placed["a"].x, placed["b"].x, places=2)

    def test_result_has_no_overlaps(self):
        doc = build(
            ["a", "b", "c", "d", "e"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")],
        )
        doc, _ = apply_commit(doc, layout_ops(doc, LayoutOptions("layered")), author="test")
        report = check_readability(doc)
        self.assertEqual(report["overlaps"], [])
        self.assertEqual(report["out_of_bounds"], [])


class TestOtherAlgorithms(unittest.TestCase):
    def test_tree_centres_parent_over_children(self):
        doc = build(["root", "l", "r"], [("root", "l"), ("root", "r")])
        placed = compute_layout(doc, LayoutOptions("tree", direction="down"))
        parent_centre = placed["root"].x + placed["root"].w / 2
        children_centre = (
            (placed["l"].x + placed["l"].w / 2) + (placed["r"].x + placed["r"].w / 2)
        ) / 2
        self.assertAlmostEqual(parent_centre, children_centre, places=1)

    def test_grid_respects_column_count(self):
        doc = build(["a", "b", "c", "d"], [])
        placed = compute_layout(doc, LayoutOptions("grid", columns=2))
        rows = {round(rect.y, 1) for rect in placed.values()}
        columns = {round(rect.x, 1) for rect in placed.values()}
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(columns), 2)

    def test_timeline_advances_along_x(self):
        doc = build(["a", "b", "c"], [("a", "b"), ("b", "c")])
        placed = compute_layout(doc, LayoutOptions("timeline"))
        self.assertLess(placed["a"].x, placed["b"].x)
        self.assertLess(placed["b"].x, placed["c"].x)

    def test_radial_places_all_nodes_on_a_ring(self):
        doc = build(["a", "b", "c", "d"], [])
        placed = compute_layout(doc, LayoutOptions("radial"))
        centres = [(r.x + r.w / 2, r.y + r.h / 2) for r in placed.values()]
        cx = sum(c[0] for c in centres) / len(centres)
        cy = sum(c[1] for c in centres) / len(centres)
        radii = [((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in centres]
        self.assertAlmostEqual(max(radii), min(radii), delta=1.0)

    def test_origin_offset_is_applied(self):
        doc = build(["a", "b"], [("a", "b")])
        placed = compute_layout(
            doc, LayoutOptions("layered", origin_x=500.0, origin_y=250.0)
        )
        self.assertAlmostEqual(min(r.x for r in placed.values()), 500.0, places=2)
        self.assertAlmostEqual(min(r.y for r in placed.values()), 250.0, places=2)


class TestLayoutOps(unittest.TestCase):
    def test_layout_ops_are_committable_and_undoable(self):
        doc = build(["a", "b", "c"], [("a", "b"), ("b", "c")])
        before = {el.id: el.rect.model_dump() for el in doc.elements if el.type == "node"}
        ops = layout_ops(doc, LayoutOptions("layered"))
        self.assertTrue(ops)
        laid_out, commit = apply_commit(doc, ops, author="agent", author_kind="agent")
        after = {el.id: el.rect.model_dump() for el in laid_out.elements if el.type == "node"}
        self.assertNotEqual(before, after)
        restored, _ = apply_commit(laid_out, commit.inverse_ops, author="user")
        self.assertEqual(
            {el.id: el.rect.model_dump() for el in restored.elements if el.type == "node"},
            before,
        )

    def test_layout_ops_are_empty_when_already_laid_out(self):
        doc = build(["a", "b"], [("a", "b")])
        doc, _ = apply_commit(doc, layout_ops(doc, LayoutOptions("layered")), author="t")
        self.assertEqual(layout_ops(doc, LayoutOptions("layered")), [])

    def test_align_left_moves_elements_to_shared_edge(self):
        doc = build(["a", "b"], [])
        doc, _ = apply_commit(doc, align_ops(doc, ["a", "b"], "left"), author="t")
        rects = [el.rect.x for el in doc.elements if el.type == "node"]
        self.assertEqual(len(set(rects)), 1)

    def test_distribute_needs_three_elements(self):
        doc = build(["a", "b"], [])
        self.assertEqual(distribute_ops(doc, ["a", "b"], "x"), [])

    def test_distribute_evens_gaps(self):
        doc = build(["a", "b", "c"], [])
        doc, _ = apply_commit(doc, layout_ops(doc, LayoutOptions("grid", columns=3)), author="t")
        ops = distribute_ops(doc, ["a", "b", "c"], "x")
        doc, _ = apply_commit(doc, ops, author="t") if ops else (doc, None)
        xs = sorted(el.rect.x for el in doc.elements if el.type == "node")
        self.assertAlmostEqual(xs[1] - xs[0], xs[2] - xs[1], places=1)


class TestReadability(unittest.TestCase):
    def test_overlap_is_reported(self):
        doc = new_document(project_id="p", folder_id="f", title="T", document_id="vdoc_r")
        doc, _ = apply_commit(
            doc,
            [
                AddElementOp(
                    element=NodeElement(
                        id="a", layer_id=SEMANTIC, rect=Rect(x=0, y=0, w=200, h=100), label="A"
                    )
                ),
                AddElementOp(
                    element=NodeElement(
                        id="b", layer_id=SEMANTIC, rect=Rect(x=50, y=50, w=200, h=100), label="B"
                    )
                ),
            ],
            author="test",
        )
        report = check_readability(doc)
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["overlaps"]), 1)
        self.assertEqual(report["overlaps"][0]["area"], 150.0 * 50.0)

    def test_crowding_is_reported_separately_from_overlap(self):
        doc = new_document(project_id="p", folder_id="f", title="T", document_id="vdoc_c")
        doc, _ = apply_commit(
            doc,
            [
                AddElementOp(
                    element=NodeElement(
                        id="a", layer_id=SEMANTIC, rect=Rect(x=0, y=0, w=100, h=100), label="A"
                    )
                ),
                AddElementOp(
                    element=NodeElement(
                        id="b", layer_id=SEMANTIC, rect=Rect(x=105, y=0, w=100, h=100), label="B"
                    )
                ),
            ],
            author="test",
        )
        report = check_readability(doc)
        self.assertEqual(report["overlaps"], [])
        self.assertEqual(report["crowded"][0]["gap"], 5.0)

    def test_disconnected_nodes_reported_only_when_edges_exist(self):
        doc = build(["a", "b", "orphan"], [("a", "b")])
        self.assertEqual(check_readability(doc)["disconnected_nodes"], ["orphan"])
        self.assertEqual(check_readability(build(["a", "b"], []))["disconnected_nodes"], [])

    def test_content_bounds_covers_every_element(self):
        doc = build(["a", "b"], [("a", "b")])
        doc, _ = apply_commit(doc, layout_ops(doc, LayoutOptions("layered")), author="t")
        bounds = content_bounds(doc)
        self.assertIsNotNone(bounds)
        assert bounds is not None
        self.assertGreater(bounds["w"], 200)

    def test_summarize_reports_counts_and_readability(self):
        doc = build(["a", "b"], [("a", "b")])
        summary = summarize(doc)
        self.assertEqual(summary["element_counts"], {"edge": 1, "node": 2})
        self.assertEqual(summary["revision"], 1)
        self.assertIn("readability", summary)
        self.assertEqual(len(summary["layers"]), 5)


if __name__ == "__main__":
    unittest.main()
