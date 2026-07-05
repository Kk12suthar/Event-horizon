"""Client-side bridge between the LangGraph agent and the EventHorizon Data MCP server.

The agent does not import ``tools/postgres`` directly for its data work. Instead it
spawns the local MCP server (``mcp_server.server``) over **stdio** - the real MCP
protocol - lists the tools it advertises, and lets the LLM call them. This keeps the
data layer behind a single, hardened, reusable MCP surface that any MCP client can use.

Trusted identity is injected out-of-band: the authenticated ``user_id`` is passed to
the child process via the ``EVENTHORIZON_AGENT_USER_ID`` environment variable so the
server's ``require_folder_access`` checks run against the real user. The LLM only ever
chooses *which* tool to call and *what* SQL to run - never *who* it is.

Usage::

    async with mcp_session(user_id) as mcp:
        tools = mcp.openai_tools           # OpenAI/LiteLLM function schemas
        text = await mcp.call("data_run_query", {"folder_id": fid, "sql": "select 1"})
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger("eventhorizon.agent_server.mcp_client")

# .../agent-server (so `python -m mcp_server.server` resolves and DB env is shared).
AGENT_ROOT = Path(__file__).resolve().parents[1]

# Tools whose `folder_id` argument must be forced to the request's folder so the
# model can never reach across folder boundaries.
FOLDER_SCOPED_ARG = "folder_id"


class MCPSession:
    """A live MCP client session exposing tool schemas and a call helper."""

    def __init__(self, session: Any, openai_tools: list[dict[str, Any]]):
        self._session = session
        self.openai_tools = openai_tools

    @property
    def tool_names(self) -> list[str]:
        return [t["function"]["name"] for t in self.openai_tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke an MCP tool and return its result as text for the LLM."""
        result = await self._session.call_tool(name, arguments)
        return _result_to_text(result)


def _result_to_text(result: Any) -> str:
    """Flatten an MCP CallToolResult into a compact string for the LLM."""
    structured = getattr(result, "structuredContent", None)
    if structured:
        try:
            return json.dumps(structured, default=str)[:8000]
        except Exception:
            pass
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    flattened = "\n".join(parts).strip()
    if getattr(result, "isError", False) and not flattened:
        return "Tool reported an error with no message."
    return flattened[:8000] or "(no output)"


def _openai_tool_from_mcp(tool: Any) -> dict[str, Any]:
    """Convert an MCP tool descriptor into an OpenAI/LiteLLM function schema."""
    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (getattr(tool, "description", None) or "").strip(),
            "parameters": schema,
        },
    }


def _child_env(user_id: str | None) -> dict[str, str]:
    """Environment for the MCP child: inherit ours (DB creds) + trusted identity."""
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["MCP_TRANSPORT"] = "stdio"
    if user_id:
        env["EVENTHORIZON_AGENT_USER_ID"] = str(user_id)
    else:
        env.pop("EVENTHORIZON_AGENT_USER_ID", None)
    return env


@asynccontextmanager
async def mcp_session(user_id: str | None) -> AsyncIterator[MCPSession]:
    """Spawn the MCP server over stdio and yield a ready-to-use {@link MCPSession}.

    The child process and session are torn down when the context exits. Raises if
    the MCP SDK is unavailable or the server fails to start/list tools; callers
    should catch and fall back to a non-MCP path.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env=_child_env(user_id),
        cwd=str(AGENT_ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            openai_tools = [_openai_tool_from_mcp(t) for t in listed.tools]
            logger.info("MCP session ready with %d tools: %s", len(openai_tools), ", ".join(t.name for t in listed.tools))
            yield MCPSession(session, openai_tools)
