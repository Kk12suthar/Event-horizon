"""Tests for the DB-free logic in ``shared.visual_document_store``.

The SQL paths need Postgres, but revision replay and restore-diffing are pure
functions and carry the risk: they decide whether a point-in-time restore
reproduces the canvas exactly. They are covered here against real commits.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.visual_document import (  # noqa: E402
    AddElementOp,
    NodeElement,
    Rect,
    SetTitleOp,
    VisualDocument,
    apply_commit,
    new_document,
)
from shared.visual_document_store import (  # noqa: E402
    VisualDocumentStoreError,
    _replay,
    _restore_ops,
    _require_uuid,
)

SEMANTIC = "layer_semantic"


def node(node_id: str, x: float = 0.0) -> NodeElement:
    return NodeElement(
        id=node_id,
        layer_id=SEMANTIC,
        rect=Rect(x=x, y=0.0, w=160, h=64),
        label=node_id.replace("_", " ").title(),
    )


def make_doc() -> VisualDocument:
    return new_document(
        project_id="11111111-1111-4111-8111-111111111111",
        folder_id="22222222-2222-4222-8222-222222222222",
        title="Process overview",
        document_id="33333333-3333-4333-8333-333333333333",
        created_by="user-1",
    )


def history_rows(doc: VisualDocument) -> list[dict[str, Any]]:
    """The revision-log rows a document's history would have produced."""
    return [
        {
            "revision": commit.revision,
            "commit": commit.model_dump(mode="json"),
            "author": commit.author,
            "author_kind": commit.author_kind,
        }
        for commit in doc.history
    ]


class ReplayTests(unittest.TestCase):
    def test_replay_reproduces_element_state(self):
        doc = make_doc()
        doc, _ = apply_commit(doc, [AddElementOp(element=node("node_a"))], author="user-1")
        doc, _ = apply_commit(
            doc, [AddElementOp(element=node("node_b", 400))], author="user-1"
        )

        replayed = _replay(doc, history_rows(doc))

        self.assertEqual(
            [element.id for element in replayed.elements], ["node_a", "node_b"]
        )
        self.assertEqual(replayed.metadata.revision, 2)
        self.assertEqual(
            [layer.id for layer in replayed.layers], [layer.id for layer in doc.layers]
        )

    def test_replay_stops_at_the_supplied_revision(self):
        doc = make_doc()
        doc, _ = apply_commit(doc, [AddElementOp(element=node("node_a"))], author="user-1")
        doc, _ = apply_commit(
            doc, [AddElementOp(element=node("node_b", 400))], author="user-1"
        )

        replayed = _replay(doc, history_rows(doc)[:1])

        self.assertEqual([element.id for element in replayed.elements], ["node_a"])

    def test_replay_of_no_history_yields_an_empty_canvas(self):
        doc = make_doc()
        doc, _ = apply_commit(doc, [AddElementOp(element=node("node_a"))], author="user-1")

        replayed = _replay(doc, [])

        self.assertEqual(replayed.elements, [])
        self.assertEqual(replayed.metadata.revision, 0)

    def test_replay_failure_is_reported_as_a_store_error(self):
        doc = make_doc()
        broken = [
            {
                "revision": 1,
                "commit": {"label": "edit", "ops": [{"op": "remove_element", "element_id": "ghost"}]},
                "author": "user-1",
                "author_kind": "user",
            }
        ]

        with self.assertRaises(VisualDocumentStoreError) as error:
            _replay(doc, broken)

        self.assertEqual(error.exception.code, "replay_failed")
        self.assertEqual(error.exception.status_code, 409)


class RestoreOpsTests(unittest.TestCase):
    def test_restore_ops_rebuild_the_target_state(self):
        base = make_doc()
        target, _ = apply_commit(
            base, [AddElementOp(element=node("node_a"))], author="user-1"
        )
        current, _ = apply_commit(
            base, [AddElementOp(element=node("node_z", 900))], author="user-1"
        )
        current, _ = apply_commit(current, [SetTitleOp(title="Renamed")], author="user-1")

        ops = _restore_ops(current, target)
        restored, commit = apply_commit(current, ops, author="user-1", label="restore:r1")

        self.assertEqual([element.id for element in restored.elements], ["node_a"])
        self.assertEqual(restored.metadata.revision, current.metadata.revision + 1)
        self.assertEqual(commit.label, "restore:r1")
        # Title is metadata, not content, so it is restored explicitly.
        self.assertEqual(restored.metadata.title, target.metadata.title)

    def test_restore_ops_are_empty_when_content_already_matches(self):
        doc = make_doc()
        doc, _ = apply_commit(doc, [AddElementOp(element=node("node_a"))], author="user-1")

        self.assertEqual(_restore_ops(doc, doc), [])

    def test_restore_ops_unlock_elements_before_removing_them(self):
        base = make_doc()
        locked = node("node_locked")
        locked.locked = True
        current, _ = apply_commit(base, [AddElementOp(element=locked)], author="user-1")
        target, _ = apply_commit(base, [AddElementOp(element=node("node_a"))], author="user-1")

        restored, _ = apply_commit(
            current, _restore_ops(current, target), author="user-1"
        )

        self.assertEqual([element.id for element in restored.elements], ["node_a"])


class IdentifierTests(unittest.TestCase):
    def test_invalid_identifier_raises_a_400(self):
        with self.assertRaises(VisualDocumentStoreError) as error:
            _require_uuid("not-a-uuid", "document_id")

        self.assertEqual(error.exception.code, "invalid_identifier")
        self.assertEqual(error.exception.status_code, 400)

    def test_valid_identifier_is_normalized(self):
        self.assertEqual(
            _require_uuid("22222222222242228222222222222222", "folder_id"),
            "22222222-2222-4222-8222-222222222222",
        )


if __name__ == "__main__":
    unittest.main()
