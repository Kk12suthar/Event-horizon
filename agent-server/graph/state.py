from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    surface: str
    session_id: str
    folder_id: Optional[str]
    project_id: Optional[str]
    user_id: str
    query_id: str
    user_message: str
    selected_tables: list[str]
    available_tables: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    intent: Optional[str]
    final_response: Optional[str]
    errors: list[dict[str, Any]]
    # Accumulated LLM token usage across every model call in the request.
    token_usage: dict[str, int]
    # True once the data agent has gathered evidence via tool calls, so the
    # deterministic fallback executor can be skipped.
    agent_evidence: bool

