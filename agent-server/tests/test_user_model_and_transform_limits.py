from __future__ import annotations

from contextlib import contextmanager
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class UserModelConfigTests(unittest.TestCase):
    def test_production_never_uses_environment_provider_key(self):
        from runtime.user_model_config import load_effective_model_config

        env = {
            "ENVIRONMENT": "production",
            "MODEL_CONFIG_MODE": "environment",
            "AGENT_PROVIDER": "openai",
            "AGENT_MODEL": "gpt-5.4-mini",
            "OPENAI_API_KEY": "deployment-key",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertIsNone(load_effective_model_config(lambda: None))

    def test_first_user_configuration_requires_own_key(self):
        from runtime.user_model_config import ModelConfigUpdate, apply_model_config_update

        with self.assertRaisesRegex(ValueError, "API key is required"):
            apply_model_config_update(
                ModelConfigUpdate(provider="openai", model="gpt-4o"),
                save_config=lambda _: None,
                existing_config=None,
            )

    def test_same_provider_keeps_existing_user_key(self):
        from runtime.user_model_config import ModelConfigUpdate, apply_model_config_update

        saved = {}
        apply_model_config_update(
            ModelConfigUpdate(provider="openai", model="gpt-4.1"),
            save_config=lambda config: saved.update(config),
            existing_config={"provider": "openai", "model": "gpt-4o", "api_key": "user-key"},
        )
        self.assertEqual(saved["api_key"], "user-key")

    def test_provider_switch_requires_a_new_user_key(self):
        from runtime.user_model_config import ModelConfigUpdate, apply_model_config_update

        with self.assertRaisesRegex(ValueError, "API key is required"):
            apply_model_config_update(
                ModelConfigUpdate(provider="google", model="gemini-2.5-flash"),
                save_config=lambda _: None,
                existing_config={"provider": "openai", "model": "gpt-4o", "api_key": "openai-user-key"},
            )

    def test_loader_is_scoped_to_each_user(self):
        from runtime.user_model_config import load_effective_model_config

        configs = {
            "user-a": {"provider": "openai", "model": "gpt-4o", "api_key": "key-a"},
            "user-b": {"provider": "google", "model": "gemini-2.5-flash", "api_key": "key-b"},
        }
        first = load_effective_model_config(lambda: configs["user-a"])
        second = load_effective_model_config(lambda: configs["user-b"])
        self.assertEqual(first.api_key, "key-a")
        self.assertEqual(second.api_key, "key-b")
        self.assertNotEqual(first.model, second.model)


class _QuotaCursor:
    def __init__(self):
        self.last_sql = ""
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.last_sql = str(sql)
        self.calls.append((self.last_sql, params))

    def fetchall(self):
        if "FROM uploads.table_registry" in self.last_sql:
            return [{"table_id": "existing-id", "name": "prepared", "folder_id": "folder-1", "session_id": "session-1"}]
        return []


class _QuotaConnection:
    def __init__(self):
        self.cursor_instance = _QuotaCursor()
        self.rolled_back = False

    def cursor(self, **_):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True


class PreparedTableLimitTests(unittest.TestCase):
    def test_second_agent_created_table_is_rejected_before_ctas(self):
        import tools.postgres as postgres

        connection = _QuotaConnection()

        @contextmanager
        def fake_connect(_):
            yield connection

        originals = {
            "DatabaseConfig": postgres.DatabaseConfig,
            "require_folder_access": postgres.require_folder_access,
            "validate_session_context": postgres.validate_session_context,
            "ensure_workspace_schema": postgres.ensure_workspace_schema,
            "_get_table_mapping": postgres._get_table_mapping,
            "_connect": postgres._connect,
        }
        try:
            postgres.DatabaseConfig = types.SimpleNamespace(from_env=lambda: types.SimpleNamespace(configured=True))
            postgres.require_folder_access = lambda *_, **__: None
            postgres.validate_session_context = lambda *_, **__: None
            postgres.ensure_workspace_schema = lambda: None
            postgres._get_table_mapping = lambda *_: {"source_table": "raw_source"}
            postgres._connect = fake_connect

            with patch.dict(os.environ, {"MAX_PREPARED_TABLES_PER_USER": "1"}, clear=False):
                result = postgres.create_transform_table(
                    folder_id="folder-1",
                    user_id="user-1",
                    session_id="session-1",
                    select_sql='SELECT * FROM "source_table"',
                )

            self.assertEqual(result["code"], "prepared_table_limit_reached")
            self.assertTrue(connection.rolled_back)
            self.assertFalse(any("CREATE TABLE" in sql for sql, _ in connection.cursor_instance.calls))
        finally:
            for name, value in originals.items():
                setattr(postgres, name, value)


if __name__ == "__main__":
    unittest.main()
