"""DB-backed tests for the additive UI list endpoints.

Covers the read shapes the frontend consumes:
- GET /generations?project_id=...
- GET /outputs/{id}/reviews and /outputs/{id}/approvals
- GET /deliveries?project_id=...

Skipped automatically when no database is reachable (mirrors
tests/test_integration_flow.py).
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
def auth(client: TestClient) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _build_generation(client, auth):
    """Full compliant chain -> returns (project_id, generation_id, [output_ids])."""
    tag = uuid.uuid4().hex[:8]
    m = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"Model {tag}", "real_name": f"Real {tag}",
        "agency_name": "ABC", "birth_date": "1998-01-01",
    }).json()["data"]
    mid = m["id"]
    client.post(f"/api/v1/models/{mid}/adult-verification", headers=auth,
                json={"adult_verified": True})
    c = client.post(f"/api/v1/models/{mid}/contracts", headers=auth, json={
        "contract_number": f"CON-{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": "2027-12-31",
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]
    client.post(f"/api/v1/models/{mid}/permissions", headers=auth, json={
        "contract_id": c["id"],
        "media_scope": ["web", "sns"], "region_scope": ["japan"],
        "product_scope": ["beverage"], "prohibited_product_scope": ["finance"],
        "exposure_level_max": 2, "approval_required_level": "internal",
    })

    p = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"UI list {tag}", "client_name": "Client A",
        "product_category": "beverage", "deadline": "2026-12-31",
    }).json()["data"]
    pid = p["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", headers=auth, json={
        "media": ["web"], "region": ["japan"], "usage_start": "2026-09-01",
        "usage_end": "2026-12-31", "output_type": "image", "outfit_type": "normal",
        "exposure_level": 0,
    })
    client.post(f"/api/v1/projects/{pid}/models", headers=auth,
                json={"model_id": mid, "usage_role": "main"})

    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid, "prompt_text": "上品な宇宙背景で商品を持つ"}).json()["data"]
    assert chk["check_status"] == "ok", chk
    check_id = chk["compliance_check_id"]

    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な宇宙背景で商品を持つ",
        "generation_params": {"output_count": 2, "width": 1024, "height": 1280},
    })
    assert gen.status_code == 200, gen.text
    gid = gen.json()["data"]["generation_id"]
    outs = client.get(f"/api/v1/generations/{gid}/outputs", headers=auth).json()["data"]
    return pid, gid, [o["id"] for o in outs]


def test_list_generations_by_project(client, auth):
    pid, gid, _ = _build_generation(client, auth)
    r = client.get("/api/v1/generations", headers=auth, params={"project_id": pid})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    ids = [g["id"] for g in data]
    assert gid in ids
    g = next(g for g in data if g["id"] == gid)
    assert set(g.keys()) == {
        "id", "project_id", "model_id", "status", "output_count",
        "prompt_text", "generated_at",
    }
    assert g["project_id"] == pid
    assert g["generated_at"] is None or isinstance(g["generated_at"], str)


def test_reviews_and_approvals_lists(client, auth):
    pid, gid, output_ids = _build_generation(client, auth)
    oid = output_ids[0]

    # empty initially
    r = client.get(f"/api/v1/outputs/{oid}/reviews", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []
    a = client.get(f"/api/v1/outputs/{oid}/approvals", headers=auth)
    assert a.status_code == 200, a.text
    assert a.json()["data"] == []

    # after posting one review
    client.post(f"/api/v1/outputs/{oid}/reviews", headers=auth,
                json={"review_type": "visual", "status": "approved", "comment": "ok"})
    r2 = client.get(f"/api/v1/outputs/{oid}/reviews", headers=auth).json()["data"]
    assert len(r2) == 1
    assert set(r2[0].keys()) == {
        "id", "review_type", "status", "comment", "reviewer_id", "created_at",
    }
    assert r2[0]["status"] == "approved"

    # after posting one approval (internal level suffices for admin)
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                json={"approval_level": "internal", "approval_status": "approved"})
    a2 = client.get(f"/api/v1/outputs/{oid}/approvals", headers=auth).json()["data"]
    assert len(a2) == 1
    assert set(a2[0].keys()) == {
        "id", "approval_level", "approval_status", "approval_comment",
        "approver_id", "approved_at",
    }
    assert a2[0]["approval_status"] == "approved"


def test_list_deliveries_by_project(client, auth):
    pid, gid, output_ids = _build_generation(client, auth)
    oid = output_ids[0]

    # approve the output so delivery is permitted
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                json={"approval_level": "internal", "approval_status": "approved"})
    d = client.post("/api/v1/deliveries", headers=auth, json={
        "project_id": pid, "output_id": oid, "delivered_to": "client@example.com",
        "delivery_method": "download_link", "usage_media": ["web"],
        "usage_region": ["japan"], "usage_start": "2026-09-01",
        "usage_end": "2026-12-31",
    })
    assert d.status_code == 200, d.text
    did = d.json()["data"]["id"]

    r = client.get("/api/v1/deliveries", headers=auth, params={"project_id": pid})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    ids = [x["id"] for x in data]
    assert did in ids
    row = next(x for x in data if x["id"] == did)
    assert set(row.keys()) == {
        "id", "project_id", "output_id", "delivered_to", "delivery_method",
        "usage_media", "usage_region", "usage_start", "usage_end",
        "status", "created_at",
    }
    assert row["project_id"] == pid
