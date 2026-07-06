"""Revision generation (P1-006) and reviewer preview — repair verification.

Revise must create a REAL new generation (not a stub) that passes all three
gates, and must be blocked when the parent's compliance check no longer allows
generation. Preview must give reviewers a signed URL for stored images (null for
mock placeholders) and audit the access as action_type='view' (migration 0002).

Requires a running Postgres (schema 0001+0002 applied, seed run); skips without.
"""

import os
import uuid

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
def auth(client: TestClient) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@example.com", "password": "ChangeMe123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _make_chain(client, auth):
    """model(adult)+contract+permission+project+requirement -> ok check -> generation."""
    tag = uuid.uuid4().hex[:6]
    mid = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"rev{tag}", "real_name": f"本名{tag}", "birth_date": "1997-01-01",
    }).json()["data"]["id"]
    client.post(f"/api/v1/models/{mid}/adult-verification", headers=auth,
                json={"adult_verified": True})
    ct = client.post(f"/api/v1/models/{mid}/contracts", headers=auth, json={
        "contract_number": f"C-{tag}", "contract_start": "2026-01-01",
        "contract_end": "2027-12-31", "ai_generation_allowed": True,
    }).json()["data"]
    client.post(f"/api/v1/models/{mid}/permissions", headers=auth, json={
        "contract_id": ct["id"], "media_scope": ["web"], "region_scope": ["japan"],
        "product_scope": ["beverage"], "exposure_level_max": 2,
        "approval_required_level": "internal",
    })
    pid = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"rev案件{tag}", "product_category": "beverage",
    }).json()["data"]["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", headers=auth,
                json={"media": ["web"], "region": ["japan"], "exposure_level": 0})
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid}).json()["data"]
    assert chk["check_status"] == "ok"
    g = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid,
        "compliance_check_id": chk["compliance_check_id"],
        "prompt_text": "上品な広告", "generation_params": {"output_count": 1},
    }).json()["data"]
    outs = client.get(f"/api/v1/generations/{g['generation_id']}/outputs",
                      headers=auth).json()["data"]
    return chk["compliance_check_id"], g["generation_id"], outs[0]


def test_revise_creates_new_generation_with_outputs(client, auth):
    _, parent_gid, out = _make_chain(client, auth)
    r = client.post(f"/api/v1/outputs/{out['id']}/revise", headers=auth,
                    json={"revision_prompt": "背景をより高級感のある照明に変更"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["generation_id"] != parent_gid
    assert data["status"] == "completed"  # eager worker runs inline
    outs = client.get(f"/api/v1/generations/{data['generation_id']}/outputs",
                      headers=auth).json()["data"]
    assert len(outs) == 1  # real outputs — not a stub


def test_revise_blocked_when_check_flipped_to_ng(client, auth):
    check_id, _, out = _make_chain(client, auth)
    with engine.begin() as c:
        c.execute(text("update compliance_checks set check_status='ng' where id=:c"),
                  {"c": check_id})
    r = client.post(f"/api/v1/outputs/{out['id']}/revise", headers=auth,
                    json={"revision_prompt": "x"})
    assert r.status_code == 422, r.text


def test_preview_mock_output_returns_null(client, auth):
    _, _, out = _make_chain(client, auth)
    r = client.get(f"/api/v1/outputs/{out['id']}/preview", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["preview_url"] is None  # mock:// has no stored bytes


def test_preview_stored_output_returns_signed_url_and_audits_view(client, auth):
    _, gid, _ = _make_chain(client, auth)
    # A stored (non-mock) output, as the real-engine worker would write it.
    oid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text(
            "insert into generation_outputs (id, generation_id, file_path, file_hash) "
            "values (:i, :g, 'local://rams-private/generations/x/0.png', 'h')"),
            {"i": oid, "g": gid})
    r = client.get(f"/api/v1/outputs/{oid}/preview", headers=auth)
    assert r.status_code == 200, r.text
    url = r.json()["data"]["preview_url"]
    assert url and "/api/v1/files?" in url and "sig=" in url
    with engine.connect() as c:
        n = c.execute(text(
            "select count(*) from audit_logs where action_type='view' and target_id=:i"),
            {"i": oid}).scalar()
    assert n == 1  # migration 0002 + audit trail for image access
