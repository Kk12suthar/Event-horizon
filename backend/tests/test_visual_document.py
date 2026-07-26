"""Tests for the Visual Document schema, op format, and generated artifacts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from shared import visual_schema_export as exporter  # noqa: E402
from shared.visual_document import (  # noqa: E402
    AddElementOp,
    ChartElement,
    EdgeElement,
    MoveElementsOp,
    NodeElement,
    Provenance,
    Rect,
    RemoveElementOp,
    SetStyleOp,
    ShapeElement,
    UpdateElementOp,
    VisualDocument,
    VisualDocumentError,
    apply_commit,
    new_document,
    parse_ops,
    redo,
    undo,
)

SEMANTIC = "layer_semantic"
DATA = "layer_data"


def make_doc() -> VisualDocument:
    return new_document(
        project_id="proj-1",
        folder_id="folder-1",
        title="Process overview",
        document_id="vdoc_test",
        created_by="user-1",
    )


def node(node_id: str, x: float = 0.0, y: float = 0.0) -> NodeElement:
    return NodeElement(
        id=node_id,
        layer_id=SEMANTIC,
        rect=Rect(x=x, y=y, w=160, h=64),
        label=node_id.replace("_", " ").title(),
    )


def chart(chart_id: str = "chart_1") -> ChartElement:
    return ChartElement(
        id=chart_id,
        layer_id=DATA,
        rect=Rect(x=400, y=0, w=480, h=320),
        chart_type="bar",
        title="Cases per variant",
        x_field="variant",
        y_fields=["case_count"],
        a11y_label="Bar chart of case count per process variant",
        provenance=Provenance(
            source_table_id="tbl_events",
            folder_id="folder-1",
            transform_revision=3,
            columns=["variant", "case_count"],
            aggregation="count",
        ),
    )


def commit(doc: VisualDocument, ops, *, author="user-1", kind="user"):
    return apply_commit(doc, ops, author=author, author_kind=kind)


class TestDocumentCreation(unittest.TestCase):
    def test_new_document_has_layer_stack_and_zero_revision(self):
        doc = make_doc()
        self.assertEqual(doc.metadata.revision, 0)
        self.assertEqual(doc.metadata.schema_version, "1.0")
        self.assertEqual(
            [layer.id for layer in doc.layers],
            [
                "layer_background",
                "layer_semantic",
                "layer_data",
                "layer_annotation",
                "layer_freeform",
            ],
        )
        self.assertEqual(doc.elements, [])

    def test_roundtrip_through_json_is_lossless(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        reparsed = VisualDocument.model_validate(doc.model_dump())
        self.assertEqual(reparsed.model_dump(), doc.model_dump())


class TestSchemaEnforcement(unittest.TestCase):
    def test_arbitrary_css_key_is_rejected(self):
        with self.assertRaises(ValidationError):
            ShapeElement(
                id="shape_1",
                layer_id=SEMANTIC,
                rect=Rect(x=0, y=0, w=100, h=100),
                style={"fill": "surface", "boxShadow": "0 0 4px red"},
            )

    def test_unknown_style_token_value_is_rejected(self):
        with self.assertRaises(ValidationError):
            ShapeElement(
                id="shape_1",
                layer_id=SEMANTIC,
                rect=Rect(x=0, y=0, w=100, h=100),
                style={"fill": "#ff0000"},
            )

    def test_out_of_bounds_position_is_rejected(self):
        with self.assertRaises(ValidationError):
            Rect(x=1_000_000, y=0, w=100, h=100)

    def test_undersized_element_is_rejected(self):
        with self.assertRaises(ValidationError):
            Rect(x=0, y=0, w=2, h=100)

    def test_chart_requires_provenance(self):
        with self.assertRaises(ValidationError):
            ChartElement(
                id="chart_1",
                layer_id=DATA,
                rect=Rect(x=0, y=0, w=400, h=300),
                chart_type="bar",
                title="Ungrounded",
                x_field="x",
                y_fields=["y"],
                a11y_label="chart",
            )

    def test_data_element_requires_a11y_label(self):
        with self.assertRaises(ValidationError):
            ChartElement(
                id="chart_1",
                layer_id=DATA,
                rect=Rect(x=0, y=0, w=400, h=300),
                chart_type="bar",
                title="No alt text",
                x_field="x",
                y_fields=["y"],
                provenance=Provenance(source_table_id="tbl_events"),
            )

    def test_element_must_reference_existing_layer(self):
        doc = make_doc()
        with self.assertRaises(VisualDocumentError) as ctx:
            commit(
                doc,
                [
                    AddElementOp(
                        element=NodeElement(
                            id="task_a",
                            layer_id="layer_missing",
                            rect=Rect(x=0, y=0, w=160, h=64),
                            label="A",
                        )
                    )
                ],
            )
        self.assertEqual(ctx.exception.code, "integrity")

    def test_edge_endpoints_must_exist(self):
        doc = make_doc()
        with self.assertRaises(VisualDocumentError):
            commit(
                doc,
                [
                    AddElementOp(
                        element=EdgeElement(
                            id="edge_1",
                            layer_id=SEMANTIC,
                            source_id="task_a",
                            target_id="task_b",
                        )
                    )
                ],
            )

    def test_parse_ops_reports_a_structured_error(self):
        with self.assertRaises(VisualDocumentError) as ctx:
            parse_ops([{"op": "drop_database"}])
        self.assertEqual(ctx.exception.code, "invalid_op")


class TestOps(unittest.TestCase):
    def test_add_elements_bumps_revision_once_per_commit(self):
        doc = make_doc()
        doc, first = commit(
            doc,
            [
                AddElementOp(element=node("task_a")),
                AddElementOp(element=node("task_b", x=300)),
                AddElementOp(
                    element=EdgeElement(
                        id="edge_1",
                        layer_id=SEMANTIC,
                        source_id="task_a",
                        target_id="task_b",
                        edge_kind="sequence",
                    )
                ),
            ],
        )
        self.assertEqual(doc.metadata.revision, 1)
        self.assertEqual(first.revision, 1)
        self.assertEqual(len(doc.elements), 3)
        self.assertEqual(doc.metadata.updated_by, "user-1")

    def test_commit_is_atomic(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        snapshot = doc.model_dump()
        with self.assertRaises(VisualDocumentError):
            commit(
                doc,
                [
                    AddElementOp(element=node("task_b", x=300)),
                    RemoveElementOp(element_id="task_missing"),
                ],
            )
        self.assertEqual(doc.model_dump(), snapshot)

    def test_input_document_is_never_mutated(self):
        doc = make_doc()
        before = doc.model_dump()
        commit(doc, [AddElementOp(element=node("task_a"))])
        self.assertEqual(doc.model_dump(), before)

    def test_cannot_remove_element_referenced_by_edge(self):
        doc, _ = commit(
            make_doc(),
            [
                AddElementOp(element=node("task_a")),
                AddElementOp(element=node("task_b", x=300)),
                AddElementOp(
                    element=EdgeElement(
                        id="edge_1",
                        layer_id=SEMANTIC,
                        source_id="task_a",
                        target_id="task_b",
                    )
                ),
            ],
        )
        with self.assertRaises(VisualDocumentError) as ctx:
            commit(doc, [RemoveElementOp(element_id="task_a")])
        self.assertEqual(ctx.exception.code, "element_in_use")

    def test_locked_element_rejects_updates(self):
        locked = node("task_a")
        locked.locked = True
        doc, _ = commit(make_doc(), [AddElementOp(element=locked)])
        with self.assertRaises(VisualDocumentError) as ctx:
            commit(doc, [UpdateElementOp(element_id="task_a", patch={"label": "New"})])
        self.assertEqual(ctx.exception.code, "locked")

    def test_immutable_fields_rejected(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        with self.assertRaises(VisualDocumentError) as ctx:
            commit(doc, [UpdateElementOp(element_id="task_a", patch={"type": "shape"})])
        self.assertEqual(ctx.exception.code, "immutable_field")

    def test_update_bumps_element_revision(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        doc, _ = commit(doc, [UpdateElementOp(element_id="task_a", patch={"label": "Renamed"})])
        element = doc.element("task_a")
        self.assertEqual(element.label, "Renamed")
        self.assertEqual(element.meta.revision, 1)

    def test_move_inverse_restores_exact_geometry(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a", x=10, y=20))])
        doc, applied = commit(doc, [MoveElementsOp(element_ids=["task_a"], dx=45.5, dy=-12.25)])
        self.assertEqual(doc.element("task_a").rect.x, 55.5)
        restored, _ = commit(doc, applied.inverse_ops)
        self.assertEqual(restored.element("task_a").rect.x, 10.0)
        self.assertEqual(restored.element("task_a").rect.y, 20.0)

    def test_set_style_inverse_is_per_element(self):
        doc, _ = commit(
            make_doc(),
            [
                AddElementOp(element=node("task_a")),
                AddElementOp(element=node("task_b", x=300)),
            ],
        )
        doc, _ = commit(doc, [SetStyleOp(element_ids=["task_a"], style={"emphasis": "highlight"})])
        doc, applied = commit(
            doc,
            [SetStyleOp(element_ids=["task_a", "task_b"], style={"emphasis": "dim"})],
        )
        self.assertEqual(len(applied.inverse_ops), 2)
        restored, _ = commit(doc, applied.inverse_ops)
        self.assertEqual(restored.element("task_a").style.emphasis, "highlight")
        self.assertEqual(restored.element("task_b").style.emphasis, "none")

    def test_agent_and_user_commits_share_one_history(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        doc, _ = commit(doc, [AddElementOp(element=chart())], author="agent", kind="agent")
        self.assertEqual([c.author_kind for c in doc.history], ["user", "agent"])
        self.assertEqual(doc.metadata.revision, 2)


class TestUndoRedo(unittest.TestCase):
    def test_undo_reverts_agent_commit_and_redo_reapplies(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        baseline = [el.id for el in doc.elements]

        doc, _ = commit(doc, [AddElementOp(element=chart())], author="agent", kind="agent")
        self.assertIn("chart_1", [el.id for el in doc.elements])

        undone, reverted = undo(doc, author="user-1")
        self.assertIsNotNone(reverted)
        self.assertEqual([el.id for el in undone.elements], baseline)
        self.assertEqual(len(undone.redo_stack), 1)

        redone, _ = redo(undone, author="user-1")
        self.assertIn("chart_1", [el.id for el in redone.elements])
        self.assertEqual(redone.redo_stack, [])

    def test_undo_on_empty_history_is_a_noop(self):
        doc = make_doc()
        result, reverted = undo(doc, author="user-1")
        self.assertIsNone(reverted)
        self.assertEqual(result.metadata.revision, 0)

    def test_undo_restores_full_element_state(self):
        doc, _ = commit(make_doc(), [AddElementOp(element=node("task_a"))])
        before = doc.element("task_a").model_dump(exclude={"meta"})
        doc, _ = commit(
            doc,
            [UpdateElementOp(element_id="task_a", patch={"label": "Changed", "node_kind": "decision"})],
        )
        restored, _ = undo(doc, author="user-1")
        self.assertEqual(restored.element("task_a").model_dump(exclude={"meta"}), before)


class TestAccessibleOutline(unittest.TestCase):
    def test_outline_exposes_labels_edges_and_provenance(self):
        doc, _ = commit(
            make_doc(),
            [
                AddElementOp(element=node("task_a")),
                AddElementOp(element=node("task_b", x=300)),
                AddElementOp(
                    element=EdgeElement(
                        id="edge_1",
                        layer_id=SEMANTIC,
                        source_id="task_a",
                        target_id="task_b",
                        edge_kind="rework",
                    )
                ),
                AddElementOp(element=chart()),
            ],
        )
        outline = {row["id"]: row for row in doc.outline()}
        self.assertEqual(outline["task_a"]["label"], "Task A")
        self.assertEqual(outline["edge_1"]["from"], "task_a")
        self.assertEqual(outline["edge_1"]["edge_kind"], "rework")
        self.assertEqual(outline["chart_1"]["source_table_id"], "tbl_events")
        self.assertEqual(outline["chart_1"]["transform_revision"], 3)


class TestGeneratedArtifacts(unittest.TestCase):
    def test_checked_in_artifacts_match_a_fresh_generation(self):
        schema_text, ts_text = exporter.generate()
        on_disk_schema = exporter.SCHEMA_PATH.read_text(encoding="utf-8")
        on_disk_ts = exporter.TS_PATH.read_text(encoding="utf-8")
        message = "run: python shared/visual_schema_export.py"
        self.assertEqual(on_disk_schema, schema_text, message)
        self.assertEqual(on_disk_ts, ts_text, message)

    def test_typescript_declares_the_element_and_op_unions(self):
        _, ts_text = exporter.generate()
        self.assertIn("export type VisualElement =", ts_text)
        self.assertIn("export type VisualOp =", ts_text)
        self.assertIn("export interface VisualDocument {", ts_text)
        self.assertNotIn(": unknown;", ts_text.replace("patch?: Record<string, unknown>", ""))


if __name__ == "__main__":
    unittest.main()
