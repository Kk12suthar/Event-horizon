from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # langgraph < 0.4 compatibility
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver

from graph.state import AgentState
from tools.inprocess import FOLDER_SCOPED_ARG, InProcessToolProvider
from llm.client import (
    EMPTY_USAGE,
    astream_text,
    astream_with_tools,
    complete_text,
    merge_usage,
)
from runtime.model_config import load_effective_model_config
from runtime.model_store import load_workspace_model_config
from tools.postgres import execute_select, get_folder_status

logger = logging.getLogger("eventhorizon.agent_server.graph")

# Safety cap on the number of LLM<->tool round-trips per request.
MAX_TOOL_ITERATIONS = 6
CONVERSATIONAL_MESSAGES = {
    "hi",
    "hii",
    "hello",
    "hey",
    "yo",
    "thanks",
    "thank you",
}


def _is_conversation_message(message: str) -> bool:
    normalized = " ".join(message.lower().replace("!", " ").replace(".", " ").split())
    return normalized in CONVERSATIONAL_MESSAGES


def _conversation_response(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if normalized.lower() == "hii":
        return "Hii"
    if normalized.lower() in {"thanks", "thank you"}:
        return "You are welcome."
    return "Hi"


def create_general_graph():
    graph = StateGraph(AgentState)
    graph.add_node("input_guard", input_guard)
    graph.add_node("context_loader", context_loader)
    graph.add_node("intent_router", intent_router)
    graph.add_node("data_agent", data_agent)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("finalizer", finalizer)

    graph.add_edge(START, "input_guard")
    graph.add_edge("input_guard", "context_loader")
    graph.add_edge("context_loader", "intent_router")
    graph.add_edge("intent_router", "data_agent")
    graph.add_edge("data_agent", "tool_executor")
    graph.add_edge("tool_executor", "finalizer")
    graph.add_edge("finalizer", END)

    return graph.compile()


def input_guard(state: AgentState) -> dict[str, Any]:
    message = (state.get("user_message") or "").strip()
    emit({"type": "agent_start", "agent_name": "orchestrator", "message": "General agent processing...", "timestamp": now()})

    if not message:
        error = {"message": "Query is required."}
        emit({"type": "error", "message": error["message"], "timestamp": now()})
        return {"errors": [error], "final_response": error["message"]}

    lowered = message.lower()
    blocked = ["drop table", "truncate", "grant ", "revoke ", "copy ", "create function", "create trigger"]
    if any(token in lowered for token in blocked):
        error = {"message": "That request is blocked because it asks for a high-risk database operation."}
        emit({"type": "error", "message": error["message"], "timestamp": now()})
        return {"errors": [error], "final_response": error["message"]}

    if _is_conversation_message(message):
        return {"intent": "conversation", "final_response": _conversation_response(message)}

    emit({"type": "status", "title": "Input Check", "message": "Request accepted.", "level": "success", "timestamp": now()})
    return {}


def context_loader(state: AgentState) -> dict[str, Any]:
    if state.get("errors") or state.get("final_response"):
        return {}

    if not state.get("folder_id"):
        emit({"type": "status", "title": "Context", "message": "No folder selected. I can answer generally, but data tools need a folder.", "level": "warning", "timestamp": now()})

    # Do not pre-load table schemas here. Data MCP tools are advertised to the
    # LLM in mcp_agent with tool_choice="auto", so the model decides whether a
    # request needs schema discovery, querying, or no tool calls at all.
    return {"available_tables": []}


def intent_router(state: AgentState) -> dict[str, Any]:
    if state.get("errors") or state.get("final_response"):
        return {}

    explicit = state.get("intent")
    if explicit:
        return {"intent": explicit}

    message = (state.get("user_message") or "").lower()
    if _is_conversation_message(message):
        intent = "conversation"
    elif any(word in message for word in ["report", "pdf", "ppt", "powerpoint", "docx", "document"]):
        intent = "report"
    elif any(word in message for word in ["chart", "graph", "plot", "visual", "dashboard"]):
        intent = "chart"
    elif any(word in message for word in ["quality", "null", "missing", "duplicate", "clean"]):
        intent = "data_quality"
    elif any(word in message for word in ["schema", "columns", "tables", "fields"]):
        intent = "schema"
    else:
        intent = "analysis"

    emit({"type": "status", "title": "Routing", "message": f"Intent: {intent}", "level": "info", "timestamp": now()})
    return {"intent": intent}


async def data_agent(state: AgentState) -> dict[str, Any]:
    """LLM-driven agent that gathers evidence by calling in-process data tools.

    Uses the shared tool registry directly (no MCP subprocess) for low latency,
    advertises the read-only folder-scoped tools to the model, and runs a
    bounded, streaming tool-calling loop. Reasoning tokens are streamed as
    ``thinking_delta`` events, tool calls as ``function_request`` /
    ``function_response``, and token usage is accumulated for the completion
    event. The folder scope and user identity are enforced here, never chosen by
    the model.

    Degrades gracefully: with no folder, no configured model, or any failure it
    returns ``{}`` so the deterministic ``tool_executor`` + ``finalizer`` path
    still produces an answer.
    """
    if state.get("errors") or state.get("final_response") or state.get("intent") == "conversation":
        return {}

    folder_id = state.get("folder_id")
    user_id = state.get("user_id")
    if not folder_id:
        return {}

    model_config = load_effective_model_config(load_workspace_model_config)
    if model_config is None or not getattr(model_config, "model", None):
        return {}

    try:
        provider = InProcessToolProvider(user_id, folder_id)
        if not provider.openai_tools:
            return {}
        emit({"type": "agent_transition", "from_agent": "orchestrator", "to_agent": "data_agent", "label": "Data Agent", "reason": "Answering a data question with folder tools.", "timestamp": now()})
        emit({
            "type": "status",
            "title": "Tools",
            "message": f"Connected to data tools ({', '.join(provider.tool_names)}).",
            "level": "info",
            "timestamp": now(),
        })
        # Discover the folder's tables once so both the model and the final
        # answer have real table context (prevents "no tables" answers even
        # after tools have run).
        try:
            status = get_folder_status(folder_id, user_id=user_id)
            table_names = [n for n in (status.get("tables") or []) if n]
        except Exception:
            table_names = []
        available = [{"name": name} for name in table_names]
        loop_state = {**state, "available_tables": available}
        result = await _run_tool_loop(loop_state, provider, model_config, folder_id)
        result.setdefault("available_tables", available)
        return result
    except Exception as exc:
        logger.warning("Data agent unavailable, falling back to deterministic path: %s", exc)
        emit({
            "type": "status",
            "title": "Tools",
            "message": "Live data tools unavailable; using built-in analysis.",
            "level": "warning",
            "timestamp": now(),
        })
        return {}


async def _run_tool_loop(state: AgentState, provider: InProcessToolProvider, model_config, folder_id: str) -> dict[str, Any]:
    tables = state.get("available_tables") or []
    table_names = ", ".join(t.get("name", "") for t in tables if t.get("name")) or "(none discovered yet)"

    system_prompt = (
        "You are EventHorizon, a production data workspace assistant. Answer the "
        "user's question about their data by calling the provided read-only tools "
        "to gather evidence, then giving a clear, grounded final answer.\n"
        "Rules:\n"
        "- Before calling a tool, briefly state your reasoning in ONE short sentence; this is shown to the user as your thinking.\n"
        f"- Operate ONLY on folder_id '{folder_id}'. Always pass this exact folder_id to tools.\n"
        f"- Tables available in this folder: {table_names}.\n"
        "- For large tables, prefer data_row_count (estimate), data_aggregate, and "
        "data_column_stats over reading raw rows, to stay fast and token-light.\n"
        "- Use data_list_tables / data_describe_tables to discover schema when unsure.\n"
        "- Do not repeat a tool call that already appears in the gathered evidence.\n"
        "- Never invent data, columns, or numbers. Base every claim on tool results.\n"
        "- When you have enough evidence, reply with a concise final answer and NO further tool call."
    )
    user_question = state.get("user_message", "")

    evidence: list[dict[str, Any]] = []
    results = list(state.get("tool_results") or [])
    usage_total = dict(state.get("token_usage") or EMPTY_USAGE)
    used_tools = False
    thinking_open = False
    final_text = ""

    def on_reasoning(delta: str) -> None:
        nonlocal thinking_open
        if not delta:
            return
        if not thinking_open:
            emit({"type": "thinking_start", "agent_name": "data_agent", "timestamp": now()})
            thinking_open = True
        emit({"type": "thinking_delta", "agent_name": "data_agent", "delta": delta, "timestamp": now()})

    for _ in range(MAX_TOOL_ITERATIONS):
        message, usage = await astream_with_tools(
            _loop_messages(system_prompt, user_question, evidence),
            provider.openai_tools,
            model_config,
            on_reasoning=on_reasoning,
        )
        usage_total = merge_usage(usage_total, usage)
        if message is None:
            break

        tool_calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()

        # No more tool calls -> the model's content IS the grounded final answer.
        if not tool_calls:
            if thinking_open:
                emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})
                thinking_open = False
            final_text = content
            break

        # Otherwise any content is the model narrating its plan -> show as thinking.
        if content:
            on_reasoning(content)
        if thinking_open:
            emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})
            thinking_open = False

        used_tools = True
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else dict(tc["arguments"] or {})
            except (TypeError, ValueError):
                args = {}
            # Enforce folder scope: the model never controls which folder is read.
            if FOLDER_SCOPED_ARG in args or name.startswith("data_"):
                args[FOLDER_SCOPED_ARG] = folder_id

            call_id = tc["id"] or f"tool_{uuid.uuid4().hex[:8]}"
            display_args = {k: v for k, v in args.items() if k != FOLDER_SCOPED_ARG}
            emit({
                "type": "function_request",
                "tool_name": name,
                "tool_args": display_args or {"request": name},
                "call_id": call_id,
                "agent_name": "data_agent",
                "timestamp": now(),
            })
            try:
                tool_text = await provider.call(name, args)
            except Exception as exc:
                tool_text = f"Tool '{name}' failed: {exc}"
            emit({
                "type": "function_response",
                "tool_name": name,
                "response": {"result": tool_text[:6000]},
                "call_id": call_id,
                "agent_name": "data_agent",
                "timestamp": now(),
            })
            results.append({"tool": name, "args": display_args, "result": tool_text})
            evidence.append({"tool": name, "args": display_args, "result": tool_text})

    if thinking_open:
        emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})

    if not final_text and (evidence or used_tools):
        # The model gathered evidence but hit the iteration cap without a final
        # answer. Force a grounded summary through the same (working) completion
        # path used for tool calls, rather than a separate streaming call.
        closing, usage = await astream_with_tools(
            _loop_messages(system_prompt, user_question, evidence, force_answer=True),
            [],
            model_config,
            on_reasoning=on_reasoning,
        )
        usage_total = merge_usage(usage_total, usage)
        if thinking_open:
            emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})
        if closing:
            final_text = (closing.get("content") or "").strip()

    result: dict[str, Any] = {
        "tool_results": results,
        "token_usage": usage_total,
        "agent_evidence": used_tools or bool(evidence),
    }
    if final_text:
        result["final_response"] = final_text
    return result


def _loop_messages(
    system_prompt: str,
    user_question: str,
    evidence: list[dict[str, Any]],
    force_answer: bool = False,
) -> list[dict[str, Any]]:
    """Build a fresh message list for one tool-loop turn from the scratchpad."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]
    if evidence:
        lines = []
        for i, step in enumerate(evidence, 1):
            args = json.dumps(step.get("args", {}), default=str)
            result = str(step.get("result", ""))[:2000]
            lines.append(f"[{i}] {step.get('tool')}({args}) ->\n{result}")
        scratchpad = "Evidence gathered from the data tools so far:\n\n" + "\n\n".join(lines)
        if force_answer:
            scratchpad += "\n\nProvide your final answer now, based only on this evidence."
        else:
            scratchpad += "\n\nIf this is enough to answer, reply now with no tool call. Otherwise call another tool."
        messages.append({"role": "user", "content": scratchpad})
    return messages


def tool_executor(state: AgentState) -> dict[str, Any]:
    if state.get("errors") or state.get("intent") == "conversation":
        return {}

    # The data agent already produced grounded evidence via tool calls; skip the
    # deterministic SQL/artifact path to avoid duplicate work and events.
    if state.get("final_response") or state.get("agent_evidence"):
        return {}

    intent = state.get("intent") or "analysis"
    tables = state.get("available_tables") or []
    results = list(state.get("tool_results") or [])
    artifacts = list(state.get("artifacts") or [])

    if not tables:
        return {"tool_results": results, "artifacts": artifacts}

    selected = set(t.lower() for t in state.get("selected_tables") or [])
    table = next((t for t in tables if t.get("name", "").lower() in selected), tables[0])
    table_name = table.get("name")

    if not table_name:
        return {"tool_results": results, "artifacts": artifacts}

    if intent in {"analysis", "data_quality", "chart", "report"}:
        call_id = f"sql_{uuid.uuid4().hex[:8]}"
        query = f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}"
        emit({
            "type": "function_request",
            "tool_name": "execute_select",
            "tool_args": {"request": query},
            "call_id": call_id,
            "agent_name": "data_tools",
            "timestamp": now(),
        })
        result = execute_select(state.get("folder_id"), query, user_id=state.get("user_id"))
        emit({
            "type": "function_response",
            "tool_name": "execute_select",
            "response": {"result": json.dumps(result, default=str)[:6000]},
            "call_id": call_id,
            "agent_name": "data_tools",
            "timestamp": now(),
        })
        results.append({"tool": "execute_select", "query": query, "result": result})

    if intent == "chart":
        artifacts.append({
            "type": "chart_spec",
            "title": f"Starter chart for {table_name}",
            "data": {
                "table": table_name,
                "suggestion": "Choose one categorical column and one numeric column to build a chart.",
                "columns": table.get("columns", []),
            },
        })
        emit({"type": "status", "title": "Chart", "message": f"Prepared a starter chart plan for {table_name}.", "level": "success", "timestamp": now()})

    if intent == "data_quality":
        table = dict(table, _user_id=state.get("user_id"))
        null_results = run_null_profile(state.get("folder_id"), table)
        if null_results:
            results.append({"tool": "null_profile", "result": null_results})

    return {"tool_results": results, "artifacts": artifacts}


async def finalizer(state: AgentState) -> dict[str, Any]:
    start = time.time()
    usage_total = dict(state.get("token_usage") or EMPTY_USAGE)

    if state.get("errors"):
        final = state.get("final_response") or state["errors"][0]["message"]
    elif state.get("final_response"):
        # A conversational / short-circuit answer is already set; stream it out
        # in small chunks so the UI renders it progressively.
        final = state["final_response"]
        _emit_answer_chunks(final)
    else:
        # Stream a grounded final answer token-by-token from the gathered evidence.
        final, usage = await _stream_final_answer(state)
        usage_total = merge_usage(usage_total, usage)
        if not final:
            final = build_final_response(state)
            _emit_answer_chunks(final)

    emit({"type": "final_response", "text": final, "agent_name": "responder", "timestamp": now()})
    emit({
        "type": "completion",
        "final_output": final,
        "time_taken": round(time.time() - start, 2),
        "token_usage": usage_total,
        "chart_ids": [],
        "query_id": state.get("query_id") or str(uuid.uuid4()),
        "query": state.get("user_message", ""),
        "timestamp": now(),
    })
    return {"final_response": final, "token_usage": usage_total}


def _emit_answer_chunks(text: str, size: int = 48) -> None:
    """Emit a non-streamed (template/short) answer as answer_delta chunks so the
    frontend can render it with the same progressive path as streamed answers."""
    if not text:
        return
    for i in range(0, len(text), size):
        emit({"type": "answer_delta", "delta": text[i : i + size], "timestamp": now()})


async def _stream_final_answer(state: AgentState) -> tuple[str, dict[str, Any]]:
    """Compose and stream the grounded final answer, returning (text, usage)."""
    model_config = load_effective_model_config(load_workspace_model_config)
    if model_config is None or not getattr(model_config, "model", None):
        return "", {}

    from_agent = "data_agent" if state.get("agent_evidence") else "orchestrator"
    emit({"type": "agent_transition", "from_agent": from_agent, "to_agent": "responder", "label": "Responder", "reason": "Composing the final answer.", "timestamp": now()})

    system_prompt, prompt = _final_prompt(state)

    def on_delta(delta: str) -> None:
        if delta:
            emit({"type": "answer_delta", "delta": delta, "timestamp": now()})

    text, usage = await astream_text(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        model_config,
        on_delta=on_delta,
    )
    return text.strip(), usage


def _final_prompt(state: AgentState) -> tuple[str, str]:
    tables = state.get("available_tables") or []
    tool_results = state.get("tool_results") or []
    artifacts = state.get("artifacts") or []

    system_prompt = """You are EventHorizon, a production-grade general data workspace assistant.

Rules:
- Answer only from the current request state, current folder context, and tool evidence provided in the prompt.
- Do not assume a specific industry, process-mining domain, hidden table, hidden file, or previous user/session context.
- Do not invent metrics, columns, charts, reports, or database results.
- If data is missing, say exactly what is missing and what the user should do next.
- Never ask for or reveal API keys, secrets, credentials, raw connection strings, or internal server paths.
- Never suggest destructive SQL or database mutations.
- Keep answers concise, practical, and directly useful to the current workspace task.
"""

    prompt = f"""Current isolated context:
- surface: {state.get("surface") or "agent"}
- user_id: {state.get("user_id") or "unknown"}
- project_id: {state.get("project_id") or "none"}
- folder_id: {state.get("folder_id") or "none"}
- session_id: {state.get("session_id") or "none"}
- intent: {state.get("intent") or "analysis"}

User request:
{state.get("user_message", "")}

Available tables for this folder only:
{json.dumps(tables[:8], default=str)}

Tool evidence from this request:
{json.dumps(tool_results[-8:], default=str)}

Artifacts prepared in this request:
{json.dumps(artifacts, default=str)}
"""
    return system_prompt, prompt


def build_final_response(state: AgentState) -> str:
    system_prompt, prompt = _final_prompt(state)
    tables = state.get("available_tables") or []
    tool_results = state.get("tool_results") or []

    model_config = load_effective_model_config(load_workspace_model_config)
    if model_config is None or not getattr(model_config, "model", None):
        return (
            "No AI model is configured for the agent yet. An admin needs to set a "
            "model and API key in Settings (agent model config), then try again."
        )

    llm_response = complete_text(prompt, system_prompt=system_prompt, model_config=model_config)
    if llm_response:
        return llm_response

    if not tables:
        return "I don't see any tables in this folder yet. Upload a CSV or spreadsheet in Sources, then ask me again."

    table_names = ", ".join(t.get("name", "unknown") for t in tables[:5])
    row_notes = []
    for result in tool_results:
        if result.get("tool") == "execute_select":
            data = result.get("result", {})
            rows = data.get("rows") or []
            if rows:
                row_notes.append(f"{result.get('query')}: {rows[0]}")
            elif data.get("error"):
                row_notes.append(f"{result.get('query')}: {data.get('error')}")

    lines = [
        f"I found {len(tables)} table(s) in this folder: {table_names}.",
    ]
    if row_notes:
        lines.append("Initial evidence: " + " | ".join(row_notes[:2]))
    lines.append("Ask for a chart, data quality check, summary, or report and I will use only this folder's data context.")
    return "\n\n".join(lines)

def run_null_profile(folder_id: str | None, table: dict[str, Any]) -> dict[str, Any] | None:
    if not folder_id:
        return None
    table_name = table.get("name")
    columns = [c.get("name") for c in table.get("columns", []) if c.get("name")]
    columns = columns[:10]
    if not table_name or not columns:
        return None

    expressions = ", ".join([
        f'SUM(CASE WHEN {quote_identifier(col)} IS NULL THEN 1 ELSE 0 END) AS {quote_identifier(f"{col}_nulls")}'
        for col in columns
    ])
    query = f'SELECT {expressions} FROM {quote_identifier(table_name)}'
    call_id = f"nulls_{uuid.uuid4().hex[:8]}"
    emit({
        "type": "function_request",
        "tool_name": "null_profile",
        "tool_args": {"request": query},
        "call_id": call_id,
        "agent_name": "data_quality",
        "timestamp": now(),
    })
    result = execute_select(folder_id, query, user_id=table.get("_user_id"))
    emit({
        "type": "function_response",
        "tool_name": "null_profile",
        "response": {"result": json.dumps(result, default=str)[:6000]},
        "call_id": call_id,
        "agent_name": "data_quality",
        "timestamp": now(),
    })
    return result


def emit(event: dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
        writer(event)
    except RuntimeError:
        pass


def now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"


def quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'
