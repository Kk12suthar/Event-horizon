import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeRowResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self, *, role="VIEWER", project_level=None, folder_level=None, session=None, table=None):
        self.role = role
        self.project_level = project_level
        self.folder_level = folder_level
        self.session = session
        self.table = table
        self.calls = []

    def execute(self, query, params=None):
        sql = str(query).lower()
        self.calls.append((sql, params or {}))
        if "select role" in sql:
            return FakeRowResult((self.role,))
        if "entity_type = 'project'" in sql:
            return FakeScalarResult(self.project_level)
        if "entity_type = 'folder'" in sql:
            return FakeScalarResult(self.folder_level)
        if "from instance01.mtd_session" in sql:
            return FakeRowResult(self.session)
        if "from instance01.mtd_table" in sql:
            return FakeRowResult(self.table)
        raise AssertionError(f"unexpected query: {query}")


class ProductionPolicyTests(unittest.TestCase):
    def test_rejects_user_id_impersonation_for_non_admin(self):
        from security.policy import require_same_user_or_admin

        with self.assertRaises(Exception) as ctx:
            require_same_user_or_admin("user-a", {"sub": "user-b"}, FakeDb(role="VIEWER"))

        self.assertEqual(getattr(ctx.exception, "status_code", None), 403)

    def test_allows_admin_user_impersonation(self):
        from security.policy import require_same_user_or_admin

        self.assertEqual(require_same_user_or_admin("user-a", {"sub": "admin"}, FakeDb(role="ADMIN")), "user-a")

    def test_folder_access_requires_minimum_level(self):
        from security.policy import require_folder_access

        self.assertEqual(
            require_folder_access("folder-1", {"sub": "user-a"}, FakeDb(folder_level="ANALYST"), min_level="VIEWER"),
            "ANALYST",
        )

        with self.assertRaises(Exception) as ctx:
            require_folder_access("folder-1", {"sub": "user-a"}, FakeDb(folder_level="VIEWER"), min_level="ANALYST")

        self.assertEqual(getattr(ctx.exception, "status_code", None), 403)

    def test_session_access_uses_owner_or_folder_access(self):
        from security.policy import require_session_owner_or_folder_access

        session = SimpleNamespace(created_by="user-a", folder_id="folder-1")
        self.assertEqual(
            require_session_owner_or_folder_access("session-1", {"sub": "user-a"}, FakeDb(session=session)),
            session,
        )

        other_user_db = FakeDb(session=session, folder_level="ANALYST")
        self.assertEqual(
            require_session_owner_or_folder_access("session-1", {"sub": "user-b"}, other_user_db),
            session,
        )

    def test_table_access_requires_table_inside_accessible_folder(self):
        from security.policy import require_table_access

        table = SimpleNamespace(parent_folder_id="folder-1")
        self.assertEqual(
            require_table_access("table-1", "folder-1", {"sub": "user-a"}, FakeDb(table=table, folder_level="VIEWER")),
            table,
        )

        with self.assertRaises(Exception) as ctx:
            require_table_access("table-1", "folder-2", {"sub": "user-a"}, FakeDb(table=table, folder_level="VIEWER"))

        self.assertEqual(getattr(ctx.exception, "status_code", None), 403)


if __name__ == "__main__":
    unittest.main()
