from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import graph.builder as builder


class FakeProvider:
    """Stands in for the in-process tool provider."""

    openai_tools = [
        {"type": "function", "function": {"name": "data_list_tables", "description": "", "parameters": {}}}
    ]
    tool_names = ["data_list_tables"]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return '{"table_count": 2}'


class StreamingAgentTests(unittest.TestCase):
    def test_tool_loop_captures_grounded_final_answer_and_totals_usage(self) -> None:
        # Scripted streaming turns: first a tool call, then a final content answer.
        turns = [
            (
                {"content": "Let me list the tables.", "tool_calls": [{"id": "c1", "name": "data_list_tables", "arguments": "{}"}]},
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
            (
                {"content": "There are 2 tables in this folder.", "tool_calls": []},
                {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            ),
        ]
        index = {"i": 0}

        async def fake_astream_with_tools(messages, tools, model_config, on_reasoning=None):
            turn = turns[index["i"]]
            index["i"] += 1
            # Exercise the reasoning callback path too.
            if on_reasoning and turn[0].get("content") and turn[0].get("tool_calls"):
                on_reasoning(turn[0]["content"])
            return turn

        original = builder.astream_with_tools
        builder.astream_with_tools = fake_astream_with_tools
        try:
            provider = FakeProvider()
            state = {"user_message": "how many tables?", "available_tables": [{"name": "orders"}], "folder_id": "f1"}
            result = asyncio.run(builder._run_tool_loop(state, provider, model_config=object(), folder_id="f1"))
        finally:
            builder.astream_with_tools = original

        # The grounded answer is captured from the loop (no template fallback).
        self.assertEqual(result["final_response"], "There are 2 tables in this folder.")
        self.assertTrue(result["agent_evidence"])
        # The tool actually ran once.
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0][0], "data_list_tables")
        # Usage is summed across both streamed turns.
        self.assertEqual(result["token_usage"]["total_tokens"], 27)
        self.assertEqual(result["token_usage"]["prompt_tokens"], 18)

    def test_build_final_response_reports_missing_model_clearly(self) -> None:
        # With no model configured, the fallback names the real problem instead of
        # telling the user (misleadingly) that there are no tables.
        original = builder.load_effective_model_config
        builder.load_effective_model_config = lambda *_a, **_k: None
        try:
            message = builder.build_final_response({"available_tables": [{"name": "orders"}], "folder_id": "f1"})
        finally:
            builder.load_effective_model_config = original
        self.assertIn("No AI model is configured", message)


if __name__ == "__main__":
    unittest.main()
