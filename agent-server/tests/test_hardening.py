from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main as agent_main

from llm.client import complete_text, resolve_model_name
from main import AgentStreamRequest, ReportRequest, _model_config_status, _resolve_artifact_root, _thread_config
from tools.postgres import _validate_select


class AgentHardeningTests(unittest.TestCase):
    def test_relative_artifact_root_resolves_from_repository_root(self) -> None:
        resolved = _resolve_artifact_root("agent-server/artifacts")
        self.assertEqual(resolved, (ROOT.parent / "agent-server" / "artifacts").resolve())

    def test_thread_config_isolates_user_folder_surface_and_sanitizes(self) -> None:
        first = _thread_config(
            surface="dashboard",
            user_id="user one@example.com",
            folder_id="folder A",
            session_id="session:1",
            project_id="project A",
        )["configurable"]["thread_id"]
        second = _thread_config(
            surface="report",
            user_id="user one@example.com",
            folder_id="folder A",
            session_id="session:1",
            project_id="project A",
        )["configurable"]["thread_id"]
        third = _thread_config(
            surface="dashboard",
            user_id="user two@example.com",
            folder_id="folder B",
            session_id="session:1",
            project_id="project A",
        )["configurable"]["thread_id"]

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertTrue(first.startswith("eventhorizon:dashboard:"))
        self.assertNotIn(" ", first)
        self.assertNotIn("@", first)
        self.assertIn("useroneexamplecom", first)
        self.assertIn("folderA", first)

    def test_agent_stream_request_selected_tables_not_shared(self) -> None:
        first = AgentStreamRequest(query="first")
        second = AgentStreamRequest(query="second")

        first.selected_tables.append("orders")

        self.assertEqual(first.selected_tables, ["orders"])
        self.assertEqual(second.selected_tables, [])

    def test_report_request_carries_context_defaults(self) -> None:
        payload = ReportRequest(
            query="Create a report",
            user_id="user-1",
            session_id="session-1",
            project_id="project-1",
            selected_tables=["orders"],
        )

        self.assertEqual(payload.user_id, "user-1")
        self.assertEqual(payload.session_id, "session-1")
        self.assertEqual(payload.project_id, "project-1")
        self.assertEqual(payload.selected_tables, ["orders"])

    def test_llm_fallback_without_model_config(self) -> None:
        old_model = os.environ.pop("AGENT_MODEL", None)
        old_model_name = os.environ.pop("MODEL_NAME", None)
        try:
            self.assertEqual(complete_text("hello"), "")
        finally:
            if old_model is not None:
                os.environ["AGENT_MODEL"] = old_model
            if old_model_name is not None:
                os.environ["MODEL_NAME"] = old_model_name


    def test_openrouter_model_normalization(self) -> None:
        self.assertEqual(resolve_model_name("openai/gpt-4o", "openrouter"), "openrouter/openai/gpt-4o")
        self.assertEqual(resolve_model_name("openrouter/anthropic/claude-sonnet-4.5", "openrouter"), "openrouter/anthropic/claude-sonnet-4.5")
        self.assertEqual(resolve_model_name("gpt-4o", "openai"), "gpt-4o")

    def test_openrouter_without_key_falls_back_cleanly(self) -> None:
        saved = {key: os.environ.pop(key, None) for key in ("AGENT_MODEL", "MODEL_NAME", "AGENT_PROVIDER", "MODEL_PROVIDER", "OPENROUTER_API_KEY")}
        try:
            os.environ["AGENT_PROVIDER"] = "openrouter"
            os.environ["AGENT_MODEL"] = "openai/gpt-4o"
            self.assertEqual(complete_text("hello"), "")
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value

    def test_openrouter_completion_uses_runtime_slug_base_url_and_headers(self) -> None:
        saved_env = {key: os.environ.get(key) for key in (
            "AGENT_MODEL",
            "MODEL_NAME",
            "AGENT_PROVIDER",
            "MODEL_PROVIDER",
            "OPENROUTER_API_KEY",
            "OPENROUTER_API_BASE",
            "OR_SITE_URL",
            "OR_APP_NAME",
        )}
        previous_litellm = sys.modules.get("litellm")
        calls: list[dict] = []

        fake_litellm = types.SimpleNamespace(
            completion=lambda **kwargs: calls.append(kwargs) or {"choices": [{"message": {"content": "ok"}}]}
        )
        sys.modules["litellm"] = fake_litellm
        try:
            os.environ["AGENT_PROVIDER"] = "openrouter"
            os.environ["AGENT_MODEL"] = "openrouter/anthropic/claude-sonnet-4.5"
            os.environ["OPENROUTER_API_KEY"] = "test-key"
            os.environ["OPENROUTER_API_BASE"] = "https://openrouter.ai/api/v1"
            os.environ["OR_SITE_URL"] = "http://127.0.0.1:5174"
            os.environ["OR_APP_NAME"] = "EventHorizon"

            self.assertEqual(complete_text("hello"), "ok")
            self.assertEqual(calls[0]["model"], "openrouter/anthropic/claude-sonnet-4.5")
            self.assertEqual(calls[0]["base_url"], "https://openrouter.ai/api/v1")
            self.assertEqual(calls[0]["extra_headers"]["HTTP-Referer"], "http://127.0.0.1:5174")
            self.assertEqual(calls[0]["extra_headers"]["X-Title"], "EventHorizon")
        finally:
            if previous_litellm is None:
                sys.modules.pop("litellm", None)
            else:
                sys.modules["litellm"] = previous_litellm
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_model_config_status_preserves_openrouter_provider_for_anthropic_slug(self) -> None:
        saved = {key: os.environ.get(key) for key in ("AGENT_MODEL", "MODEL_NAME", "AGENT_PROVIDER", "MODEL_PROVIDER", "OPENROUTER_API_KEY")}
        original_loader = agent_main.load_workspace_model_config
        try:
            agent_main.load_workspace_model_config = lambda: None
            os.environ["AGENT_PROVIDER"] = "openrouter"
            os.environ["AGENT_MODEL"] = "openrouter/anthropic/claude-sonnet-4.5"
            os.environ["OPENROUTER_API_KEY"] = "test-key"

            status = _model_config_status()
            self.assertEqual(status["provider"], "openrouter")
            self.assertEqual(status["resolved_model"], "openrouter/anthropic/claude-sonnet-4.5")
            self.assertEqual(status["key_env"], "OPENROUTER_API_KEY")
            self.assertTrue(status["key_configured"])
        finally:
            agent_main.load_workspace_model_config = original_loader
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_sql_scope_validation(self) -> None:
        self.assertIsNone(_validate_select('SELECT COUNT(*) FROM "orders"', {"orders"}))
        self.assertIn("outside the selected folder", _validate_select("SELECT * FROM other", {"orders"}) or "")
        self.assertIn("Schema-qualified", _validate_select("SELECT * FROM uploads.orders", {"orders"}) or "")
        self.assertIn("Only direct SELECT", _validate_select("WITH x AS (SELECT 1) SELECT * FROM x", {"x"}) or "")
        self.assertIn("Only direct SELECT", _validate_select("DROP TABLE orders", {"orders"}) or "")
        self.assertIn("Multiple SQL", _validate_select("SELECT * FROM orders; SELECT * FROM users", {"orders"}) or "")


if __name__ == "__main__":
    unittest.main()
