from __future__ import annotations

import base64
import hashlib
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

CONFIG_ID = "workspace"


def load_workspace_model_config() -> dict[str, Any] | None:
    try:
        with _connect() as conn:
            _ensure_table(conn)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT provider, model, encrypted_api_key, base_url, site_url, app_name, temperature
                    FROM instance01.agent_model_config
                    WHERE id = %s
                    """,
                    (CONFIG_ID,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "provider": row["provider"],
            "model": row["model"],
            "api_key": _decrypt_secret(row.get("encrypted_api_key")) if row.get("encrypted_api_key") else None,
            "base_url": row.get("base_url"),
            "site_url": row.get("site_url"),
            "app_name": row.get("app_name"),
            "temperature": float(row["temperature"]) if row.get("temperature") is not None else None,
        }
    except Exception:
        return None


def save_workspace_model_config(config: dict[str, Any], updated_by: str | None = None) -> None:
    with _connect() as conn:
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO instance01.agent_model_config(
                    id, provider, model, encrypted_api_key, base_url, site_url, app_name, temperature, updated_by, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    encrypted_api_key = CASE
                        WHEN EXCLUDED.encrypted_api_key IS NOT NULL THEN EXCLUDED.encrypted_api_key
                        WHEN instance01.agent_model_config.provider IS DISTINCT FROM EXCLUDED.provider THEN NULL
                        ELSE instance01.agent_model_config.encrypted_api_key
                    END,
                    base_url = EXCLUDED.base_url,
                    site_url = EXCLUDED.site_url,
                    app_name = EXCLUDED.app_name,
                    temperature = EXCLUDED.temperature,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """,
                (
                    CONFIG_ID,
                    config["provider"],
                    config["model"],
                    _encrypt_secret(config.get("api_key")) if config.get("api_key") else None,
                    config.get("base_url"),
                    config.get("site_url"),
                    config.get("app_name"),
                    config.get("temperature"),
                    updated_by,
                ),
            )
        conn.commit()


def _ensure_table(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instance01.agent_model_config (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                encrypted_api_key TEXT,
                base_url TEXT,
                site_url TEXT,
                app_name TEXT,
                temperature NUMERIC,
                updated_by TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def _encrypt_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).encrypt(secret.encode("utf-8")).decode("utf-8")


def _decrypt_secret(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).decrypt(encrypted.encode("utf-8")).decode("utf-8")


def _fernet_key() -> bytes:
    seed = os.getenv("API_KEY_ENCRYPTION_KEY")
    if not seed:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY is required for persisted API keys.")
    return base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())


@contextmanager
def _connect() -> Iterator[Any]:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DBNAME") or os.getenv("POSTGRES_UPLOAD_DBNAME"),
    )
    try:
        yield conn
    finally:
        conn.close()
