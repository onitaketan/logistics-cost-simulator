"""End-to-end integration test against a real Postgres.

Proves the central promise of the system: generation is blocked at BOTH the API
layer and the DB layer, not just hidden in the UI.

Requires a running Postgres and DATABASE_URL pointing at it, with the schema
applied (migrations/0001_init.sql) and seed run (scripts/seed.py). Skipped
automatically when no database is reachable.
"""

import os
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


def _make_model(client, auth, *, verify_adult: bool, with_permission: bool):
    tag = uuid.uuid4().hex[:8]
    m = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"Model {tag}", "real_name": f"Real {tag}",
        "agency_name": "ABC", "birth_date": "1998-01-01",
    }).json()["data"]
    mid = m["id"]
    if verify_adult:
        client.post(f"/api/v1/models/{mid}/adult-verification", headers=auth,
                    json={"adult_verified": True})
    c = client.post(f"/api/v1/models/{mid}/contracts", headers=auth, json={
        "contract_number": f"CON-{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": "2027-12-31",
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]
    if with_permission:
        client.post(f"/api/v1/models/{mid}/permissions", headers=auth, json={
            "contract_id": c["id"],
            "media_scope": ["web", "sns"], "region_scope": ["japan"],
            "product_scope": ["beverage"], "prohibited_product_scope": ["finance"],
            "exposure_level_max": 2, "approval_required_level": "internal",
        })
    return mid


def _make_project(client, auth):
    tag = uuid.uuid4().hex[:8]
    p = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"宇宙 飲料広告 {tag}", "client_name": "Client A",
        "product_category": "beverage", "deadline": "2026-12-31",
    }).json()["data"]
    pid = p["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", headers=auth, json={
        "media": ["web"], "region": ["japan"], "usage_start": "2026-09-01",
        "usage_end": "2026-12-31", "output_type": "image", "outfit_type": "normal",
        "exposure_level": 0,
    })
    return pid


def test_happy_path_generation_succeeds(client, auth):
    mid = _make_model(client, auth, verify_adult=True, with_permission=True)
    pid = _make_project(client, auth)
    client.post(f"/api/v1/projects/{pid}/models", headers=auth,
                json={"model_id": mid, "usage_role": "main"})

    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid, "prompt_text": "上品な宇宙背景で商品を持つ"})
    body = chk.json()["data"]
    assert body["check_status"] == "ok", body
    check_id = body["compliance_check_id"]

    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な宇宙背景で商品を持つ",
        "generation_params": {"output_count": 3, "width": 1024, "height": 1280},
    })
    assert gen.status_code == 200, gen.text
    assert gen.json()["data"]["status"] == "completed"
    gid = gen.json()["data"]["generation_id"]
    outs = client.get(f"/api/v1/generations/{gid}/outputs", headers=auth).json()["data"]
    assert len(outs) == 3


def test_no_adult_verification_blocks_generation_at_api(client, auth):
    # model has contract+permission but adult NOT verified -> compliance prohibited
    mid = _make_model(client, auth, verify_adult=False, with_permission=True)
    pid = _make_project(client, auth)
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid}).json()["data"]
    assert chk["check_status"] == "prohibited", chk
    check_id = chk["compliance_check_id"]

    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "x", "generation_params": {"output_count": 1},
    })
    assert gen.status_code == 422, gen.text
    assert "生成" in gen.json()["error"]["message"]


def test_db_trigger_blocks_generation_for_ng_check(client, auth):
    """Even if the API were bypassed, the DB trigger refuses an ng/prohibited check."""
    with engine.begin() as conn:
        pid = conn.execute(text(
            "INSERT INTO projects (project_name) VALUES ('trig-test') RETURNING id")).scalar()
        mid = conn.execute(text(
            "INSERT INTO models (stage_name, real_name, adult_verified) "
            "VALUES ('t','t', false) RETURNING id")).scalar()
        ng_check = conn.execute(text(
            "INSERT INTO compliance_checks (project_id, model_id, check_status) "
            "VALUES (:p, :m, 'ng') RETURNING id"), {"p": pid, "m": mid}).scalar()

    with pytest.raises(Exception) as exc:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO generations (project_id, model_id, compliance_check_id, prompt_text) "
                "VALUES (:p, :m, :c, 'x')"), {"p": pid, "m": mid, "c": ng_check})
    assert "generation blocked" in str(exc.value).lower()
