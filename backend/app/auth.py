"""Supabase JWT verification + single-email allowlist."""

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Config, get_config

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def decode_token(token: str, config: Config) -> dict:
    """Verify a Supabase access token: legacy HS256 secret if configured,
    otherwise the project's published signing keys."""
    options = {"require": ["exp", "sub"]}
    if config.supabase_jwt_secret:
        return jwt.decode(token, config.supabase_jwt_secret, algorithms=["HS256"],
                          audience="authenticated", options=options)
    if config.supabase_url:
        key = _jwks_client(config.supabase_url).get_signing_key_from_jwt(token)
        return jwt.decode(token, key, algorithms=["ES256", "RS256"],
                          audience="authenticated", options=options)
    raise RuntimeError("Set SUPABASE_URL or SUPABASE_JWT_SECRET to verify tokens")


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Return the signed-in email, or reject the request."""
    config = get_config()
    if config.auth_disabled:
        if config.env == "prod":  # also enforced by Config; never trust one check
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth misconfigured")
        return config.allowed_email or "dev@localhost"

    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not signed in", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_token(credentials.credentials, config)
    except (jwt.PyJWTError, jwt.PyJWKClientError):
        raise unauthorized from None

    email = str(claims.get("email", "")).lower()
    if email != config.allowed_email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is not allowed")
    return email
