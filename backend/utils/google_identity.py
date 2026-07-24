"""Google Identity Services token verification helpers."""

from __future__ import annotations

import hmac
from typing import Any, Callable


class GoogleIdentityError(ValueError):
    pass


def verify_google_credential(
    credential: str,
    nonce: str,
    client_id: str,
    verifier: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not credential or not nonce or not client_id:
        raise GoogleIdentityError("Google sign-in is not configured or the request is incomplete.")
    if verifier is None:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        verifier = lambda token, audience: id_token.verify_oauth2_token(token, GoogleRequest(), audience)

    try:
        claims = verifier(credential, client_id)
    except Exception as exc:
        raise GoogleIdentityError("Google could not verify this sign-in.") from exc

    issuer = str(claims.get("iss") or "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleIdentityError("Google token issuer is invalid.")
    token_nonce = str(claims.get("nonce") or "")
    if not token_nonce or not hmac.compare_digest(token_nonce, nonce):
        raise GoogleIdentityError("Google sign-in nonce is invalid.")
    if claims.get("email_verified") is not True:
        raise GoogleIdentityError("Google account email is not verified.")

    email = str(claims.get("email") or "").strip().lower()
    hosted_domain = str(claims.get("hd") or "").strip().lower()
    google_is_authoritative = email.endswith(("@gmail.com", "@googlemail.com")) or bool(hosted_domain)
    if not email or not google_is_authoritative:
        raise GoogleIdentityError(
            "Use a Gmail or Google Workspace account for Google sign-in."
        )
    if not str(claims.get("sub") or "").strip():
        raise GoogleIdentityError("Google account identifier is missing.")
    return claims
