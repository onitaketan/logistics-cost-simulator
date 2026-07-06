"""External approval portal (P2-001/P2-002) — verification, incl. review fixes.

Builds a bath scenario whose compliance check requires agency sign-off, issues a
portal link, and drives the public token endpoints:
  * issuing requires a contact email and a level the check actually requires;
  * the public GET/POST work WITHOUT auth and record an external approval that
    flows through the completeness gate;
  * separation of duties: the internal issuer (accountable for an external link)
    cannot also record a DIFFERENT level in-system;
  * links are single-use and revocable; invalid tokens 404;
  * a reviewer-rejected output cannot be issued a link.

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


def _make_user(client, auth, role: str) -> dict:
    tag = uuid.uuid4().hex[:8]
    email = f"{role}{tag}@example.com"
    client.post("/api/v1/users", headers=auth, json={
        "name": f"{role}-{tag}", "email": email, "password": "RolePass123", "role": role})
    tok = client.post("/api/v1/auth/login",
                      json={"email": email, "password": "RolePass123"}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


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


def _issue(client, auth, oid, level="agency"):
    return client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=auth,
                       json={"level": level, "contact_name": "Agency X",
                             "contact_email": "agency@example.com"})


def test_portal_full_flow(client, auth):
    oid = _build_bath_output(client, auth)
    legal = _make_user(client, auth, "legal")  # distinct party for the legal level

    iss = _issue(client, auth, oid, "agency")
    assert iss.status_code == 200, iss.text
    token = iss.json()["data"]["token"]

    # public view — NO auth header
    vd = client.get(f"/api/v1/portal/approvals/{token}").json()["data"]
    assert vd["level"] == "agency" and vd["already_decided"] is False

    # public decision — NO auth header
    dec = client.post(f"/api/v1/portal/approvals/{token}",
                      json={"decision": "approved", "approver_name": "田中（事務所）"})
    assert dec.status_code == 200, dec.text
    assert dec.json()["data"]["output_status"] != "approved"  # legal still missing

    apprs = client.get(f"/api/v1/outputs/{oid}/approvals", headers=auth).json()["data"]
    assert any(a["approval_level"] == "agency" and a["approval_status"] == "approved"
               for a in apprs)

    # single-use: reuse blocked
    assert client.post(f"/api/v1/portal/approvals/{token}",
                       json={"decision": "approved"}).status_code == 409
    # closed link leaks no metadata
    closed = client.get(f"/api/v1/portal/approvals/{token}").json()["data"]
    assert closed["already_decided"] is True and closed["level"] is None

    # a DISTINCT legal user finishes the gate -> approved
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=legal,
                json={"approval_level": "legal", "approval_status": "approved"})
    with engine.connect() as conn:
        st = conn.execute(text("select output_status from generation_outputs where id=:i"),
                          {"i": oid}).scalar()
    assert st == "approved"


def test_separation_of_duties_issuer_cannot_also_record_other_level(client, auth):
    oid = _build_bath_output(client, auth)
    token = _issue(client, auth, oid, "agency").json()["data"]["token"]
    client.post(f"/api/v1/portal/approvals/{token}", json={"decision": "approved"})
    # admin issued+is accountable for the agency approval; recording legal too collapses SoD
    r = client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                    json={"approval_level": "legal", "approval_status": "approved"})
    assert r.status_code == 409, r.text


def test_revoke_kills_link(client, auth):
    oid = _build_bath_output(client, auth)
    iss = _issue(client, auth, oid, "agency").json()["data"]
    rid, token = iss["id"], iss["token"]
    rv = client.post(f"/api/v1/outputs/{oid}/approval-requests/{rid}/revoke", headers=auth)
    assert rv.status_code == 200, rv.text
    # revoked link cannot be viewed as open, nor decided
    assert client.get(f"/api/v1/portal/approvals/{token}").json()["data"]["already_decided"] is True
    assert client.post(f"/api/v1/portal/approvals/{token}",
                       json={"decision": "approved"}).status_code == 409


def test_issue_requires_email(client, auth):
    oid = _build_bath_output(client, auth)
    r = client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=auth,
                    json={"level": "agency"})  # no contact_email
    assert r.status_code == 422, r.text


def test_rejected_output_cannot_issue(client, auth):
    oid = _build_bath_output(client, auth)
    client.patch(f"/api/v1/outputs/{oid}/status", headers=auth, json={"output_status": "rejected"})
    r = _issue(client, auth, oid, "agency")
    assert r.status_code == 409, r.text


def test_invalid_token_404(client):
    assert client.get("/api/v1/portal/approvals/nope").status_code == 404
    assert client.post("/api/v1/portal/approvals/nope",
                       json={"decision": "approved"}).status_code == 404


def test_issue_unrequired_level_rejected(client, auth):
    oid = _build_bath_output(client, auth)
    # bath requires legal+agency, NOT person
    r = client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=auth,
                    json={"level": "person", "contact_email": "p@example.com"})
    assert r.status_code == 422, r.text


def test_viewer_cannot_issue(client, auth):
    oid = _build_bath_output(client, auth)
    vauth = _make_user(client, auth, "viewer")
    r = client.post(f"/api/v1/outputs/{oid}/approval-requests", headers=vauth,
                    json={"level": "agency", "contact_email": "a@example.com"})
    assert r.status_code == 403, r.text
