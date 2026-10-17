"""Connect Gmail: OAuth web flow. `connect`/`status` need the signed-in user;
`callback` is hit by Google's redirect, so it is checked by its signed `state`."""

import secrets
import time
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crypto, gmail, services
from app.auth import require_user
from app.config import get_config
from app.db import get_db

router = APIRouter(prefix="/gmail", tags=["gmail"])

STATE_TTL_SECONDS = 600


class GmailStatus(BaseModel):
    oauth_configured: bool
    connected: bool
    address: str | None
    needs_reconnect: bool


class ConnectUrl(BaseModel):
    url: str


def _state_key() -> bytes:
    return crypto.derived_secret("gmail-oauth-state")


@router.get("/status", response_model=GmailStatus, dependencies=[Depends(require_user)])
def status(db: Session = Depends(get_db)):
    settings = services.get_settings(db)
    connected = bool(settings.gmail_refresh_token_encrypted)
    return GmailStatus(
        oauth_configured=gmail.oauth_configured(),
        connected=connected,
        address=settings.gmail_address,
        needs_reconnect=not connected and bool(settings.gmail_address),
    )


@router.get("/connect", response_model=ConnectUrl, dependencies=[Depends(require_user)])
def connect():
    """The Google consent URL. The frontend sends the browser there."""
    if not gmail.oauth_configured():
        raise HTTPException(409, "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first")
    try:
        state = jwt.encode(
            {"purpose": "gmail", "nonce": secrets.token_urlsafe(16),
             "exp": int(time.time()) + STATE_TTL_SECONDS},
            _state_key(), algorithm="HS256",
        )
    except crypto.CryptoError as exc:
        raise HTTPException(409, str(exc)) from None
    return ConnectUrl(url=gmail.authorization_url(state))


@router.get("/callback", include_in_schema=False)
def callback(state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    def back(**params: str) -> RedirectResponse:
        return RedirectResponse(f"{get_config().frontend_url}/settings?{urlencode(params)}", 303)

    try:
        claims = jwt.decode(state, _state_key(), algorithms=["HS256"])
        if claims.get("purpose") != "gmail":
            raise jwt.InvalidTokenError("wrong purpose")
    except (jwt.PyJWTError, crypto.CryptoError):
        return back(gmail="error", message="The connect link expired or was invalid. Try again.")
    if error or not code:
        return back(gmail="error", message=f"Google said: {error or 'no code returned'}")

    try:
        refresh_token, address = gmail.exchange_code(code)
        encrypted = crypto.encrypt(refresh_token)
    except (gmail.GmailAuthError, crypto.CryptoError) as exc:
        return back(gmail="error", message=str(exc))

    settings = services.get_settings(db)
    settings.gmail_refresh_token_encrypted = encrypted
    settings.gmail_address = address
    db.commit()
    return back(gmail="connected")
