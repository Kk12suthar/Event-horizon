from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

AGENT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from shared.visual_document import (
    VisualDocument,
    VisualDocumentError,
    apply_commit,
    new_document,
    undo,
)
from shared.visual_layout import check_readability
from tools import canvas_tools


class FakeStore:
    """In-memory stand-in for shared.visual_document_store.

    It is backed by the real schema (``new_document`` / ``apply_commit`` / ``undo``),
    so every assertion below exercises the authoritative validation rules.
    """

    def __init__(self) -> None:
        self.documents: dict[str, VisualDocument] = {}

    # -- store contract ---------------------------------------------------
    def create_document(
        self,
        folder_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        title: str = "Canvas",
        **_: Any,
    ) -> VisualDocument:
        document = new_document(
            project_id=project_id or "project-id",
            folder_id=folder_id or "folder-id",
            session_id=session_id,
            title=title,
            created_by=user_id,
        )
        self.documents[document.metadata.id] = document
        return document

    def load_document(self, document_id: str, **_: Any) -> VisualDocument:
        document = self.documents.get(str(document_id))
        if document is None:
            raise VisualDocumentError(
                f"unknown document '{document_id}'", code="unknown_document"
            )
        return document

    def list_documents(self, folder_id: str | None = None, **_: Any) -> list[VisualDocument]:
        return [
            document
            for document in self.documents.values()
            if folder_id is None or document.metadata.folder_id == folder_id
        ]

    def commit_ops(
        self,
        document_id: str,
        ops: list[Any],
        author: str | None = None,
        author_kind: str = "agent",
        base_revision: int | None = None,
        label: str = "edit",
        **_: Any,
    ) -> tuple[VisualDocument, Any]:
        document = self.load_document(document_id)
        if base_revision is not None and int(base_revision) != document.metadata.revision:
            raise VisualDocumentError(
                f"base_revision {base_revision} is stale", code="revision_conflict"
            )
        updated, commit = apply_commit(
            document,
            ops,
            author=author or "agent",
            author_kind=author_kind,  # type: ignore[arg-type]
            label=label,
        )
        self.documents[str(document_id)] = updated
        return updated, commit

    def undo_document(self, document_id: str, author: str | None = None, **_: Any):
        document = self.load_document(document_id)
        updated, commit = undo(document, author=author or "agent")
        self.documents[str(document_id)] = updated
        return updated, commit


class CanvasToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        patches = [
            patch.object(canvas_tools, "create_document", self.store.create_document),
            patch.object(canvas_tools, "load_document", self.store.load_document),
            patch.object(canvas_tools, "list_documents", self.store.list_documents),
            patch.object(canvas_tools, "commit_ops", self.store.commit_ops),
            patch.object(canvas_tools, "undo_document", self.store.undo_document),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    # -- helpers ----------------------------------------------------------
    def _create(self, title: str = "Order flow") -> str:
        result = canvas_tools.create_canvas(
            folder_id="folder-id", user_id="user-id", session_id="session-id", title=title
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["revision"], 0)
        return result["document_id"]

    def _document(self, document_id: str) -> VisualDocument:
        return self.store.documents[document_id]


class CanvasBasicsTests(CanvasToolTestCase):
    def test_create_then_add_node_and_edge(self) -> None:
        document_id = self._create()

        first = canvas_tools.add_node(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            node_kind="start",
            label="Order received",
        )
        second = canvas_tools.add_node(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            node_kind="task",
            label="Check credit",
            metrics=[{"label": "avg days", "value": 2.5, "format": "decimal"}],
        )
        self.assertNotIn("error", first)
        self.assertNotIn("error", second)
        self.assertEqual(first["element_ids"], ["order_received"])
        self.assertEqual(second["element_ids"], ["check_credit"])
        self.assertEqual(first["artifact"]["artifact_type"], "visual_patch")
        self.assertEqual(first["artifact"]["label"], "canvas_add_node")
        self.assertEqual(first["artifact"]["commit"]["author_kind"], "agent")
        self.assertEqual(second["revision"], 2)

        edge = canvas_tools.add_edge(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            source_id="order_received",
            target_id="check_credit",
            edge_kind="sequence",
            label="always",
        )
        self.assertNotIn("error", edge)
        self.assertEqual(edge["revision"], 3)
        self.assertIn("readability", edge)

        document = self._document(document_id)
        self.assertEqual(
            sorted(element.type for element in document.elements), ["edge", "node", "node"]
        )
        node = document.element("check_credit")
        self.assertEqual(node.metrics[0].label, "avg days")

    def test_add_edge_with_unknown_endpoint_returns_error(self) -> None:
        document_id = self._create()
        result = canvas_tools.add_edge(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            source_id="nope",
            target_id="also_nope",
            edge_kind="sequence",
        )
        self.assertEqual(result["error"], "unknown_element")
        self.assertIn("nope", result["message"])

    def test_missing_document_id_returns_error(self) -> None:
        result = canvas_tools.add_node(
            folder_id="folder-id", user_id="user-id", label="Orphan", node_kind="task"
        )
        self.assertEqual(result["error"], "missing_document_id")

    def test_inspect_and_summarize(self) -> None:
        document_id = self._create()
        canvas_tools.add_node(
            folder_id="folder-id", user_id="user-id", document_id=document_id, label="Intake"
        )

        inspected = canvas_tools.inspect_canvas(
            folder_id="folder-id", user_id="user-id", document_id=document_id
        )
        self.assertEqual(inspected["revision"], 1)
        self.assertEqual([row["id"] for row in inspected["outline"]], ["intake"])
        self.assertEqual(len(inspected["layers"]), 5)
        self.assertEqual(inspected["groups"], [])
        self.assertIn("readability", inspected)

        summarized = canvas_tools.summarize_canvas(
            folder_id="folder-id", user_id="user-id", document_id=document_id
        )
        self.assertEqual(summarized["element_counts"], {"node": 1})

        overlaps = canvas_tools.find_overlaps(
            folder_id="folder-id", user_id="user-id", document_id=document_id
        )
        self.assertEqual(overlaps["overlaps"], [])

        listed = canvas_tools.list_canvases(folder_id="folder-id", user_id="user-id")
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["documents"][0]["document_id"], document_id)


class ProcessMapTests(CanvasToolTestCase):
    NODES = [
        {"label": "Order received", "kind": "start"},
        {"label": "Check credit", "kind": "task"},
        {"label": "Approve order", "kind": "decision"},
        {"label": "Ship order", "kind": "task"},
        {"label": "Closed", "kind": "end"},
    ]
    EDGES = [
        {"source": "Order received", "target": "Check credit"},
        {"source": "Check credit", "target": "Approve order"},
        {"source": "Approve order", "target": "Ship order", "label": "approved"},
        {"source": "Approve order", "target": "Check credit", "kind": "rework", "label": "more info"},
        {"source": "Ship order", "target": "Closed"},
    ]

    def test_process_map_layout_has_no_overlaps(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_process_map(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=self.NODES,
            edges=self.EDGES,
            title="Order to cash",
            direction="right",
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["node_ids"]), len(self.NODES))
        self.assertEqual(len(result["edge_ids"]), len(self.EDGES))
        self.assertEqual(len(result["element_ids"]), len(self.NODES) + len(self.EDGES))
        self.assertGreater(result["revision"], 1)
        self.assertEqual(len(result["artifact"]["commits"]), 2)

        document = self._document(document_id)
        self.assertEqual(document.metadata.title, "Order to cash")
        self.assertEqual(sum(1 for el in document.elements if el.type == "node"), len(self.NODES))
        self.assertEqual(sum(1 for el in document.elements if el.type == "edge"), len(self.EDGES))
        self.assertEqual(check_readability(document)["overlaps"], [])
        self.assertEqual(result["readability"]["overlaps"], [])

        # Geometry is engine-computed, so nodes no longer sit at the origin.
        positions = {el.id: (el.rect.x, el.rect.y) for el in document.elements if el.type == "node"}
        self.assertEqual(len(set(positions.values())), len(self.NODES))
        self.assertEqual(result["node_ids"][0], "order_received")

    def test_process_map_slugs_are_unique(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_process_map(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[{"label": "Review"}, {"label": "Review"}, {"label": "review!"}],
            edges=[{"source": "Review", "target": "review!"}],
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["node_ids"], ["review", "review_2", "review_3"])
        self.assertEqual(len(set(result["node_ids"])), 3)

    def test_process_map_rejects_unknown_edge_endpoint(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_process_map(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[{"label": "Intake"}],
            edges=[{"source": "Intake", "target": "Missing step"}],
        )
        self.assertEqual(result["error"], "unknown_node_ref")

    def test_process_map_requires_nodes(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_process_map(
            folder_id="folder-id", user_id="user-id", document_id=document_id, nodes=[]
        )
        self.assertEqual(result["error"], "empty_nodes")


class VariantPathTests(CanvasToolTestCase):
    def test_variant_paths_render_edges_and_legend(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_variant_paths(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[
                {"label": "Intake", "kind": "start"},
                {"label": "Review", "kind": "task"},
                {"label": "Rework", "kind": "task"},
                {"label": "Done", "kind": "end"},
            ],
            variants=[
                {"label": "Happy path", "path": ["Intake", "Review", "Done"], "case_count": 820, "percentage": 82},
                {"label": "Rework loop", "path": ["Intake", "Review", "Rework", "Done"], "case_count": 180, "percentage": 18},
            ],
            title="Variants of intake",
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["node_ids"]), 4)
        self.assertEqual(len(result["edge_ids"]), 5)
        self.assertEqual(len(result["variants"]), 2)
        self.assertEqual(result["variants"][0]["emphasis"], "highlight")
        self.assertEqual(len(result["artifact"]["commits"]), 3)

        document = self._document(document_id)
        legend = document.element(result["legend_id"])
        self.assertEqual(legend.type, "legend")
        self.assertEqual(len(legend.entries), 2)
        self.assertIn("820 cases", legend.entries[0].label)
        self.assertIn("(18%)", legend.entries[1].label)
        self.assertEqual(check_readability(document)["overlaps"], [])

        emphasised = {
            el.style.emphasis
            for el in document.elements
            if el.id in set(result["variants"][0]["edge_ids"])
        }
        self.assertEqual(emphasised, {"highlight"})

    def test_variant_path_needs_two_steps(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_variant_paths(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[{"label": "Intake"}],
            variants=[{"label": "Short", "path": ["Intake"]}],
        )
        self.assertEqual(result["error"], "invalid_variant_path")


class HighlightTests(CanvasToolTestCase):
    def _process(self) -> tuple[str, dict[str, Any]]:
        document_id = self._create()
        result = canvas_tools.create_process_map(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[{"label": "Intake"}, {"label": "Review"}, {"label": "Done"}],
            edges=[{"source": "Intake", "target": "Review"}, {"source": "Review", "target": "Done"}],
        )
        self.assertNotIn("error", result)
        return document_id, result

    def test_highlight_path_only_changes_style_tokens(self) -> None:
        document_id, created = self._process()
        before = self._document(document_id)
        snapshot = {
            element.id: element.model_dump(exclude={"style", "meta"})
            for element in before.elements
        }

        result = canvas_tools.highlight_path(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["intake", "review"],
            emphasis="highlight",
            dim_others=True,
        )

        self.assertNotIn("error", result)
        self.assertEqual(result["element_ids"], ["intake", "review"])
        after = self._document(document_id)
        self.assertEqual(
            {element.id: element.model_dump(exclude={"style", "meta"}) for element in after.elements},
            snapshot,
        )
        self.assertEqual(after.element("intake").style.emphasis, "highlight")
        self.assertEqual(after.element("review").style.emphasis, "highlight")
        self.assertEqual(after.element("done").style.emphasis, "dim")
        self.assertGreater(result["revision"], created["revision"])

    def test_highlight_rejects_unknown_emphasis(self) -> None:
        document_id, _ = self._process()
        result = canvas_tools.highlight_path(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["intake"],
            emphasis="neon-glow",
        )
        self.assertEqual(result["error"], "invalid_style")
        self.assertEqual(self._document(document_id).element("intake").style.emphasis, "none")

    def test_update_style_rejects_unknown_style_token(self) -> None:
        document_id, created = self._process()
        result = canvas_tools.update_style(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["intake"],
            style={"color": "#ff0000"},
        )
        self.assertEqual(result["error"], "unknown_style_token")
        self.assertIn("color", result["message"])
        self.assertEqual(self._document(document_id).metadata.revision, created["revision"])

    def test_update_style_rejects_invalid_token_value(self) -> None:
        document_id, _ = self._process()
        result = canvas_tools.update_style(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["intake"],
            style={"fill": "hot-pink"},
        )
        self.assertEqual(result["error"], "invalid_style")

    def test_update_style_accepts_tokens(self) -> None:
        document_id, _ = self._process()
        result = canvas_tools.update_style(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["intake"],
            style={"fill": "accent", "corner": "pill"},
        )
        self.assertNotIn("error", result)
        style = self._document(document_id).element("intake").style
        self.assertEqual((style.fill, style.corner), ("accent", "pill"))


class GroundedElementTests(CanvasToolTestCase):
    def test_chart_without_source_table_id_returns_error(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_chart(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            chart_type="bar",
            title="Revenue by region",
            x_field="region",
            y_fields=["revenue"],
            a11y_label="Revenue by region for 2026.",
        )
        self.assertEqual(result["error"], "missing_provenance")
        self.assertIn("source_table_id", result["message"])
        self.assertEqual(self._document(document_id).elements, [])

    def test_chart_without_a11y_label_returns_error(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_chart(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            chart_type="bar",
            title="Revenue by region",
            x_field="region",
            y_fields=["revenue"],
            source_table_id="prepared-sales",
        )
        self.assertEqual(result["error"], "missing_a11y_label")

    def test_chart_with_provenance_is_accepted_and_provenance_survives(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_chart(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            chart_type="column",
            title="Revenue by region",
            x_field="region",
            y_fields=["revenue"],
            source_table_id="prepared-sales",
            transform_revision=4,
            aggregation="sum",
            filters=[{"field": "year", "op": "eq", "value": 2026}],
            a11y_label="Total revenue per region for 2026, summed from prepared-sales.",
        )

        self.assertNotIn("error", result)
        self.assertEqual(result["source_table_id"], "prepared-sales")
        chart = self._document(document_id).element(result["element_ids"][0])
        self.assertEqual(chart.type, "chart")
        self.assertEqual(chart.chart_type, "column")
        self.assertEqual(chart.provenance.source_table_id, "prepared-sales")
        self.assertEqual(chart.provenance.transform_revision, 4)
        self.assertEqual(chart.provenance.aggregation, "sum")
        self.assertEqual(chart.provenance.filters[0].field, "year")
        self.assertEqual(chart.provenance.folder_id, "folder-id")
        self.assertTrue(chart.a11y_label)

        outline = canvas_tools.inspect_canvas(
            folder_id="folder-id", user_id="user-id", document_id=document_id
        )["outline"]
        self.assertEqual(outline[0]["source_table_id"], "prepared-sales")
        self.assertEqual(outline[0]["transform_revision"], 4)

    def test_chart_requires_y_fields(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_chart(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            chart_type="bar",
            title="Revenue",
            x_field="region",
            y_fields=[],
            source_table_id="prepared-sales",
            a11y_label="Revenue by region.",
        )
        self.assertEqual(result["error"], "missing_y_fields")

    def test_kpi_and_gantt_carry_provenance(self) -> None:
        document_id = self._create()
        kpi = canvas_tools.create_kpi(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            label="Total revenue",
            value=1200.5,
            unit="USD",
            format="currency",
            source_table_id="prepared-sales",
            transform_revision=4,
            aggregation="sum",
            a11y_label="Total revenue of 1200.50 USD from prepared-sales.",
            trend="up",
        )
        self.assertNotIn("error", kpi)
        kpi_element = self._document(document_id).element(kpi["element_ids"][0])
        self.assertEqual(kpi_element.metric.value, 1200.5)
        self.assertEqual(kpi_element.metric.format, "currency")
        self.assertEqual(kpi_element.provenance.source_table_id, "prepared-sales")

        gantt = canvas_tools.create_gantt(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            title="Delivery plan",
            bars=[
                {"label": "Design", "lane": "Team A", "start": "2026-01-05", "end": "2026-01-19", "progress": 0.5},
                {"label": "Build", "lane": "Team B", "start": "2026-01-20", "end": "2026-02-10"},
            ],
            source_table_id="prepared-plan",
            a11y_label="Two delivery phases between January and February 2026.",
            time_unit="week",
        )
        self.assertNotIn("error", gantt)
        gantt_element = self._document(document_id).element(gantt["element_ids"][0])
        self.assertEqual([bar.id for bar in gantt_element.bars], ["design", "build"])
        self.assertEqual(gantt_element.provenance.source_table_id, "prepared-plan")
        self.assertEqual(gantt_element.time_unit, "week")
        self.assertEqual(check_readability(self._document(document_id))["overlaps"], [])

    def test_kpi_without_value_returns_error(self) -> None:
        document_id = self._create()
        result = canvas_tools.create_kpi(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            label="Total revenue",
            source_table_id="prepared-sales",
            a11y_label="Total revenue.",
        )
        self.assertEqual(result["error"], "missing_value")


class GeometryTests(CanvasToolTestCase):
    def _grid_canvas(self) -> str:
        document_id = self._create()
        for label in ("Alpha", "Beta", "Gamma"):
            self.assertNotIn(
                "error",
                canvas_tools.add_node(
                    folder_id="folder-id", user_id="user-id", document_id=document_id, label=label
                ),
            )
        return document_id

    def test_apply_layout_with_unknown_algorithm_returns_error(self) -> None:
        document_id = self._grid_canvas()
        result = canvas_tools.apply_layout(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            algorithm="spaghetti",
        )
        self.assertEqual(result["error"], "unknown_layout")
        self.assertIn("spaghetti", result["message"])

    def test_apply_layout_with_unknown_direction_returns_error(self) -> None:
        document_id = self._grid_canvas()
        result = canvas_tools.apply_layout(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            algorithm="grid",
            direction="sideways",
        )
        self.assertEqual(result["error"], "unknown_direction")

    def test_apply_layout_grid_removes_overlaps(self) -> None:
        document_id = self._grid_canvas()
        self.assertNotEqual(check_readability(self._document(document_id))["overlaps"], [])

        result = canvas_tools.apply_layout(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            algorithm="grid",
            columns=3,
        )
        self.assertNotIn("error", result)
        self.assertEqual(sorted(result["element_ids"]), ["alpha", "beta", "gamma"])
        self.assertEqual(result["readability"]["overlaps"], [])

    def test_align_distribute_move_resize_and_delete(self) -> None:
        document_id = self._grid_canvas()
        canvas_tools.apply_layout(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            algorithm="grid",
            columns=3,
        )

        aligned = canvas_tools.align_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha", "beta"],
            axis="top",
        )
        self.assertNotIn("error", aligned)

        distributed = canvas_tools.distribute_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha", "beta", "gamma"],
            axis="x",
        )
        self.assertNotIn("error", distributed)

        before = self._document(document_id).element("alpha").rect
        moved = canvas_tools.move_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha"],
            dx=25,
            dy=-10,
        )
        self.assertNotIn("error", moved)
        after = self._document(document_id).element("alpha").rect
        self.assertAlmostEqual(after.x - before.x, 25.0)
        self.assertAlmostEqual(after.y - before.y, -10.0)

        resized = canvas_tools.resize_element(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_id="alpha",
            width=320,
            height=120,
        )
        self.assertNotIn("error", resized)
        rect = self._document(document_id).element("alpha").rect
        self.assertEqual((rect.w, rect.h), (320.0, 120.0))

        deleted = canvas_tools.delete_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["gamma"],
        )
        self.assertNotIn("error", deleted)
        self.assertFalse(self._document(document_id).has_element("gamma"))

    def test_align_requires_two_elements(self) -> None:
        document_id = self._grid_canvas()
        result = canvas_tools.align_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha"],
            axis="left",
        )
        self.assertEqual(result["error"], "not_enough_elements")

    def test_align_rejects_unknown_axis(self) -> None:
        document_id = self._grid_canvas()
        result = canvas_tools.align_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha", "beta"],
            axis="diagonal",
        )
        self.assertEqual(result["error"], "unknown_axis")

    def test_delete_edge_and_node_together(self) -> None:
        document_id = self._create()
        created = canvas_tools.create_process_map(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            nodes=[{"label": "Intake"}, {"label": "Review"}],
            edges=[{"source": "Intake", "target": "Review"}],
        )
        result = canvas_tools.delete_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["review", created["edge_ids"][0]],
        )
        self.assertNotIn("error", result)
        document = self._document(document_id)
        self.assertFalse(document.has_element("review"))
        self.assertTrue(document.has_element("intake"))

    def test_group_and_undo(self) -> None:
        document_id = self._grid_canvas()
        grouped = canvas_tools.group_elements(
            folder_id="folder-id",
            user_id="user-id",
            document_id=document_id,
            element_ids=["alpha", "beta"],
            name="Intake stage",
        )
        self.assertNotIn("error", grouped)
        self.assertEqual(len(self._document(document_id).groups), 1)

        undone = canvas_tools.undo_canvas(
            folder_id="folder-id", user_id="user-id", document_id=document_id
        )
        self.assertNotIn("error", undone)
        self.assertEqual(undone["undone"], "canvas_group_elements")
        self.assertEqual(self._document(document_id).groups, [])


class RegistryTests(unittest.TestCase):
    def test_every_spec_is_well_formed(self) -> None:
        names: list[str] = []
        for spec in canvas_tools.CANVAS_TOOLS:
            names.append(spec.name)
            self.assertTrue(spec.name.startswith("canvas_"), spec.name)
            self.assertTrue(spec.title.strip(), spec.name)
            self.assertTrue(spec.description.strip(), spec.name)
            self.assertIsInstance(spec.parameters, dict)
            self.assertEqual(spec.parameters.get("type"), "object", spec.name)
            self.assertIsInstance(spec.parameters.get("properties"), dict)
            self.assertTrue(callable(spec.handler), spec.name)
            for required in spec.parameters.get("required", []):
                self.assertIn(required, spec.parameters["properties"], f"{spec.name}:{required}")
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 20)

    def test_expected_tools_exist(self) -> None:
        names = {spec.name for spec in canvas_tools.CANVAS_TOOLS}
        expected = {
            "canvas_create",
            "canvas_list",
            "canvas_inspect",
            "canvas_summarize",
            "canvas_find_overlaps",
            "canvas_add_node",
            "canvas_add_edge",
            "canvas_add_text",
            "canvas_add_shape",
            "canvas_add_legend",
            "canvas_create_process_map",
            "canvas_create_variant_paths",
            "canvas_highlight_path",
            "canvas_create_chart",
            "canvas_create_kpi",
            "canvas_create_gantt",
            "canvas_apply_layout",
            "canvas_align",
            "canvas_distribute",
            "canvas_move_elements",
            "canvas_resize_element",
            "canvas_update_style",
            "canvas_delete_elements",
            "canvas_undo",
        }
        self.assertEqual(expected - names, set())

    def test_enums_come_from_the_schema(self) -> None:
        by_name = {spec.name: spec for spec in canvas_tools.CANVAS_TOOLS}
        node_kinds = by_name["canvas_add_node"].parameters["properties"]["node_kind"]["enum"]
        self.assertIn("gateway", node_kinds)
        self.assertNotIn("not-a-kind", node_kinds)
        algorithms = by_name["canvas_apply_layout"].parameters["properties"]["algorithm"]["enum"]
        self.assertEqual(sorted(algorithms), ["grid", "layered", "radial", "timeline", "tree"])
        emphasis = by_name["canvas_highlight_path"].parameters["properties"]["emphasis"]["enum"]
        self.assertEqual(sorted(emphasis), ["dim", "highlight", "none", "outline"])

    def test_tools_are_registered_in_the_shared_registry(self) -> None:
        from tools import data_tools

        for spec in canvas_tools.CANVAS_TOOLS:
            self.assertIn(spec.name, data_tools.TOOLS_BY_NAME, spec.name)
            self.assertIs(data_tools.TOOLS_BY_NAME[spec.name], spec)
        registered = [tool.name for tool in data_tools.DATA_TOOLS if tool.name.startswith("canvas_")]
        self.assertEqual(registered, [spec.name for spec in canvas_tools.CANVAS_TOOLS])

    def test_openai_schemas_include_canvas_surface(self) -> None:
        from tools import data_tools

        schemas = data_tools.openai_tool_schemas("canvas")
        names = {schema["function"]["name"] for schema in schemas}
        self.assertIn("canvas_create_process_map", names)
        for schema in schemas:
            self.assertTrue(schema["function"]["description"].strip())


if __name__ == "__main__":
    unittest.main()
