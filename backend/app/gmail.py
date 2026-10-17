"""Gmail: OAuth web flow, building the MIME message, and sending it.

Send errors are split by what we know about the email afterwards:
- GmailRejected: Gmail answered with an error, so the email was NOT sent.
- GmailUnknown: no clear answer (timeout, dropped connection, 5xx), so it MAY
  have been sent. Never retried automatically.
- GmailAuthError: the stored token no longer works; reconnect Gmail.
"""

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt

from app.config import get_config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
# gmail.send to send; openid + email only to learn which address was connected.
SCOPES = "https://www.googleapis.com/auth/gmail.send openid email"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class GmailError(Exception):
    pass


class GmailAuthError(GmailError):
    """Token revoked/expired or OAuth misconfigured. Nothing was sent."""


class GmailRejected(GmailError):
    """Gmail returned an error response. The email was not sent."""


class GmailUnknown(GmailError):
    """No definite answer from Gmail. The email may or may not have been sent."""


@dataclass
class SentMessage:
    message_id: str
    thread_id: str


class GmailClient(Protocol):
    def access_token(self, refresh_token: str) -> str: ...
    def send(self, access_token: str, raw_message: bytes) -> SentMessage: ...


def oauth_configured() -> bool:
    config = get_config()
    return bool(config.google_client_id and config.google_client_secret)


def authorization_url(state: str) -> str:
    config = get_config()
    return AUTH_URL + "?" + urlencode({
        "client_id": config.google_client_id,
        "redirect_uri": config.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # we need a refresh token
        "prompt": "consent",  # ...and Google only returns one on consent
        "include_granted_scopes": "true",
        "state": state,
    })


def exchange_code(code: str) -> tuple[str, str]:
    """OAuth callback code -> (refresh_token, gmail_address)."""
    config = get_config()
    try:
        res = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
            "code": code,
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "redirect_uri": config.google_redirect_uri,
            "grant_type": "authorization_code",
        })
    except httpx.HTTPError as exc:
        raise GmailAuthError(f"Couldn't reach Google: {exc}") from exc
    body = res.json() if res.content else {}
    if res.status_code != 200:
        raise GmailAuthError(body.get("error_description") or body.get("error") or res.text)
    if "gmail.send" not in body.get("scope", ""):
        raise GmailAuthError("Permission to send email wasn't granted. Tick the Gmail box when connecting.")
    if not body.get("refresh_token"):
        raise GmailAuthError("Google didn't return a refresh token. Remove the app's access in your Google account and connect again.")
    # The ID token came straight from Google's token endpoint over TLS, so its
    # signature doesn't need checking here (OpenID Connect Core 3.1.3.7).
    claims = jwt.decode(body["id_token"], options={"verify_signature": False})
    email = str(claims.get("email", "")).lower()
    if not email or not claims.get("email_verified", False):
        raise GmailAuthError("Couldn't confirm which Gmail address was connected")
    return body["refresh_token"], email


def build_message(
    *,
    sender_name: str,
    sender_address: str,
    to: str,
    subject: str,
    body: str,
    attachment_name: str,
    attachment: bytes,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender_address)) if sender_name else sender_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(attachment, maintype="application", subtype="pdf", filename=attachment_name)
    return msg.as_bytes()


class HttpGmailClient:
    """The real thing: Google's OAuth token endpoint + Gmail REST API."""

    def access_token(self, refresh_token: str) -> str:
        config = get_config()
        try:
            res = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
        except httpx.HTTPError as exc:
            # Nothing has been sent yet; the run just stops and tries next time.
            raise GmailError(f"Couldn't reach Google: {exc}") from exc
        if res.status_code in (400, 401):
            raise GmailAuthError(res.json().get("error", res.text) if res.content else res.text)
        if res.status_code != 200:
            raise GmailError(f"Google token endpoint returned {res.status_code}")
        return res.json()["access_token"]

    def send(self, access_token: str, raw_message: bytes) -> SentMessage:
        payload = {"raw": base64.urlsafe_b64encode(raw_message).decode()}
        try:
            res = httpx.post(SEND_URL, json=payload, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {access_token}"})
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # The request never reached Gmail.
            raise GmailRejected(f"Couldn't connect to Gmail: {exc}") from exc
        except httpx.HTTPError as exc:
            raise GmailUnknown(f"No answer from Gmail ({type(exc).__name__}): {exc}") from exc
        if res.status_code == 200:
            data = res.json()
            return SentMessage(message_id=data["id"], thread_id=data["threadId"])
        detail = _error_message(res)
        if res.status_code == 401:
            raise GmailAuthError(detail)
        if res.status_code >= 500:
            raise GmailUnknown(f"Gmail returned {res.status_code}: {detail}")
        raise GmailRejected(f"Gmail returned {res.status_code}: {detail}")


def _error_message(res: httpx.Response) -> str:
    try:
        return res.json()["error"]["message"]
    except Exception:
        return res.text[:300]


def get_gmail() -> GmailClient:
    """FastAPI dependency / worker default; tests swap in a fake."""
    return HttpGmailClient()
