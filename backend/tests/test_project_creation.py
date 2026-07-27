import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _install_database_stub() -> None:
    """Keep this unit test independent from a reachable PostgreSQL instance."""
    if "database" in sys.modules:
        return
    try:
        import database  # noqa: F401
    except Exception:
        stub = types.ModuleType("database")

        def get_db():
            yield None

        stub.get_db = get_db
        sys.modules["database"] = stub


_install_database_stub()

from router import projects
from schemas import ProjectCreate


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _ProjectDb:
    def __init__(self):
        self.calls = []
        self.committed = False
        self.rolled_back = False

    def execute(self, query, params=None):
        sql = str(query).lower()
        payload = dict(params or {})
        self.calls.append((sql, payload))
        if "select role" in sql:
            return _Result(("ANALYST",))
        if "select id from instance01.mtd_users" in sql:
            return _Result(("authenticated-user",))
        return _Result()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class ProjectCreationTests(unittest.TestCase):
    def test_creator_identity_and_owner_access_are_atomic(self):
        db = _ProjectDb()
        request = SimpleNamespace(
            state=SimpleNamespace(user={"sub": "authenticated-user"})
        )
        payload = ProjectCreate(
            id="11111111-1111-4111-8111-111111111111",
            name="First project",
            description="New user data",
            created_at="2026-07-26 10:00:00",
            created_by="spoofed-user",
            status="ACTIVE",
        )

        with (
            patch.object(projects, "enforce_project_limit"),
            patch.object(projects, "_update_project_counts"),
            patch.object(projects, "log_admin_action"),
        ):
            response = projects.create_project(payload, request, db)

        self.assertEqual(response.message, "Project created successfully")
        self.assertTrue(db.committed)
        self.assertFalse(db.rolled_back)

        project_insert = next(
            params
            for sql, params in db.calls
            if "insert into instance01.mtd_project" in sql
        )
        owner_insert = next(
            params
            for sql, params in db.calls
            if "insert into instance01.mtd_access" in sql
        )
        self.assertEqual(project_insert["created_by"], "authenticated-user")
        self.assertEqual(owner_insert["user_id"], "authenticated-user")
        self.assertEqual(
            owner_insert["project_id"], "11111111-1111-4111-8111-111111111111"
        )


if __name__ == "__main__":
    unittest.main()
