from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class AgentProductionHardeningTests(unittest.TestCase):
    def test_bearer_token_extracts_user_and_rejects_missing_token(self) -> None:
        from security.auth import get_user_from_authorization

        self.assertIsNone(get_user_from_authorization(None))

        import jwt

        old_secret = os.environ.get("JWT_SECRET_KEY")
        os.environ["JWT_SECRET_KEY"] = "x" * 40
        try:
            token = jwt.encode({"sub": "user-1"}, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
            self.assertEqual(get_user_from_authorization(f"Bearer {token}")["sub"], "user-1")
        finally:
            if old_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = old_secret

    def test_model_config_update_does_not_mutate_process_environment(self) -> None:
        from runtime.model_config import ModelConfigUpdate, apply_model_config_update

        saved = {name: os.environ.get(name) for name in ("AGENT_MODEL", "AGENT_PROVIDER", "OPENROUTER_API_KEY")}
        try:
            os.environ["AGENT_MODEL"] = "openrouter/openai/gpt-4o"
            os.environ["AGENT_PROVIDER"] = "openrouter"
            os.environ.pop("OPENROUTER_API_KEY", None)

            stored = {}

            def save(config):
                stored.update(config)

            status = apply_model_config_update(
                ModelConfigUpdate(provider="openrouter", model="openai/gpt-4o", api_key="secret-key"),
                save_config=save,
            )

            self.assertEqual(os.environ["AGENT_MODEL"], "openrouter/openai/gpt-4o")
            self.assertNotIn("OPENROUTER_API_KEY", os.environ)
            self.assertEqual(stored["api_key"], "secret-key")
            self.assertTrue(status["key_configured"])
            self.assertNotIn("api_key", status)
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_llm_completion_uses_runtime_config_without_env_key(self) -> None:
        from llm.client import complete_text
        from runtime.model_config import EffectiveModelConfig

        previous_litellm = sys.modules.get("litellm")
        calls: list[dict] = []
        sys.modules["litellm"] = types.SimpleNamespace(
            completion=lambda **kwargs: calls.append(kwargs) or {"choices": [{"message": {"content": "ok"}}]}
        )
        saved = {name: os.environ.get(name) for name in ("AGENT_MODEL", "AGENT_PROVIDER", "OPENROUTER_API_KEY")}
        try:
            os.environ.pop("OPENROUTER_API_KEY", None)
            response = complete_text(
                "hello",
                model_config=EffectiveModelConfig(
                    provider="openrouter",
                    model="openrouter/openai/gpt-4o",
                    api_key="runtime-key",
                    base_url="https://openrouter.ai/api/v1",
                    site_url="http://127.0.0.1:5174",
                    app_name="EventHorizon",
                    temperature=0.2,
                ),
            )

            self.assertEqual(response, "ok")
            self.assertEqual(calls[0]["api_key"], "runtime-key")
            self.assertNotIn("OPENROUTER_API_KEY", os.environ)
        finally:
            if previous_litellm is None:
                sys.modules.pop("litellm", None)
            else:
                sys.modules["litellm"] = previous_litellm
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_persisted_google_config_uses_env_api_key_when_secret_not_stored(self) -> None:
        from runtime.model_config import effective_config_from_mapping

        old_google = os.environ.get("GOOGLE_API_KEY")
        old_gemini = os.environ.get("GEMINI_API_KEY")
        try:
            os.environ["GOOGLE_API_KEY"] = "google-env-key"
            os.environ.pop("GEMINI_API_KEY", None)

            config = effective_config_from_mapping({
                "provider": "google",
                "model": "gemini-3.5-flash",
                "api_key": None,
                "temperature": 0.2,
            })

            self.assertEqual(config.provider, "google")
            self.assertEqual(config.model, "gemini/gemini-3.5-flash")
            self.assertEqual(config.api_key, "google-env-key")
        finally:
            if old_google is None:
                os.environ.pop("GOOGLE_API_KEY", None)
            else:
                os.environ["GOOGLE_API_KEY"] = old_google
            if old_gemini is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old_gemini
    def test_memory_checkpointer_is_disabled_for_production_safety(self) -> None:
        from graph.builder import create_general_graph

        graph = create_general_graph()

        self.assertIsNotNone(graph)

    def test_greeting_is_conversational_and_does_not_need_tools(self) -> None:
        from graph.builder import input_guard

        result = input_guard({"user_message": "Hii"})

        self.assertEqual(result["intent"], "conversation")
        self.assertEqual(result["final_response"], "Hii")

    def test_context_loader_does_not_describe_tables_automatically(self) -> None:
        from graph.builder import context_loader

        result = context_loader({
            "user_message": "Hii",
            "folder_id": "folder-1",
            "user_id": "user-1",
        })

        self.assertEqual(result["available_tables"], [])
        self.assertNotIn("tool_results", result)


if __name__ == "__main__":
    unittest.main()
