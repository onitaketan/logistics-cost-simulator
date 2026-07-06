"""Phase 5 — permission (RBAC) matrix test (docs/07 §4.1, CLAUDE.md Phase 5 権限テスト).

For each role we log in and assert allow (200) / deny (403) across representative
protected endpoints, exercising the matrix in app/core/rbac.py end-to-end through
the real API dependency (`require(Perm.*)`). Default is deny.

Requires a running Postgres (schema + seed applied); skips without.
"""

import uuid

import pytest
from sqlalchemy import text

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ChangeMe123!"
ROLES = ["admin", "legal", "sales", "creative", "approver", "viewer"]


def _db_available() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="no database available")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_auth(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture(scope="module")
def role_auth(client, admin_auth) -> dict:
    """Create one active user per role and return {role: auth-headers}."""
    out = {"admin": admin_auth}
    for role in ROLES:
        if role == "admin":
            continue
        tag = uuid.uuid4().hex[:8]
        email = f"{role}{tag}@example.com"
        pw = "RolePass123"
        r = client.post("/api/v1/users", headers=admin_auth, json={
            "name": f"{role}-{tag}", "email": email, "password": pw, "role": role,
        })
        assert r.status_code == 200, r.text
        tok = client.post("/api/v1/auth/login",
                          json={"email": email, "password": pw}).json()["data"]["access_token"]
        out[role] = {"Authorization": f"Bearer {tok}"}
    return out


# expected allow-sets per capability (everyone not listed is denied)
_MODEL_VIEW = set(ROLES)                      # all roles can view models
_MODEL_EDIT = {"admin", "legal"}             # POST /models -> MODEL_EDIT
_PROJECT_EDIT = {"admin", "sales"}           # POST /projects -> PROJECT_EDIT
_USER_MANAGE = {"admin"}                     # GET /users -> USER_MANAGE
_AUDIT_VIEW = {"admin", "legal"}             # GET /audit-logs -> AUDIT_VIEW


def _assert(cond_ok: bool, resp, role: str, cap: str):
    if cond_ok:
        assert resp.status_code == 200, f"{role} should be ALLOWED {cap}: {resp.status_code} {resp.text}"
    else:
        assert resp.status_code == 403, f"{role} should be DENIED {cap}: {resp.status_code} {resp.text}"


def test_model_view_allowed_for_all_roles(client, role_auth):
    for role in ROLES:
        r = client.get("/api/v1/models", headers=role_auth[role])
        _assert(role in _MODEL_VIEW, r, role, "GET /models")


def test_model_edit_matrix(client, role_auth):
    for role in ROLES:
        tag = uuid.uuid4().hex[:6]
        r = client.post("/api/v1/models", headers=role_auth[role], json={
            "stage_name": f"S{tag}", "real_name": f"R{tag}",
        })
        _assert(role in _MODEL_EDIT, r, role, "POST /models")


def test_project_edit_matrix(client, role_auth):
    for role in ROLES:
        tag = uuid.uuid4().hex[:6]
        r = client.post("/api/v1/projects", headers=role_auth[role], json={
            "project_name": f"P{tag}",
        })
        _assert(role in _PROJECT_EDIT, r, role, "POST /projects")


def test_user_manage_matrix(client, role_auth):
    for role in ROLES:
        r = client.get("/api/v1/users", headers=role_auth[role])
        _assert(role in _USER_MANAGE, r, role, "GET /users")


def test_audit_view_matrix(client, role_auth):
    for role in ROLES:
        r = client.get("/api/v1/audit-logs", headers=role_auth[role])
        _assert(role in _AUDIT_VIEW, r, role, "GET /audit-logs")
