"""In-process data-tool provider for the LangGraph agent.

Exposes the shared :data:`tools.data_tools.DATA_TOOLS` registry to the agent
with the *same surface* as the MCP client session (``openai_tools``,
``tool_names``, ``call``) - but dispatches handlers **directly in-process**
instead of spawning an MCP subprocess per request. This removes interpreter
cold-start, re-imports, and new DB connections from the request hot path while
reusing the identical, hardened tool definitions the MCP server exposes to
external clients.

Security is unchanged and enforced here, not by the model:
- ``folder_id`` is forced to the request's folder on every call, so the model
  can never reach across folder boundaries.
- ``user_id`` is injected from the trusted request context; the model only
  chooses *which* tool to call and *what* arguments (besides scope) to pass.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tools.data_tools import TOOLS_BY_NAME, openai_tool_schemas

logger = logging.getLogger("eventhorizon.agent_server.inprocess_tools")

FOLDER_SCOPED_ARG = "folder_id"
_MAX_RESULT_CHARS = 8000


class InProcessToolProvider:
    """A drop-in replacement for ``MCPSession`` backed by direct handler calls."""

    def __init__(
        self,
        user_id: str | None,
        folder_id: str | None,
        *,
        surface: str,
        session_id: str | None = None,
        selected_table_id: str | None = None,
        selected_table_name: str | None = None,
    ):
        self._user_id = user_id
        self._folder_id = folder_id
        self._surface = surface
        self._session_id = session_id
        self._selected_table_id = selected_table_id
        self._selected_table_name = selected_table_name
        self.openai_tools = openai_tool_schemas(surface, include_context=False)

    @property
    def tool_names(self) -> list[str]:
        return [t["function"]["name"] for t in self.openai_tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke a data tool and return its result as compact text for the LLM."""
        spec = TOOLS_BY_NAME.get(name)
        if spec is None:
            return f"Unknown tool '{name}'."
        if spec.surfaces and self._surface not in spec.surfaces:
            return f"Tool '{name}' is not available on the {self._surface} surface."
        args = dict(arguments or {})
        # Force folder scope and trusted identity - never model-controlled.
        args[FOLDER_SCOPED_ARG] = self._folder_id
        args["session_id"] = self._session_id
        args["selected_table_id"] = self._selected_table_id
        args["selected_table_name"] = self._selected_table_name
        args.pop("user_id", None)
        try:
            result = spec.handler(user_id=self._user_id, **args)
        except TypeError as exc:
            return f"Tool '{name}' rejected the given arguments: {exc}"
        except Exception as exc:  # surface tool errors to the model + trail
            logger.warning("In-process tool '%s' failed: %s", name, exc)
            return f"Tool '{name}' failed: {exc}"
        try:
            return json.dumps(result, default=str)[:_MAX_RESULT_CHARS]
        except Exception:
            return str(result)[:_MAX_RESULT_CHARS]
