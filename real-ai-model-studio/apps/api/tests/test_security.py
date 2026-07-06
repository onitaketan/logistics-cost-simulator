"""Phase 5 — security tests (CLAUDE.md Phase 5 セキュリティテスト).

Covers authentication trust boundaries that the compliance/RBAC layers assume:
  * missing / malformed / wrong-secret / expired tokens are all rejected (401);
  * a token stays only as trustworthy as the live user — suspending the user
    revokes access immediately, before token expiry (SEC-F6);
  * the app refuses to start outside `local` with the default signing secret
    (SEC-F2), a pure-unit guard that needs no DB.

DB-backed cases skip without a database; the config guard always runs.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy import text

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.security import _ALGO  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ChangeMe123!"
PROTECTED = "/api/v1/models"  # requires a valid, active user


# ---- Pure unit: production secret guard (no DB) ----

def test_default_secret_rejected_outside_local():
    s = Settings(app_env="production", api_secret_key="change-me")
    with pytest.raises(RuntimeError):
        s.enforce_production_secrets()


def test_nondefault_secret_allowed():
    s = Settings(app_env="production", api_secret_key="a-real-long-random-secret")
    s.enforce_production_secrets()  # must not raise


def test_local_allows_default_secret():
    s = Settings(app_env="local", api_secret_key="change-me")
    s.enforce_production_secrets()  # local dev convenience — must not raise


# ---- DB-backed auth boundary tests ----

def _db_available() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


db_only = pytest.mark.skipif(not _db_available(), reason="no database available")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_auth(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@db_only
def test_missing_token_rejected(client):
    assert client.get(PROTECTED).status_code == 401


@db_only
def test_garbage_token_rejected(client):
    r = client.get(PROTECTED, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


@db_only
def test_token_signed_with_wrong_secret_rejected(client):
    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "role": "admin",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "attacker-guessed-secret", algorithm=_ALGO,
    )
    r = client.get(PROTECTED, headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


@db_only
def test_expired_token_rejected(client):
    secret = get_settings().api_secret_key
    expired = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "role": "admin",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        secret, algorithm=_ALGO,
    )
    r = client.get(PROTECTED, headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


@db_only
def test_valid_token_for_unknown_user_rejected(client):
    """A correctly-signed token whose subject is not a real user is rejected
    (get_current_user loads the user, not just trusts the claim)."""
    secret = get_settings().api_secret_key
    tok = jwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "role": "admin",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        secret, algorithm=_ALGO,
    )
    r = client.get(PROTECTED, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


@db_only
def test_suspended_user_token_revoked_immediately(client, admin_auth):
    import uuid
    tag = uuid.uuid4().hex[:8]
    email = f"sec{tag}@example.com"
    pw = "SecPass123"
    u = client.post("/api/v1/users", headers=admin_auth, json={
        "name": f"sec{tag}", "email": email, "password": pw, "role": "creative",
    }).json()["data"]
    tok = client.post("/api/v1/auth/login",
                      json={"email": email, "password": pw}).json()["data"]["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}

    # Token works while active.
    assert client.get(PROTECTED, headers=auth).status_code == 200

    # Admin suspends the user; the SAME (unexpired) token must now be rejected.
    client.patch(f"/api/v1/users/{u['id']}", headers=admin_auth,
                 json={"status": "suspended"})
    assert client.get(PROTECTED, headers=auth).status_code == 401
