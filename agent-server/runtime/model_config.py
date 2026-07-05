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


def apply_model_config_update(
    payload: ModelConfigUpdate,
    save_config: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    provider = normalize_model_provider(payload.provider)
    model = (payload.model or "").strip()
    if not model:
        raise ValueError("Model is required.")

    resolved_model = resolve_model_name(model, provider)
    effective_provider = provider_from_model(resolved_model, provider)
    stored = {
        "provider": effective_provider,
        "model": resolved_model,
        "api_key": (payload.api_key or "").strip() or None,
        "base_url": (payload.base_url or "").strip() or None,
        "site_url": (payload.site_url or "").strip() or None,
        "app_name": (payload.app_name or "").strip() or None,
        "temperature": payload.temperature,
    }
    save_config(stored)
    return config_status_from_effective(effective_config_from_mapping(stored), prefer_secret=stored.get("api_key"))


def load_effective_model_config(load_config: Callable[[], dict[str, Any] | None] | None = None) -> EffectiveModelConfig | None:
    config = load_config() if load_config else None
    if config:
        return effective_config_from_mapping(config)

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
        api_key=config.get("api_key") or _env_api_key(provider),
        base_url=config.get("base_url") or None,
        site_url=config.get("site_url") or None,
        app_name=config.get("app_name") or "EventHorizon",
        temperature=float(temperature) if temperature is not None else 0.2,
    )


def config_status_from_effective(config: EffectiveModelConfig | None, prefer_secret: str | None = None) -> dict[str, Any]:
    if config is None:
        provider = normalize_model_provider(os.getenv("AGENT_PROVIDER") or os.getenv("MODEL_PROVIDER") or "openrouter")
        model = os.getenv("AGENT_MODEL") or os.getenv("MODEL_NAME") or ""
        resolved = resolve_model_name(model, provider) if model else ""
        provider = provider_from_model(resolved, provider) if resolved else provider
        key_env = model_provider_key(provider)
        return {
            "provider": provider,
            "model": model,
            "resolved_model": resolved,
            "key_env": key_env,
            "key_configured": bool(key_env and os.getenv(key_env)),
            "base_url": os.getenv("OPENROUTER_API_BASE") if provider == "openrouter" else os.getenv("AGENT_API_BASE", ""),
            "site_url": os.getenv("OR_SITE_URL", ""),
            "app_name": os.getenv("OR_APP_NAME", "EventHorizon"),
            "temperature": float(os.getenv("AGENT_TEMPERATURE", "0.2")),
        }

    key_env = model_provider_key(config.provider)
    key_configured = bool(prefer_secret or config.api_key or (key_env and os.getenv(key_env)))
    if config.provider == "vertex" and not key_configured:
        key_env = "ADC (gcloud application-default credentials)"
        key_configured = bool(os.getenv("VERTEXAI_PROJECT") or os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"))
    return {
        "provider": config.provider,
        "model": config.model,
        "resolved_model": config.model,
        "key_env": key_env,
        "key_configured": key_configured,
        "base_url": config.base_url or (OPENROUTER_BASE_URL if config.provider == "openrouter" else ""),
        "site_url": config.site_url or "",
        "app_name": config.app_name or "EventHorizon",
        "temperature": config.temperature if config.temperature is not None else 0.2,
    }


def resolve_model_name(model: str, provider: str | None = None) -> str:
    normalized = str(model or "").strip()
    provider_key = normalize_model_provider(provider)
    if not normalized:
        return normalized
    if normalized.startswith(("openrouter/", "vertex_ai/", "gemini/")):
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

