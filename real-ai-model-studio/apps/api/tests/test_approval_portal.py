"""External approval portal (P2-001/P2-002) — verification.

Builds a bath scenario whose compliance check requires agency sign-off, issues a
portal link, and drives the public token endpoints:
  * an internal legal-level user can issue a link only for a required level;
  * the public GET/POST work WITHOUT auth and record an external approval that
    flows through the completeness gate;
  * links are single-use, and invalid tokens 404;
  * a viewer cannot issue; issuing an unrequired level is refused.

Requires a running Postgres (schema 0003 applied + seed); skips without.
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
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _build_bath_output(client, auth) -> str:
    """Full chain with a bath requirement -> compliance requires legal+agency.
    Returns an output id in candidate state."""
    tag = uuid.uuid4().hex[:8]
    m = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"M{tag}", "real_name": f"R{tag}", "birth_date": "1996-01-01",
    }).json()["data"]
    mid = m["id"]
    client.post(f"/api/v1/models/{mid}/adult-verification", headers=auth,
                json={"adult_verified": True})
    c = client.post(f"/api/v1/models/{mid}/contracts", headers=auth, json={
        "contract_number": f"C{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": "2027-12-31",
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]
    client.post(f"/api/v1/models/{mid}/permissions", headers=auth, json={
        "contract_id": c["id"], "media_scope": ["web"], "region_scope": ["japan"],
        "product_scope": ["beverage"], "bath_allowed": "conditional",
        "exposure_level_max": 4, "approval_required_level": "legal",
    })
    p = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"bath {tag}", "product_category": "beverage"}).json()["data"]
    pid = p["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", headers=auth, json={
        "media": ["web"], "region": ["japan"], "output_type": "image",
        "outfit_type": "bath", "exposure_level": 0,
    })
    client.post(f"/api/v1/projects/{pid}/models", headers=auth,
                json={"model_id": mid, "usage_role": "main"})
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid, "prompt_text": "入浴シーンの上品な広告カット"}).json()["data"]
    assert chk["check_status"] == "conditional", chk
    assert "agency" in chk["required_approvals"], chk
    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": chk["compliance_check_id"],
        "prompt_text": "入浴シーンの上品な広告カット",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    return client.get(f"/api/v1/generations/{gen['generation_id']}/outputs",
                      headers=auth).json()["data"][0]["id"]


def test_portal_full_flow(client, auth):
    oid = _build_bath_output(client, auth)

    # issue an agency link (admin has APPROVE_LEGAL)
    iss = client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=auth,
                      json={"level": "agency", "contact_name": "Agency X"})
    assert iss.status_code == 200, iss.text
    token = iss.json()["data"]["token"]
    assert iss.json()["data"]["portal_path"].endswith(token)

    # public view — NO auth header
    view = client.get(f"/api/v1/portal/approvals/{token}")
    assert view.status_code == 200, view.text
    vd = view.json()["data"]
    assert vd["level"] == "agency" and vd["already_decided"] is False

    # public decision — NO auth header
    dec = client.post(f"/api/v1/portal/approvals/{token}",
                      json={"decision": "approved", "approver_name": "田中（事務所）"})
    assert dec.status_code == 200, dec.text
    # legal still missing, so not yet fully approved
    assert dec.json()["data"]["output_status"] != "approved"

    # the external approval is recorded at agency level
    apprs = client.get(f"/api/v1/outputs/{oid}/approvals", headers=auth).json()["data"]
    assert any(a["approval_level"] == "agency" and a["approval_status"] == "approved"
               for a in apprs)

    # single-use: the link cannot be reused
    again = client.post(f"/api/v1/portal/approvals/{token}", json={"decision": "approved"})
    assert again.status_code == 409, again.text

    # after legal also approves in-system, the output becomes approved
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                json={"approval_level": "legal", "approval_status": "approved"})
    final = client.get(f"/api/v1/outputs/{oid}/approvals", headers=auth)
    assert final.status_code == 200
    with engine.connect() as conn:
        st = conn.execute(text("select output_status from generation_outputs where id=:i"),
                          {"i": oid}).scalar()
    assert st == "approved"


def test_invalid_token_404(client):
    assert client.get("/api/v1/portal/approvals/nope").status_code == 404
    assert client.post("/api/v1/portal/approvals/nope",
                       json={"decision": "approved"}).status_code == 404


def test_issue_unrequired_level_rejected(client, auth):
    oid = _build_bath_output(client, auth)
    # bath requires legal+agency, NOT person
    r = client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=auth,
                    json={"level": "person"})
    assert r.status_code == 422, r.text


def test_viewer_cannot_issue(client, auth):
    oid = _build_bath_output(client, auth)
    tag = uuid.uuid4().hex[:6]
    client.post("/api/v1/users", headers=auth, json={
        "name": f"v{tag}", "email": f"v{tag}@example.com",
        "password": "ViewerPass123", "role": "viewer"})
    vtok = client.post("/api/v1/auth/login", json={
        "email": f"v{tag}@example.com", "password": "ViewerPass123"}).json()["data"]["access_token"]
    r = client.post(f"/api/v1/outputs/{oid}/approval-requests",
                    headers={"Authorization": f"Bearer {vtok}"}, json={"level": "agency"})
    assert r.status_code == 403, r.text
