"""Tests for the Visual Document REST API.

Postgres is not available to the test suite, so the store functions the router
imports are replaced with an in-memory implementation that keeps the *real*
``shared.visual_document`` commit/undo/redo semantics (and the real optimistic
locking contract). Only persistence is faked; ops, validation, history, and layout
are exercised for real.
"""

from __future__ import annotations

import sys
import types
import unittest
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (str(ROOT), str(BACKEND)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _install_database_stub() -> None:
    """Keep the router importable when the SQLAlchemy engine cannot connect."""
    if "database" in sys.modules:
        return
    try:
        import database  # noqa: F401
    except Exception:  # pragma: no cover - only hit without a reachable DB
        stub = types.ModuleType("database")

        def get_db():
            yield None

        stub.get_db = get_db
        sys.modules["database"] = stub


_install_database_stub()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from router import visual_documents as api  # noqa: E402
from security.policy import ACCESS_ORDER  # noqa: E402
from shared.visual_document import (  # noqa: E402
    Commit,
    VisualDocument,
    apply_commit,
    new_document,
    new_id,
    parse_ops,
    redo,
    undo,
)
from shared.visual_document_store import VisualDocumentStoreError  # noqa: E402

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
FOLDER_ID = "22222222-2222-4222-8222-222222222222"
USER_ID = "user-1"
SEMANTIC = "layer_semantic"


def node_op(node_id: str, x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
    """An ``add_element`` op for a plain semantic node."""
    return {
        "op": "add_element",
        "element": {
            "type": "node",
            "id": node_id,
            "layer_id": SEMANTIC,
            "rect": {"x": x, "y": y, "w": 160, "h": 64},
            "label": node_id.replace("_", " ").title(),
        },
    }


def edge_op(edge_id: str, source_id: str, target_id: str) -> dict[str, Any]:
    return {
        "op": "add_element",
        "element": {
            "type": "edge",
            "id": edge_id,
            "layer_id": SEMANTIC,
            "source_id": source_id,
            "target_id": target_id,
        },
    }


class FakeStore:
    """Dict-backed stand-in for ``shared.visual_document_store``."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.revisions: dict[str, list[Commit]] = {}
        self.schema_calls = 0

    # -- schema ----------------------------------------------------------
    def ensure_visual_document_schema(self) -> None:
        self.schema_calls += 1

    # -- helpers ---------------------------------------------------------
    def _row(self, document_id: str) -> dict[str, Any]:
        row = self.rows.get(str(document_id))
        if not row or row["status"] == "DELETED":
            raise VisualDocumentStoreError(
                f"Visual document '{document_id}' was not found.",
                code="not_found",
                status_code=404,
            )
        return row

    def _save(self, row: dict[str, Any], doc: VisualDocument, commit: Commit) -> None:
        row["document"] = VisualDocument.model_validate(doc.model_dump(mode="json"))
        row["revision"] = doc.metadata.revision
        row["title"] = doc.metadata.title
        self.revisions.setdefault(row["id"], []).append(commit)

    # -- store API -------------------------------------------------------
    def create_document(
        self,
        project_id: str,
        folder_id: str,
        title: str,
        *,
        created_by: str,
        session_id: str | None = None,
        source_table_ids: list[str] | None = None,
    ) -> VisualDocument:
        document_id = str(uuid.uuid4())
        doc = new_document(
            project_id=project_id,
            folder_id=folder_id,
            title=title,
            document_id=document_id,
            session_id=session_id,
            created_by=created_by,
            source_table_ids=list(source_table_ids or []),
        )
        self.rows[document_id] = {
            "id": document_id,
            "project_id": project_id,
            "folder_id": folder_id,
            "session_id": session_id,
            "title": title,
            "revision": 0,
            "status": "ACTIVE",
            "created_by": created_by,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "document": doc,
        }
        self.revisions[document_id] = []
        return doc

    def get_document(self, document_id: str) -> VisualDocument:
        return self._row(document_id)["document"]

    def get_document_row(self, document_id: str) -> dict[str, Any]:
        row = self._row(document_id)
        return {key: value for key, value in row.items() if key != "document"}

    def list_documents(self, folder_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "revision": row["revision"],
                "updated_at": row["updated_at"],
                "created_by": row["created_by"],
                "element_count": len(row["document"].elements),
            }
            for row in self.rows.values()
            if row["folder_id"] == folder_id and row["status"] != "DELETED"
        ]

    def commit_ops(
        self,
        document_id: str,
        ops: list[Any],
        *,
        author: str,
        author_kind: str = "user",
        base_revision: int | None = None,
        label: str = "edit",
    ) -> tuple[VisualDocument, Commit]:
        parsed = parse_ops(list(ops))
        row = self._row(document_id)
        if base_revision is not None and int(base_revision) != row["revision"]:
            raise VisualDocumentStoreError(
                "This canvas changed since it was loaded.",
                code="revision_conflict",
                status_code=409,
                current_revision=row["revision"],
            )
        doc, commit = apply_commit(
            row["document"], parsed, author=author, author_kind=author_kind, label=label
        )
        self._save(row, doc, commit)
        return doc, commit

    def undo_document(
        self, document_id: str, author: str
    ) -> tuple[VisualDocument, Commit | None]:
        row = self._row(document_id)
        doc, undone = undo(row["document"], author=author)
        if undone is None:
            return doc, None
        record = Commit(
            id=new_id("cmt"),
            revision=doc.metadata.revision,
            at=doc.metadata.updated_at,
            author=author,
            author_kind="system",
            label=f"undo:{undone.label}",
            ops=[op.model_copy(deep=True) for op in undone.inverse_ops],
            inverse_ops=[op.model_copy(deep=True) for op in undone.ops],
        )
        self._save(row, doc, record)
        return doc, record

    def redo_document(
        self, document_id: str, author: str
    ) -> tuple[VisualDocument, Commit | None]:
        row = self._row(document_id)
        doc, commit = redo(row["document"], author=author)
        if commit is None:
            return doc, None
        self._save(row, doc, commit)
        return doc, commit

    def soft_delete_document(self, document_id: str) -> None:
        self._row(document_id)["status"] = "DELETED"


class VisualDocumentApiTestCase(unittest.TestCase):
    """Base case wiring the router to a fake store and a fake access policy."""

    access_level = "ANALYST"

    def setUp(self) -> None:
        self.store = FakeStore()
        self.access_level = type(self).access_level
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.get_db] = lambda: None
        self.client = TestClient(app)

        def fake_require_folder_access(folder_id, user, db, min_level="VIEWER"):
            granted = ACCESS_ORDER.get(str(self.access_level).upper(), 0)
            if granted < ACCESS_ORDER.get(str(min_level).upper(), 0):
                raise HTTPException(status_code=403, detail="Access denied.")
            return str(self.access_level).upper()

        patches = {
            "ensure_visual_document_schema": self.store.ensure_visual_document_schema,
            "create_document": self.store.create_document,
            "get_document": self.store.get_document,
            "get_document_row": self.store.get_document_row,
            "list_documents": self.store.list_documents,
            "commit_ops": self.store.commit_ops,
            "undo_document": self.store.undo_document,
            "redo_document": self.store.redo_document,
            "soft_delete_document": self.store.soft_delete_document,
            "require_folder_access": fake_require_folder_access,
            "user_from_request": lambda request: {"sub": USER_ID},
            "_validated_creation_context": lambda payload, user, db: payload.project_id,
            "current_user_id": lambda user: str((user or {}).get("sub") or USER_ID),
        }
        self._originals = {name: getattr(api, name) for name in patches}
        for name, replacement in patches.items():
            setattr(api, name, replacement)
        self._schema_ready = api._SCHEMA_READY
        api._SCHEMA_READY = False

    def tearDown(self) -> None:
        for name, original in self._originals.items():
            setattr(api, name, original)
        api._SCHEMA_READY = self._schema_ready
        self.client.close()

    # -- helpers ---------------------------------------------------------
    def create(self, title: str = "Process overview") -> dict[str, Any]:
        response = self.client.post(
            "/api/v1/visual-documents",
            json={"project_id": PROJECT_ID, "folder_id": FOLDER_ID, "title": title},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["document"]

    def commit(self, document_id: str, ops: list[dict[str, Any]], base_revision: int):
        return self.client.post(
            f"/api/v1/visual-documents/{document_id}/commit",
            json={"ops": ops, "base_revision": base_revision},
        )

    def with_nodes(self, *node_ids: str) -> dict[str, Any]:
        """Create a document and add the given nodes in one commit."""
        document = self.create()
        response = self.commit(
            document["metadata"]["id"],
            [node_op(node_id) for node_id in node_ids],
            0,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["document"]


class DocumentLifecycleTests(VisualDocumentApiTestCase):
    def test_create_returns_document_with_standard_layers(self):
        document = self.create("Order to cash")

        self.assertEqual(document["metadata"]["title"], "Order to cash")
        self.assertEqual(document["metadata"]["revision"], 0)
        self.assertEqual(document["metadata"]["created_by"], USER_ID)
        self.assertEqual(document["elements"], [])
        self.assertIn(SEMANTIC, [layer["id"] for layer in document["layers"]])
        self.assertEqual(self.store.schema_calls, 1)

    def test_get_returns_the_stored_document(self):
        created = self.create()

        response = self.client.get(f"/api/v1/visual-documents/{created['metadata']['id']}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["document"]["metadata"]["id"], created["metadata"]["id"]
        )

    def test_get_unknown_document_returns_404(self):
        response = self.client.get(f"/api/v1/visual-documents/{uuid.uuid4()}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "not_found")

    def test_list_returns_summaries_for_the_folder(self):
        first = self.create("First canvas")
        self.create("Second canvas")
        self.commit(first["metadata"]["id"], [node_op("node_a")], 0)

        response = self.client.get(
            "/api/v1/visual-documents", params={"folder_id": FOLDER_ID}
        )

        self.assertEqual(response.status_code, 200, response.text)
        summaries = {item["title"]: item for item in response.json()["documents"]}
        self.assertEqual(set(summaries), {"First canvas", "Second canvas"})
        self.assertEqual(summaries["First canvas"]["revision"], 1)
        self.assertEqual(summaries["First canvas"]["element_count"], 1)
        self.assertEqual(summaries["Second canvas"]["element_count"], 0)

    def test_delete_then_get_returns_404(self):
        document = self.create()
        document_id = document["metadata"]["id"]

        deleted = self.client.delete(f"/api/v1/visual-documents/{document_id}")
        fetched = self.client.get(f"/api/v1/visual-documents/{document_id}")

        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["message"], "Visual document deleted")
        self.assertEqual(fetched.status_code, 404)

    def test_outline_returns_one_row_per_element(self):
        document = self.with_nodes("node_a", "node_b")

        response = self.client.get(
            f"/api/v1/visual-documents/{document['metadata']['id']}/outline"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([row["id"] for row in body["outline"]], ["node_a", "node_b"])
        self.assertEqual(body["outline"][0]["label"], "Node A")
        self.assertEqual(body["summary"]["element_counts"], {"node": 2})
        self.assertEqual(body["summary"]["revision"], 1)

    def test_readability_reports_overlapping_nodes(self):
        document = self.create()
        document_id = document["metadata"]["id"]
        self.commit(document_id, [node_op("node_a", 0, 0), node_op("node_b", 10, 10)], 0)

        response = self.client.get(
            f"/api/v1/visual-documents/{document_id}/readability"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(
            [(item["a"], item["b"]) for item in body["overlaps"]], [("node_a", "node_b")]
        )


class CommitTests(VisualDocumentApiTestCase):
    def test_commit_adds_elements_and_bumps_revision(self):
        document = self.create()
        document_id = document["metadata"]["id"]

        response = self.commit(document_id, [node_op("node_a"), node_op("node_b")], 0)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["document"]["metadata"]["revision"], 1)
        self.assertEqual(
            [element["id"] for element in body["document"]["elements"]],
            ["node_a", "node_b"],
        )
        self.assertEqual(body["commit"]["revision"], 1)
        self.assertEqual(body["commit"]["author"], USER_ID)
        self.assertEqual(body["commit"]["author_kind"], "user")
        self.assertEqual(len(body["commit"]["inverse_ops"]), 2)
        self.assertEqual(self.store.rows[document_id]["revision"], 1)

    def test_stale_base_revision_returns_409_with_current_revision(self):
        document = self.create()
        document_id = document["metadata"]["id"]
        self.commit(document_id, [node_op("node_a")], 0)

        response = self.commit(document_id, [node_op("node_b")], 0)

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "revision_conflict")
        self.assertEqual(detail["current_revision"], 1)
        self.assertEqual(self.store.rows[document_id]["revision"], 1)

    def test_invalid_op_returns_422_with_a_code(self):
        document = self.create()

        response = self.commit(
            document["metadata"]["id"],
            [{"op": "add_element", "element": {"type": "node", "id": "node_a"}}],
            0,
        )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "invalid_op")
        self.assertIn("invalid op at index 0", detail["message"])

    def test_commit_rejects_op_that_breaks_document_integrity(self):
        document = self.with_nodes("node_a")

        response = self.commit(
            document["metadata"]["id"],
            [edge_op("edge_1", "node_a", "node_missing")],
            1,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error"], "integrity")

    def test_undo_then_redo_round_trips(self):
        document = self.with_nodes("node_a")
        document_id = document["metadata"]["id"]

        undone = self.client.post(f"/api/v1/visual-documents/{document_id}/undo")
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["document"]["elements"], [])
        self.assertEqual(undone.json()["commit"]["label"], "undo:edit")

        redone = self.client.post(f"/api/v1/visual-documents/{document_id}/redo")
        self.assertEqual(redone.status_code, 200, redone.text)
        elements = redone.json()["document"]["elements"]
        self.assertEqual([element["id"] for element in elements], ["node_a"])
        self.assertEqual(
            redone.json()["document"]["metadata"]["revision"],
            undone.json()["document"]["metadata"]["revision"] + 1,
        )

    def test_undo_with_empty_history_returns_null_commit(self):
        document = self.create()

        response = self.client.post(
            f"/api/v1/visual-documents/{document['metadata']['id']}/undo"
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["commit"])
        self.assertEqual(response.json()["document"]["metadata"]["revision"], 0)


class LayoutTests(VisualDocumentApiTestCase):
    def test_layout_moves_overlapping_nodes_apart(self):
        document = self.create()
        document_id = document["metadata"]["id"]
        self.commit(
            document_id,
            [
                node_op("node_a", 0, 0),
                node_op("node_b", 0, 0),
                node_op("node_c", 0, 0),
                edge_op("edge_ab", "node_a", "node_b"),
                edge_op("edge_bc", "node_b", "node_c"),
            ],
            0,
        )

        response = self.client.post(
            f"/api/v1/visual-documents/{document_id}/layout",
            json={"algorithm": "layered", "direction": "right", "base_revision": 1},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNotNone(body["commit"])
        self.assertEqual(body["document"]["metadata"]["revision"], 2)
        self.assertEqual(body["commit"]["label"], "layout:layered")
        rects = {
            element["id"]: element["rect"]
            for element in body["document"]["elements"]
            if element["type"] == "node"
        }
        self.assertEqual(len({rect["x"] for rect in rects.values()}), 3)
        self.assertLess(rects["node_a"]["x"], rects["node_b"]["x"])
        self.assertLess(rects["node_b"]["x"], rects["node_c"]["x"])

    def test_layout_on_empty_canvas_is_a_no_op(self):
        document = self.create()

        response = self.client.post(
            f"/api/v1/visual-documents/{document['metadata']['id']}/layout",
            json={"algorithm": "grid", "base_revision": 0},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["commit"])
        self.assertEqual(response.json()["document"]["metadata"]["revision"], 0)

    def test_unknown_layout_algorithm_is_rejected_by_validation(self):
        document = self.create()

        response = self.client.post(
            f"/api/v1/visual-documents/{document['metadata']['id']}/layout",
            json={"algorithm": "spiral", "base_revision": 0},
        )

        self.assertEqual(response.status_code, 422)

    def test_align_left_moves_elements_onto_one_edge(self):
        document = self.create()
        document_id = document["metadata"]["id"]
        self.commit(
            document_id,
            [node_op("node_a", 40, 0), node_op("node_b", 300, 200)],
            0,
        )

        response = self.client.post(
            f"/api/v1/visual-documents/{document_id}/align",
            json={"element_ids": ["node_a", "node_b"], "axis": "left", "base_revision": 1},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        rects = {
            element["id"]: element["rect"] for element in body["document"]["elements"]
        }
        self.assertEqual(rects["node_a"]["x"], 40)
        self.assertEqual(rects["node_b"]["x"], 40)
        self.assertEqual(rects["node_b"]["y"], 200)
        self.assertEqual(body["commit"]["label"], "align:left")


class AccessControlTests(VisualDocumentApiTestCase):
    access_level = "VIEWER"

    def test_viewer_can_read_but_not_commit(self):
        self.access_level = "ANALYST"
        document = self.with_nodes("node_a")
        document_id = document["metadata"]["id"]
        self.access_level = "VIEWER"

        readable = self.client.get(f"/api/v1/visual-documents/{document_id}")
        written = self.commit(document_id, [node_op("node_b")], 1)

        self.assertEqual(readable.status_code, 200, readable.text)
        self.assertEqual(written.status_code, 403)
        self.assertEqual(self.store.rows[document_id]["revision"], 1)

    def test_viewer_cannot_create_undo_layout_or_delete(self):
        self.access_level = "ANALYST"
        document_id = self.with_nodes("node_a")["metadata"]["id"]
        self.access_level = "VIEWER"

        created = self.client.post(
            "/api/v1/visual-documents",
            json={"project_id": PROJECT_ID, "folder_id": FOLDER_ID, "title": "Blocked"},
        )
        undone = self.client.post(f"/api/v1/visual-documents/{document_id}/undo")
        laid_out = self.client.post(
            f"/api/v1/visual-documents/{document_id}/layout",
            json={"algorithm": "grid", "base_revision": 1},
        )
        deleted = self.client.delete(f"/api/v1/visual-documents/{document_id}")

        self.assertEqual(
            [created.status_code, undone.status_code, laid_out.status_code, deleted.status_code],
            [403, 403, 403, 403],
        )
        self.assertEqual(self.store.rows[document_id]["status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()
