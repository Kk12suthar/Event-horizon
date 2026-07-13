from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    """One shared MCP/agent tool definition."""

    name: str
    title: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    annotations: dict[str, Any] = field(default_factory=dict)
    surfaces: frozenset[str] = field(default_factory=lambda: frozenset({"chat"}))
