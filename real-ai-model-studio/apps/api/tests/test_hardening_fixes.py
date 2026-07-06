"""Hardening-round repairs — verification.

1. PATCH /outputs/{id}/status must NOT accept 'approved'/'delivered' (a REVIEW-role
   user could otherwise bypass the multi-level approval gate).
2. Audit-log date filters (?from=&to=) must actually filter.
3. Admin password reset via PATCH /users/{id} must work, never leak the value
   into the audit log, and allow login with the new password.
4. /audit-logs/export must return CSV.

Requires a running Postgres (schema + seed applied); skips without.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


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
def auth(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@example.com", "password": "ChangeMe123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _any_output(client, auth) -> str:
    """Grab any existing output id (created by earlier test chains / demo)."""
    with engine.connect() as c:
        oid = c.execute(text("select id from generation_outputs limit 1")).scalar()
    assert oid, "expected at least one output in the test DB"
    return str(oid)


def test_status_endpoint_rejects_approved_and_delivered(client, auth):
    oid = _any_output(client, auth)
    for forbidden in ("approved", "delivered"):
        r = client.patch(f"/api/v1/outputs/{oid}/status", headers=auth,
                         json={"output_status": forbidden})
        assert r.status_code == 422, (forbidden, r.status_code, r.text)
    # selection statuses still work
    r = client.patch(f"/api/v1/outputs/{oid}/status", headers=auth,
                     json={"output_status": "selected"})
    assert r.status_code == 200, r.text


def test_audit_date_filter_actually_filters(client, auth):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = client.get(f"/api/v1/audit-logs?from={tomorrow}", headers=auth)
    assert r.status_code == 200
    assert r.json()["data"] == []  # nothing from the future
    r2 = client.get(f"/api/v1/audit-logs?to={date.today().isoformat()}", headers=auth)
    assert len(r2.json()["data"]) > 0  # today's activity present


def test_admin_password_reset_and_login(client, auth):
    tag = uuid.uuid4().hex[:6]
    u = client.post("/api/v1/users", headers=auth, json={
        "name": f"pw{tag}", "email": f"pw{tag}@example.com",
        "password": "InitialPw123", "role": "viewer",
    }).json()["data"]

    r = client.patch(f"/api/v1/users/{u['id']}", headers=auth,
                     json={"password": "NewSecret456"})
    assert r.status_code == 200, r.text
    assert "password" not in r.text.lower() or "password_reset" in r.text  # value never echoed

    # old password refused, new one accepted
    bad = client.post("/api/v1/auth/login",
                      json={"email": u["email"], "password": "InitialPw123"})
    assert bad.status_code == 401
    good = client.post("/api/v1/auth/login",
                       json={"email": u["email"], "password": "NewSecret456"})
    assert good.status_code == 200, good.text

    # audit log records the reset as a flag, never the value
    with engine.connect() as c:
        rows = c.execute(text(
            "select after_data::text from audit_logs "
            "where target_type='user' and target_id=:i order by created_at desc limit 1"),
            {"i": u["id"]}).scalar()
    assert "NewSecret456" not in (rows or "")
    assert "password_reset" in (rows or "")


def test_audit_csv_export(client, auth):
    r = client.get("/api/v1/audit-logs/export", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text.splitlines()
    assert body[0].startswith("created_at,user_id,action_type")
    assert len(body) > 1  # at least one data row
