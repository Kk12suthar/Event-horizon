"""Per-user LLM configuration with development-only environment fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ModelConfigUpdate(BaseModel):
    provider: str = "openrouter"
    model: str = "openai/gpt-4o"
    api_key: str | None = None
    base_url: str | None = None
    site_url: str | None = None
    app_name: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


@dataclass(frozen=True)
class EffectiveModelConfig:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    site_url: str | None = None
    app_name: str | None = None
    temperature: float | None = None


def environment_model_fallback_allowed() -> bool:
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    default_mode = "environment" if environment != "production" else "user"
    mode = os.getenv("MODEL_CONFIG_MODE", default_mode).strip().lower()
    return environment != "production" and mode == "environment"


def apply_model_config_update(
    payload: ModelConfigUpdate,
    save_config: Callable[[dict[str, Any]], Any],
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = normalize_model_provider(payload.provider)
    model = (payload.model or "").strip()
    if not model:
        raise ValueError("Model is required.")

    resolved_model = resolve_model_name(model, provider)
    effective_provider = provider_from_model(resolved_model, provider)
    provided_key = (payload.api_key or "").strip() or None
    existing_provider = normalize_model_provider((existing_config or {}).get("provider"))
    existing_key = (existing_config or {}).get("api_key")
    if provided_key:
        api_key = provided_key
    elif existing_key and existing_provider == effective_provider:
        api_key = existing_key
    else:
        raise ValueError(
            "An API key is required for this provider. Deployment environment keys are never shared with users."
        )

    stored = {
        "provider": effective_provider,
        "model": resolved_model,
        "api_key": api_key,
        "base_url": (payload.base_url or "").strip() or None,
        "site_url": (payload.site_url or "").strip() or None,
        "app_name": (payload.app_name or "").strip() or None,
        "temperature": payload.temperature,
    }
    save_config(stored)
    return config_status_from_effective(effective_config_from_mapping(stored), prefer_secret=api_key)


def load_effective_model_config(
    load_config: Callable[[], dict[str, Any] | None] | None = None,
) -> EffectiveModelConfig | None:
    config = load_config() if load_config else None
    if config:
        return effective_config_from_mapping(config)
    if not environment_model_fallback_allowed():
        return None

    provider = normalize_model_provider(os.getenv("AGENT_PROVIDER") or os.getenv("MODEL_PROVIDER") or "openrouter")
    model = os.getenv("AGENT_MODEL") or os.getenv("MODEL_NAME") or ""
    if not model:
        return None
    resolved_model = resolve_model_name(model, provider)
    provider = provider_from_model(resolved_model, provider)
    return EffectiveModelConfig(
        provider=provider,
        model=resolved_model,
        api_key=_env_api_key(provider),
        base_url=os.getenv("OPENROUTER_API_BASE") if provider == "openrouter" else os.getenv("AGENT_API_BASE"),
        site_url=os.getenv("OR_SITE_URL"),
        app_name=os.getenv("OR_APP_NAME") or "EventHorizon",
        temperature=float(os.getenv("AGENT_TEMPERATURE", "0.2")),
    )


def effective_config_from_mapping(config: dict[str, Any]) -> EffectiveModelConfig:
    provider = normalize_model_provider(config.get("provider") or "openrouter")
    model = str(config.get("model") or "").strip()
    resolved = resolve_model_name(model, provider)
    provider = provider_from_model(resolved, provider)
    temperature = config.get("temperature")
    return EffectiveModelConfig(
        provider=provider,
        model=resolved,
        api_key=config.get("api_key") or None,
        base_url=config.get("base_url") or None,
        site_url=config.get("site_url") or None,
        app_name=config.get("app_name") or "EventHorizon",
        temperature=float(temperature) if temperature is not None else 0.2,
    )


def config_status_from_effective(
    config: EffectiveModelConfig | None,
    prefer_secret: str | None = None,
) -> dict[str, Any]:
    if config is None and environment_model_fallback_allowed():
        config = load_effective_model_config()
        if config is not None:
            status = _status(config, bool(config.api_key), "environment")
            status["managed_by_environment"] = True
            return status
    if config is None:
        return {
            "provider": "",
            "model": "",
            "resolved_model": "",
            "key_env": None,
            "key_configured": False,
            "base_url": "",
            "site_url": "",
            "app_name": "EventHorizon",
            "temperature": 0.2,
            "configuration_scope": "user",
            "managed_by_environment": False,
        }
    return _status(config, bool(prefer_secret or config.api_key), "user")


def _status(config: EffectiveModelConfig, key_configured: bool, scope: str) -> dict[str, Any]:
    return {
        "provider": config.provider,
        "model": config.model,
        "resolved_model": config.model,
        "key_env": model_provider_key(config.provider),
        "key_configured": key_configured,
        "base_url": config.base_url or (OPENROUTER_BASE_URL if config.provider == "openrouter" else ""),
        "site_url": config.site_url or "",
        "app_name": config.app_name or "EventHorizon",
        "temperature": config.temperature if config.temperature is not None else 0.2,
        "configuration_scope": scope,
        "managed_by_environment": scope == "environment",
    }


def resolve_model_name(model: str, provider: str | None = None) -> str:
    normalized = str(model or "").strip()
    provider_key = normalize_model_provider(provider)
    if not normalized or normalized.startswith(("openrouter/", "vertex_ai/", "gemini/")):
        return normalized
    if provider_key == "openrouter":
        return f"openrouter/{normalized.lstrip('/')}"
    if provider_key in {"vertex", "vertex_ai"}:
        return f"vertex_ai/{normalized.lstrip('/')}"
    if provider_key == "google":
        base = normalized.split("/", 1)[1] if "/" in normalized else normalized
        return f"gemini/{base.lstrip('/')}"
    return normalized


def provider_from_model(model: str, fallback: str) -> str:
    lowered = model.lower()
    if lowered.startswith("openrouter/"):
        return "openrouter"
    if lowered.startswith(("vertex_ai/", "vertex/")):
        return "vertex"
    if lowered.startswith(("anthropic/", "claude")):
        return "anthropic"
    if lowered.startswith(("google/", "gemini")):
        return "google"
    if lowered.startswith(("openai/", "gpt-", "o1", "o3")):
        return "openai"
    return normalize_model_provider(fallback)


def normalize_model_provider(provider: str | None) -> str:
    value = str(provider or "openrouter").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "open_router": "openrouter",
        "openai_compatible": "openai",
        "gemini": "google",
        "google_gemini": "google",
        "vertex_ai": "vertex",
        "vertexai": "vertex",
        "google_vertex": "vertex",
        "google_vertex_ai": "vertex",
    }
    return aliases.get(value, value or "openrouter")


def model_provider_key(provider: str) -> str | None:
    return {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "vertex": "VERTEX_API_KEY",
    }.get(normalize_model_provider(provider))


def _env_api_key(provider: str) -> str | None:
    key = model_provider_key(provider)
    if provider == "google":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key and os.getenv(key):
        return os.getenv(key)
    if provider == "vertex":
        return os.getenv("VERTEX_API_KEY") or os.getenv("VERTEXAI_API_KEY")
    return None
