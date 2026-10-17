import time

import jwt
import pytest
from pydantic import ValidationError

from app.config import Config, get_config

SECRET = "test-secret-at-least-32-bytes-long!!"


@pytest.fixture
def auth_on(monkeypatch, client):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_config.cache_clear()
    yield client
    get_config.cache_clear()


def token(email="me@example.com", **overrides):
    claims = {"sub": "user-1", "email": email, "aud": "authenticated",
              "exp": int(time.time()) + 300, **overrides}
    return {"Authorization": f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}


def test_no_token_is_401(auth_on):
    assert auth_on.get("/contacts").status_code == 401
    assert auth_on.post("/parse", json={"text": "a@b.com"}).status_code == 401
    assert auth_on.get("/resume").status_code == 401  # the resume is personal data


def test_bad_or_expired_token_is_401(auth_on):
    assert auth_on.get("/contacts", headers={"Authorization": "Bearer junk"}).status_code == 401
    expired = token(exp=int(time.time()) - 10)
    assert auth_on.get("/contacts", headers=expired).status_code == 401
    wrong_aud = token(aud="anon")
    assert auth_on.get("/contacts", headers=wrong_aud).status_code == 401


def test_other_email_is_403(auth_on):
    assert auth_on.get("/contacts", headers=token("someone@else.com")).status_code == 403


def test_allowlisted_email_gets_in(auth_on):
    assert auth_on.get("/contacts", headers=token("ME@example.com")).status_code == 200


def test_health_is_public(auth_on):
    assert auth_on.get("/health").status_code == 200


def test_auth_bypass_refused_in_prod():
    with pytest.raises(ValidationError, match="not allowed when ENV=prod"):
        Config(env="prod", auth_disabled=True, allowed_email="me@example.com")


def test_allowlist_required_when_auth_on():
    with pytest.raises(ValidationError, match="ALLOWED_EMAIL is required"):
        Config(auth_disabled=False, allowed_email="")


def test_supabase_url_gets_psycopg_driver():
    cfg = Config(auth_disabled=True, database_url="postgresql://u:p@db.supabase.co:5432/postgres")
    assert cfg.database_url.startswith("postgresql+psycopg://")
