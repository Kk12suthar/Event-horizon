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
from runtime.user_model_config import load_effective_model_config
from runtime.user_model_store import load_user_model_config
from tools.postgres import execute_select

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


def is_conversation_message(message: str) -> bool:
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

    if is_conversation_message(message):
        return {"intent": "conversation", "final_response": _conversation_response(message)}

    return {}


def context_loader(state: AgentState) -> dict[str, Any]:
    if state.get("errors") or state.get("final_response"):
        return {}

    surface = state.get("surface") or "chat"
    if surface in {"dashboard", "report"} and not state.get("selected_table_id"):
        message = "Create and select a prepared table in Prepare first."
        emit({"type": "error", "message": message, "timestamp": now()})
        return {"errors": [{"message": message}], "final_response": message}

    selected_name = state.get("selected_table_name")
    available = [{"name": selected_name, "source": "agent_created"}] if selected_name else []
    return {"available_tables": available}


def intent_router(state: AgentState) -> dict[str, Any]:
    if state.get("errors") or state.get("final_response"):
        return {}

    explicit = state.get("intent")
    if explicit:
        return {"intent": explicit}

    message = (state.get("user_message") or "").lower()
    if is_conversation_message(message):
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

    model_config = _model_config_for_state(state)
    if model_config is None or not getattr(model_config, "model", None):
        return {}

    try:
        surface = state.get("surface") or "chat"
        provider = InProcessToolProvider(
            user_id,
            folder_id,
            surface=surface,
            session_id=state.get("session_id"),
            selected_table_id=state.get("selected_table_id"),
            selected_table_name=state.get("selected_table_name"),
            project_id=state.get("project_id"),
            visual_document_id=state.get("visual_document_id"),
        )
        if not provider.openai_tools:
            return {}
        labels = {
            "chat": ("prepare_agent", "Prepare Agent"),
            "dashboard": ("visualize_agent", "Visualize Agent"),
            "report": ("publish_agent", "Publish Agent"),
            "canvas": ("canvas_agent", "Canvas Agent"),
        }
        agent_name, label = labels.get(surface, ("data_agent", "Data Agent"))
        emit({
            "type": "agent_transition",
            "from_agent": "orchestrator",
            "to_agent": agent_name,
            "label": label,
            "reason": "Handling the request with the tools allowed for this workspace mode.",
            "timestamp": now(),
        })
        available = list(state.get("available_tables") or [])
        loop_state = {**state, "available_tables": available}
        result = await _run_tool_loop(loop_state, provider, model_config, folder_id)
        result.setdefault("available_tables", available)
        return result
    except Exception as exc:
        logger.warning("Data agent unavailable: %s", exc)
        message = "The AI agent is currently unavailable. Please retry this request."
        emit({"type": "error", "message": message, "timestamp": now()})
        return {"errors": [{"message": message}], "final_response": message}


def _surface_system_prompt(state: AgentState, folder_id: str, table_names: str) -> str:
    surface = state.get("surface") or "chat"
    selected = state.get("selected_table_name") or "none"
    common = f"""You are EventHorizon operating in the {surface} workspace mode.

Rules:
- Decide whether a tool is needed. Never call tools for greetings, thanks, or casual conversation.
- Before a necessary tool call, explain the reason in one short sentence.
- Operate only inside folder_id '{folder_id}'. The runtime injects folder, user, session, and selected-table scope; never ask for or override them.
- Never invent tables, columns, metrics, chart values, report evidence, or tool results.
- Do not repeat a tool call when the evidence is already available.
- When enough evidence exists, answer directly with no further tool call.
"""
    if surface == "dashboard":
        return common + f"""
You are the Visualize agent. The only permitted data source is the selected prepared table '{selected}'.
Use viz_get_schema when column names are unknown. For chart and KPI requests, use viz_create_chart or viz_create_kpi so a grounded transient preview is emitted. Never claim a preview is saved; the user persists it with Add to dashboard. Use viz_aggregate, viz_time_series, or viz_correlation for analysis. Call update/delete tools only for an explicit request about an already saved chart. Never query uploaded source tables and never mutate data.
"""
    if surface == "report":
        return common + f"""
You are the Publish agent. Use only the selected prepared table '{selected}' and persisted, non-stale charts. Every report-generation request is data-dependent: before drafting or finalizing, you must call report_get_data_summary and report_list_charts successfully. Persist requested outline sections with report_create_section. Do not fabricate numbers or chart findings. The server handles PDF, HTML, PPTX, and DOCX export after your grounded final response.
"""
    if surface == "canvas":
        active_document = state.get("visual_document_id") or "none"
        return common + f"""
You are the Canvas agent. You create and edit validated Visual Documents, not raw frontend code.
The currently open visual document id is '{active_document}'.

Canvas workflow:
- If an open document id is provided, reuse it. Call canvas_inspect or canvas_summarize before a substantial edit so you preserve the existing work.
- If no document is open, call canvas_list first. Reuse the most relevant existing canvas when the user clearly refers to it; otherwise call canvas_create.
- For process maps and variant flows, prefer canvas_create_process_map or canvas_create_variant_paths over many tiny calls.
- For custom diagrams, compose nodes, edges, shapes, text, legends, charts, KPIs, and Gantt elements.
- Use data tools before creating a data-bearing visual. Numbers, columns, table ids, and metrics must come from tool evidence.
- After adding structural elements, call canvas_apply_layout and canvas_find_overlaps. Correct readability problems before finishing.
- Never invent element ids. Read them from tool results or canvas_inspect.
- Do not create a duplicate canvas merely because the user asks to change the open one.
- Explain the visual result briefly after the tools succeed.
"""
    return common + f"""
You are the Prepare agent. Tables are discovered only when the user's data request requires them; current known tables: {table_names}.
Use data_list_tables and data_describe_tables to inspect uploaded sources. Use prepare_detect_quality_issues for profiling. Each account may create only one prepared table. When the user explicitly asks to clean, join, combine, or create a final table and no prepared table exists yet, formulate one safe folder-scoped SELECT, validate it with prepare_plan_transform, then call prepare_build_transform. If the build tool reports prepared_table_limit_reached, do not retry it; direct the user to the existing table for Visualize and Publish. The build tool never changes uploaded sources. Do not stop after merely listing tables when the request asks for a transformation.
"""

async def _run_tool_loop(state: AgentState, provider: InProcessToolProvider, model_config, folder_id: str) -> dict[str, Any]:
    tables = state.get("available_tables") or []
    table_names = ", ".join(t.get("name", "") for t in tables if t.get("name")) or "(none discovered yet)"

    system_prompt = _surface_system_prompt(state, folder_id, table_names)
    user_question = state.get("user_message", "")

    evidence: list[dict[str, Any]] = []
    results = list(state.get("tool_results") or [])
    artifacts = list(state.get("artifacts") or [])
    usage_total = dict(state.get("token_usage") or EMPTY_USAGE)
    used_tools = False
    thinking_open = False
    final_text = ""
    required_grounding_tools = (
        {"report_get_data_summary", "report_list_charts"}
        if state.get("surface") == "report"
        else set()
    )
    grounding_instruction = ""
    grounding_nudges = 0

    def missing_grounding_tools() -> list[str]:
        successful = {
            str(step.get("tool"))
            for step in evidence
            if isinstance(step.get("result"), dict) and not step["result"].get("error")
        }
        return sorted(required_grounding_tools - successful)

    def grounding_failure(missing: list[str]) -> dict[str, Any]:
        message = (
            "The report was not generated because required table and chart evidence "
            f"could not be gathered ({', '.join(missing)}). Please retry."
        )
        emit({"type": "error", "message": message, "timestamp": now()})
        return {
            "tool_results": results,
            "token_usage": usage_total,
            "agent_evidence": bool(evidence),
            "artifacts": artifacts,
            "errors": [{"message": message}],
            "final_response": message,
        }

    async def execute_tool(name: str, args: dict[str, Any], call_id: str | None = None) -> bool:
        nonlocal used_tools
        used_tools = True
        arguments = dict(args or {})
        if FOLDER_SCOPED_ARG in arguments or name.startswith("data_"):
            arguments[FOLDER_SCOPED_ARG] = folder_id
        context = {
            "folder_id": folder_id,
            "session_id": state.get("session_id"),
            "selected_table_id": state.get("selected_table_id"),
            "selected_table_name": state.get("selected_table_name"),
        }
        display_args = {
            key: value
            for key, value in arguments.items()
            if key not in {FOLDER_SCOPED_ARG, "session_id", "selected_table_id", "selected_table_name", "user_id"}
        }
        display_args["context"] = {key: value for key, value in context.items() if value}
        resolved_call_id = call_id or f"tool_{uuid.uuid4().hex[:8]}"
        emit({
            "type": "function_request",
            "tool_name": name,
            "tool_args": display_args,
            "call_id": resolved_call_id,
            "agent_name": "data_agent",
            "timestamp": now(),
        })
        started = time.perf_counter()
        try:
            tool_text = await provider.call(name, arguments)
        except Exception as exc:
            tool_text = json.dumps({"error": f"Tool '{name}' failed: {exc}"})
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            tool_result = json.loads(tool_text)
        except (TypeError, ValueError):
            tool_result = {"result": tool_text}
        success = not bool(tool_result.get("error"))
        emit({
            "type": "function_response",
            "tool_name": name,
            "response": tool_result,
            "call_id": resolved_call_id,
            "agent_name": "data_agent",
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": now(),
        })
        artifact = tool_result.get("artifact")
        if isinstance(artifact, dict):
            artifact_type = str(artifact.get("artifact_type") or artifact.get("type") or "artifact")
            artifacts.append(artifact)
            emit({
                "type": "artifact",
                "artifact_type": artifact_type,
                "data": artifact,
                "artifact": artifact,
                "timestamp": now(),
            })
        results.append({"tool": name, "args": display_args, "result": tool_result, "duration_ms": duration_ms})
        evidence.append({"tool": name, "args": display_args, "result": tool_result})
        return success

    def on_reasoning(delta: str) -> None:
        nonlocal thinking_open
        if not delta:
            return
        if not thinking_open:
            emit({"type": "thinking_start", "agent_name": "data_agent", "timestamp": now()})
            thinking_open = True
        emit({"type": "thinking_delta", "agent_name": "data_agent", "delta": delta, "timestamp": now()})

    # Publish generation always needs these two bounded, read-only context reads.
    # Conversation messages never reach this function because request_filter exits first.
    for tool_name in sorted(required_grounding_tools):
        await execute_tool(
            tool_name,
            {"folder_id": folder_id, "session_id": state.get("session_id")},
            f"required_{tool_name}_{uuid.uuid4().hex[:8]}",
        )

    for _ in range(MAX_TOOL_ITERATIONS):
        message, usage = await astream_with_tools(
            _loop_messages(system_prompt, user_question, evidence, grounding_instruction=grounding_instruction),
            provider.openai_tools,
            model_config,
            on_reasoning=on_reasoning,
        )
        usage_total = merge_usage(usage_total, usage)
        if message is None:
            break

        tool_calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()

        # A report cannot finalize until its required evidence tools succeeded.
        if not tool_calls:
            if thinking_open:
                emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})
                thinking_open = False
            missing = missing_grounding_tools()
            if missing:
                if grounding_nudges < 2:
                    grounding_nudges += 1
                    grounding_instruction = (
                        "Do not draft the report yet. Required evidence is still missing. "
                        f"Call these tools now: {', '.join(missing)}."
                    )
                    continue
                return grounding_failure(missing)
            final_text = content
            break

        # Otherwise any content is the model narrating its plan -> show as thinking.
        if content:
            on_reasoning(content)
        if thinking_open:
            emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})
            thinking_open = False

        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else dict(tc["arguments"] or {})
            except (TypeError, ValueError):
                args = {}
            await execute_tool(name, args, tc["id"] or None)

    if thinking_open:
        emit({"type": "thinking_end", "agent_name": "data_agent", "timestamp": now()})

    missing = missing_grounding_tools()
    if missing:
        return grounding_failure(missing)

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
        "artifacts": artifacts,
    }
    if final_text:
        result["final_response"] = final_text
    return result


def _loop_messages(
    system_prompt: str,
    user_question: str,
    evidence: list[dict[str, Any]],
    force_answer: bool = False,
    grounding_instruction: str = "",
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
    if grounding_instruction:
        messages.append({"role": "user", "content": grounding_instruction})
    return messages


def tool_executor(state: AgentState) -> dict[str, Any]:
    """Compatibility node; all domain tools are selected by the LLM tool loop."""
    return {
        "tool_results": list(state.get("tool_results") or []),
        "artifacts": list(state.get("artifacts") or []),
    }


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
    artifacts = list(state.get("artifacts") or [])
    emit({
        "type": "completion",
        "final_output": final,
        "time_taken": round(time.time() - start, 2),
        "token_usage": usage_total,
        "artifact_ids": [item.get("id") for item in artifacts if item.get("id")],
        "chart_ids": [item.get("id") for item in artifacts if item.get("artifact_type") == "chart"],
        "selected_table_id": state.get("selected_table_id"),
        "selected_table_name": state.get("selected_table_name"),
        "transform_revision": state.get("transform_revision") or 0,
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
    model_config = _model_config_for_state(state)
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
- selected_table_id: {state.get("selected_table_id") or "none"}
- selected_table_name: {state.get("selected_table_name") or "none"}
- transform_revision: {state.get("transform_revision") or 0}

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

    model_config = _model_config_for_state(state)
    if model_config is None or not getattr(model_config, "model", None):
        return (
            "Model access is not configured. Set your provider, model name, and API key in Model Access, then try again."
        )

    llm_response = complete_text(prompt, system_prompt=system_prompt, model_config=model_config)
    if llm_response:
        return llm_response

    if not tables:
        return "I don't see any tables in this folder yet. Upload a CSV or spreadsheet in Prepare, then ask me again."

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


def _model_config_for_state(state: AgentState):
    user_id = str(state.get("user_id") or "")
    return load_effective_model_config(lambda: load_user_model_config(user_id))


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
