from __future__ import annotations

import logging
import os
from typing import Optional

from runtime.model_config import EffectiveModelConfig

logger = logging.getLogger("eventhorizon.agent_server.llm")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def complete_text(prompt: str, system_prompt: Optional[str] = None, model_config: Optional[EffectiveModelConfig] = None) -> str:
    """Best-effort LLM call with deterministic fallback.

    Runtime model configuration is passed per request. The function does not
    mutate process-wide provider key environment variables.
    """
    if model_config is not None:
        resolved_model = model_config.model
        provider = model_config.provider
        temperature = model_config.temperature if model_config.temperature is not None else 0.2
        api_key = model_config.api_key
        base_url = model_config.base_url
    else:
        model = os.getenv("AGENT_MODEL") or os.getenv("MODEL_NAME")
        if not model:
            logger.info("No AGENT_MODEL/MODEL_NAME configured; using deterministic agent fallback.")
            return ""
        provider = os.getenv("AGENT_PROVIDER") or os.getenv("MODEL_PROVIDER")
        resolved_model = resolve_model_name(model, provider)
        temperature = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
        api_key = _api_key_for_model(resolved_model)
        base_url = os.getenv("OPENROUTER_API_BASE") if resolved_model.startswith("openrouter/") else os.getenv("AGENT_API_BASE")

    if _provider_requires_key(resolved_model) and not api_key:
        missing_key = _provider_key_env(_provider_for_model(resolved_model), resolved_model)
        logger.warning("LLM completion skipped for model %s because %s is not configured.", resolved_model, missing_key or "provider key")
        return ""

    try:
        import litellm

        kwargs = {
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "You are EventHorizon, a concise and reliable data workspace assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "4096")),
            "timeout": int(os.getenv("AGENT_LLM_TIMEOUT", "90")),
        }
        if api_key:
            kwargs["api_key"] = api_key
        if resolved_model.startswith("openrouter/"):
            kwargs["base_url"] = base_url or OPENROUTER_BASE_URL
            extra_headers = _openrouter_headers(model_config)
            if extra_headers:
                kwargs["extra_headers"] = extra_headers
        elif resolved_model.startswith("vertex_ai/"):
            if api_key:
                kwargs["api_key"] = api_key
            else:
                project = os.getenv("VERTEXAI_PROJECT") or os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
                if project:
                    kwargs["vertex_project"] = project
                kwargs["vertex_location"] = os.getenv("VERTEXAI_LOCATION") or os.getenv("VERTEX_LOCATION") or "global"

        response = litellm.completion(**kwargs)
        return response["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        logger.warning("LLM completion failed for model %s: %s", resolved_model, _safe_error(exc))
        return ""


def _provider_call_kwargs(model_config: Optional[EffectiveModelConfig]) -> dict:
    """Resolve the provider-specific LiteLLM kwargs (model, key, base_url, vertex...).

    Centralizes the same provider/key/base-url resolution used by
    :func:`complete_text` so tool-calling requests stay consistent with plain
    completions. Returns an empty dict when no usable model is configured.
    """
    if model_config is not None and model_config.model:
        resolved_model = model_config.model
        temperature = model_config.temperature if model_config.temperature is not None else 0.2
        api_key = model_config.api_key
        base_url = model_config.base_url
    else:
        model = os.getenv("AGENT_MODEL") or os.getenv("MODEL_NAME")
        if not model:
            return {}
        provider = os.getenv("AGENT_PROVIDER") or os.getenv("MODEL_PROVIDER")
        resolved_model = resolve_model_name(model, provider)
        temperature = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
        api_key = _api_key_for_model(resolved_model)
        base_url = os.getenv("OPENROUTER_API_BASE") if resolved_model.startswith("openrouter/") else os.getenv("AGENT_API_BASE")

    if _provider_requires_key(resolved_model) and not api_key:
        return {}

    kwargs: dict = {
        "model": resolved_model,
        "temperature": temperature,
        "max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "4096")),
        "timeout": int(os.getenv("AGENT_LLM_TIMEOUT", "90")),
    }
    if api_key:
        kwargs["api_key"] = api_key
    if resolved_model.startswith("openrouter/"):
        kwargs["base_url"] = base_url or OPENROUTER_BASE_URL
        extra_headers = _openrouter_headers(model_config)
        if extra_headers:
            kwargs["extra_headers"] = extra_headers
    elif resolved_model.startswith("vertex_ai/"):
        if not api_key:
            project = os.getenv("VERTEXAI_PROJECT") or os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if project:
                kwargs["vertex_project"] = project
            kwargs["vertex_location"] = os.getenv("VERTEXAI_LOCATION") or os.getenv("VERTEX_LOCATION") or "global"
    return kwargs


async def acomplete_with_tools(
    messages: list[dict],
    tools: list[dict],
    model_config: Optional[EffectiveModelConfig] = None,
) -> Optional[dict]:
    """Async chat completion that may request tool calls.

    Returns the assistant message as a normalized dict with ``content`` and an
    optional ``tool_calls`` list (each ``{id, name, arguments}``), or ``None`` if
    no model is configured or the call fails. Caller decides whether to execute
    the tool calls and loop again.
    """
    base = _provider_call_kwargs(model_config)
    if not base:
        return None
    try:
        import litellm

        kwargs = dict(base)
        kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = await litellm.acompletion(**kwargs)
        message = response["choices"][0]["message"]
        # Full-fidelity dump of the assistant turn so callers can replay it
        # verbatim. This preserves provider-specific fields (e.g. Gemini's
        # `thought_signature`) that are REQUIRED when sending a prior
        # function-call turn back in a multi-step tool loop.
        try:
            raw = message.model_dump()
        except Exception:
            raw = None
        content = getattr(message, "content", None)
        if isinstance(message, dict):
            content = message.get("content")
            raw_calls = message.get("tool_calls") or []
        else:
            raw_calls = getattr(message, "tool_calls", None) or []

        tool_calls = []
        for call in raw_calls:
            fn = call["function"] if isinstance(call, dict) else call.function
            call_id = call["id"] if isinstance(call, dict) else getattr(call, "id", None)
            name = fn["name"] if isinstance(fn, dict) else fn.name
            arguments = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            tool_calls.append({"id": call_id, "name": name, "arguments": arguments or "{}"})

        return {"content": content or "", "tool_calls": tool_calls, "raw": raw}
    except Exception as exc:
        logger.warning("Tool-calling completion failed: %s", _safe_error(exc))
        return None



# ---------------------------------------------------------------------------
# Streaming completions with token-usage accounting
# ---------------------------------------------------------------------------
EMPTY_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def merge_usage(a: dict | None, b: dict | None) -> dict:
    """Sum two usage dicts field-by-field (used to total usage across a query)."""
    a = a or {}
    b = b or {}
    return {k: int(a.get(k, 0) or 0) + int(b.get(k, 0) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _extract_usage(obj: object) -> dict:
    usage = getattr(obj, "usage", None)
    if usage is None and isinstance(obj, dict):
        usage = obj.get("usage")
    if not usage:
        return {}

    def field(key: str) -> int:
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    prompt = field("prompt_tokens")
    completion = field("completion_tokens")
    total = field("total_tokens") or (prompt + completion)
    if not (prompt or completion or total):
        return {}
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def _count_tokens(model: str, *, messages: list[dict] | None = None, text: str | None = None) -> int:
    try:
        import litellm

        if messages is not None:
            return int(litellm.token_counter(model=model, messages=messages))
        return int(litellm.token_counter(model=model, text=text or ""))
    except Exception:
        content = text if text is not None else "".join(str(m.get("content", "")) for m in (messages or []))
        return max(1, len(content) // 4)


def _usage_from_chunks(chunks: list, model_config: Optional[EffectiveModelConfig], messages: list[dict], full_text: str) -> dict:
    """Resolve token usage from a streamed response, with robust fallbacks.

    Order: (1) an ``include_usage`` final chunk, (2) litellm's
    ``stream_chunk_builder`` reconstruction, (3) a local ``token_counter``
    estimate - so usage is always reported even when a provider omits it.
    """
    model = (model_config.model if model_config else "") or ""
    for chunk in reversed(chunks):
        usage = _extract_usage(chunk)
        if usage.get("total_tokens"):
            return usage
    try:
        import litellm

        rebuilt = litellm.stream_chunk_builder(chunks, messages=messages)
        usage = _extract_usage(rebuilt)
        if usage.get("prompt_tokens") or usage.get("total_tokens"):
            return usage
    except Exception:
        pass
    prompt = _count_tokens(model, messages=messages)
    completion = _count_tokens(model, text=full_text)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


async def _open_stream(kwargs: dict):
    """Open a LiteLLM streaming response, retrying without stream_options if a
    provider rejects it."""
    import litellm

    try:
        return await litellm.acompletion(**kwargs)
    except Exception:
        if "stream_options" in kwargs:
            kwargs.pop("stream_options", None)
            return await litellm.acompletion(**kwargs)
        raise


async def astream_text(
    messages: list[dict],
    model_config: Optional[EffectiveModelConfig] = None,
    *,
    on_delta: Optional[callable] = None,
    on_reasoning: Optional[callable] = None,
) -> tuple[str, dict]:
    """Stream a plain completion, invoking callbacks per token.

    ``on_delta(text)`` receives visible answer tokens; ``on_reasoning(text)``
    receives reasoning/thinking tokens when the provider emits them. Returns
    ``(full_text, usage)``; ``("", {})`` when no model is configured or on error.
    """
    base = _provider_call_kwargs(model_config)
    if not base:
        return "", {}
    try:
        kwargs = dict(base)
        kwargs["messages"] = messages
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
        stream = await _open_stream(kwargs)

        chunks: list = []
        parts: list[str] = []
        async for chunk in stream:
            chunks.append(chunk)
            try:
                delta = chunk.choices[0].delta
            except Exception:
                continue
            if delta is None:
                continue
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and on_reasoning:
                on_reasoning(reasoning)
            content = getattr(delta, "content", None)
            if content:
                parts.append(content)
                if on_delta:
                    on_delta(content)
        full = "".join(parts)
        return full, _usage_from_chunks(chunks, model_config, messages, full)
    except Exception as exc:
        logger.warning("Streaming completion failed: %s", _safe_error(exc))
        return "", {}


async def astream_with_tools(
    messages: list[dict],
    tools: list[dict],
    model_config: Optional[EffectiveModelConfig] = None,
    *,
    on_reasoning: Optional[callable] = None,
) -> tuple[Optional[dict], dict]:
    """Streaming tool-calling turn. Streams reasoning tokens via ``on_reasoning``
    while accumulating any tool calls.

    Returns ``(message, usage)`` where ``message`` is a normalized
    ``{content, tool_calls}`` dict (or ``None`` on failure) and ``usage`` totals
    the tokens for this turn.
    """
    base = _provider_call_kwargs(model_config)
    if not base:
        return None, {}
    try:
        import litellm

        kwargs = dict(base)
        kwargs["messages"] = messages
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        stream = await _open_stream(kwargs)

        chunks: list = []
        async for chunk in stream:
            chunks.append(chunk)
            try:
                delta = chunk.choices[0].delta
            except Exception:
                continue
            reasoning = getattr(delta, "reasoning_content", None) if delta else None
            if reasoning and on_reasoning:
                on_reasoning(reasoning)

        try:
            rebuilt = litellm.stream_chunk_builder(chunks, messages=messages)
            message = rebuilt["choices"][0]["message"]
        except Exception:
            message = None

        usage = _usage_from_chunks(chunks, model_config, messages, "")
        if message is None:
            return None, usage

        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        raw_calls = (message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)) or []
        tool_calls = []
        for call in raw_calls:
            fn = call["function"] if isinstance(call, dict) else call.function
            call_id = call["id"] if isinstance(call, dict) else getattr(call, "id", None)
            name = fn["name"] if isinstance(fn, dict) else fn.name
            arguments = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            tool_calls.append({"id": call_id, "name": name, "arguments": arguments or "{}"})
        return {"content": content or "", "tool_calls": tool_calls}, usage
    except Exception as exc:
        logger.warning("Streaming tool completion failed: %s", _safe_error(exc))
        return None, {}



def resolve_model_name(model: str, provider: Optional[str] = None) -> str:
    """Normalize UI/env model values into the LiteLLM model name we execute."""
    normalized = str(model or "").strip()
    provider_key = _normalize_provider_name(provider)
    if not normalized:
        return normalized
    if normalized.startswith("openrouter/"):
        return normalized
    if normalized.startswith("vertex_ai/"):
        return normalized
    if normalized.startswith("gemini/"):
        return normalized
    if provider_key == "openrouter":
        return f"openrouter/{normalized.lstrip('/')}"
    if provider_key in ("vertex", "vertex_ai"):
        return f"vertex_ai/{normalized.lstrip('/')}"
    if provider_key == "google":
        base = normalized.split("/", 1)[1] if "/" in normalized else normalized
        return f"gemini/{base.lstrip('/')}"
    return normalized


def _normalize_provider_env() -> None:
    """Deprecated no-op kept for import compatibility; runtime calls must not mutate os.environ."""
    return None


def _missing_provider_key(model: str) -> str | None:
    key_name = _provider_key_env(_provider_for_model(model), model)
    if key_name and not os.getenv(key_name):
        return key_name
    return None


def _provider_for_model(model: str) -> str:
    lowered = model.lower()
    if lowered.startswith("openrouter/"):
        return "openrouter"
    if lowered.startswith("vertex_ai/") or lowered.startswith("vertex/"):
        return "vertex"
    if lowered.startswith("anthropic/") or lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith("google/") or lowered.startswith("gemini"):
        return "google"
    if lowered.startswith("openai/") or lowered.startswith("gpt-") or lowered.startswith("o1") or lowered.startswith("o3"):
        return "openai"
    return _normalize_provider_name(os.getenv("AGENT_PROVIDER") or os.getenv("MODEL_PROVIDER"))


def _provider_key_env(provider: str, model: str = "") -> str | None:
    provider_key = _normalize_provider_name(provider) or _provider_for_model(model)
    return {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
    }.get(provider_key)


def _normalize_provider_name(provider: Optional[str]) -> str:
    value = str(provider or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "open_router": "openrouter",
        "openai_compatible": "openai",
        "gemini": "google",
        "google_gemini": "google",
        "vertex": "vertex",
        "vertex_ai": "vertex",
        "vertexai": "vertex",
        "google_vertex": "vertex",
        "google_vertex_ai": "vertex",
    }
    return aliases.get(value, value)


def _openrouter_headers(model_config: Optional[EffectiveModelConfig] = None) -> dict[str, str]:
    """Optional OpenRouter attribution headers for rankings and dashboard traces."""
    headers: dict[str, str] = {}
    site_url = ((model_config.site_url if model_config else None) or os.getenv("OR_SITE_URL") or "").strip()
    app_name = ((model_config.app_name if model_config else None) or os.getenv("OR_APP_NAME") or "EventHorizon").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers


def _api_key_for_model(model: str) -> str | None:
    provider = _provider_for_model(model)
    if provider == "vertex":
        return os.getenv("VERTEX_API_KEY") or os.getenv("VERTEXAI_API_KEY") or os.getenv("AGENT_API_KEY") or os.getenv("MODEL_API_KEY")
    key_name = _provider_key_env(provider, model)
    if provider == "google":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("AGENT_API_KEY") or os.getenv("MODEL_API_KEY")
    if key_name and os.getenv(key_name):
        return os.getenv(key_name)
    return os.getenv("AGENT_API_KEY") or os.getenv("MODEL_API_KEY")


def _provider_requires_key(model: str) -> bool:
    return _provider_for_model(model) != "vertex" or bool(os.getenv("VERTEX_API_KEY") or os.getenv("VERTEXAI_API_KEY"))
def _safe_error(exc: Exception) -> str:
    message = str(exc)
    for key_name in (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "AGENT_API_KEY",
        "MODEL_API_KEY",
    ):
        key = os.getenv(key_name)
        if key:
            message = message.replace(key, f"<{key_name}>")
    return message[:500]
