"""Second audit round — verification of the confirmed safety/correctness fixes.

Unit (pure engine, no DB):
  * exposure level 4 with a generic outfit label is Conditional, not silently OK.

DB-backed (skips without a database):
  * prompt screening at the generation boundary rejects a prohibited prompt even
    when the compliance check passed (SEC-F1 / COMP-#2).
  * output_count is clamped to a sane maximum (SEC-F5).
  * separation of duties: one user cannot fill two distinct approval levels (SEC-F3).
  * the selection-status endpoint cannot walk an approved output back (SEC-F13).
  * a delivery must reference an output that belongs to its project (SEC-F4).
  * a permission cannot bind to a contract of a different model (SEC-F10).
  * preview of an unapproved image is denied to a plain viewer role (SEC-F9).
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services.compliance_engine import (
    ContractInput,
    ModelInput,
    PermissionInput,
    RequirementInput,
    Status,
    evaluate,
)

TODAY = date(2026, 7, 4)


# ---- Unit: exposure level 4 (COMP-#1) ----

def test_exposure_level_4_generic_outfit_is_conditional():
    model = ModelInput(adult_verified=True, birth_date=date(1998, 1, 1))
    contract = ContractInput(
        contract_end=date(2027, 6, 30),
        ai_generation_allowed=True,
        ai_training_allowed=True,
    )
    perm = PermissionInput(
        media_scope={"web"}, region_scope={"japan"}, product_scope={"beverage"},
        prohibited_product_scope=set(), swimwear_allowed=True, underwear_allowed=True,
        bath_allowed="conditional", exposure_level_max=4, overseas_allowed=False,
        secondary_use_allowed=False, video_allowed=False,
        age_appearance_change_allowed=False, approval_required_level="legal",
    )
    req = RequirementInput(
        media={"web"}, region={"japan"}, product_category="beverage",
        output_type="image", outfit_type="normal",  # generic label, level says 4
        exposure_level=4, usage_end=date(2026, 12, 31),
    )
    r = evaluate(model, contract, perm, req, TODAY)
    # Must NOT be OK: level-4 body exposure requires legal + agency sign-off.
    assert r.status == Status.CONDITIONAL, r.summary
    assert "legal" in r.required_approvals and "agency" in r.required_approvals


# ---- DB-backed fixtures ----

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


db_only = pytest.mark.skipif(not _db_available(), reason="no database available")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client: TestClient) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _build_chain(client, auth, *, exposure_max=2):
    """Full compliant chain -> (project_id, model_id, compliance_check_id)."""
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
        "exposure_level_max": exposure_max, "approval_required_level": "internal",
    })
    p = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"AR2 {tag}", "client_name": "Client",
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
                      json={"model_id": mid, "prompt_text": "上品な背景で商品を持つ"}).json()["data"]
    assert chk["check_status"] == "ok", chk
    return pid, mid, chk["compliance_check_id"]


@db_only
def test_generation_rejects_prohibited_prompt(client, auth):
    pid, mid, check_id = _build_chain(client, auth)
    # Compliance check passed, but the actual prompt smuggles a prohibited term.
    r = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "nude portrait on a beach",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    })
    assert r.status_code == 422, r.text
    assert "禁止" in r.json()["error"]["message"]


@db_only
def test_output_count_is_clamped(client, auth):
    pid, mid, check_id = _build_chain(client, auth)
    r = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 999, "width": 512, "height": 512},
    })
    assert r.status_code == 200, r.text
    gid = r.json()["data"]["generation_id"]
    g = client.get(f"/api/v1/generations/{gid}", headers=auth).json()["data"]
    assert g["output_count"] <= 8


@db_only
def test_separation_of_duties_blocks_same_user_two_levels(client, auth):
    pid, mid, check_id = _build_chain(client, auth)
    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    oid = client.get(f"/api/v1/generations/{gen['generation_id']}/outputs",
                     headers=auth).json()["data"][0]["id"]
    # First approval (internal) — fine.
    r1 = client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                     json={"approval_level": "internal", "approval_status": "approved"})
    assert r1.status_code == 200, r1.text
    # Same user, a DIFFERENT level (legal) — blocked by separation of duties.
    r2 = client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                     json={"approval_level": "legal", "approval_status": "approved"})
    assert r2.status_code == 409, r2.text


@db_only
def test_status_cannot_regress_from_approved(client, auth):
    pid, mid, check_id = _build_chain(client, auth)
    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    oid = client.get(f"/api/v1/generations/{gen['generation_id']}/outputs",
                     headers=auth).json()["data"][0]["id"]
    # Drive to approved (internal suffices for this permission's required level).
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                json={"approval_level": "internal", "approval_status": "approved"})
    # Now the selection endpoint must refuse to walk it back.
    r = client.patch(f"/api/v1/outputs/{oid}/status", headers=auth,
                     json={"output_status": "candidate"})
    assert r.status_code == 409, r.text


@db_only
def test_delivery_rejects_output_from_other_project(client, auth):
    # Project A produces and approves an output.
    pid_a, mid, check_id = _build_chain(client, auth)
    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid_a, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    oid = client.get(f"/api/v1/generations/{gen['generation_id']}/outputs",
                     headers=auth).json()["data"][0]["id"]
    client.post(f"/api/v1/outputs/{oid}/approvals", headers=auth,
                json={"approval_level": "internal", "approval_status": "approved"})
    # A separate project B tries to deliver project A's output.
    pid_b, _, _ = _build_chain(client, auth)
    r = client.post("/api/v1/deliveries", headers=auth, json={
        "project_id": pid_b, "output_id": oid, "delivered_to": "c@example.com",
        "delivery_method": "download_link",
    })
    assert r.status_code == 422, r.text
    assert "案件" in r.json()["detail"]


@db_only
def test_permission_rejects_contract_of_other_model(client, auth):
    _pid_a, mid_a, _ = _build_chain(client, auth)
    # A contract that belongs to model A.
    with engine.connect() as c:
        cid = c.execute(text(
            "select id from model_contracts where model_id=:m limit 1"),
            {"m": mid_a}).scalar()
    # A brand new model B tries to attach a permission to model A's contract.
    tag = uuid.uuid4().hex[:8]
    mb = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"MB {tag}", "real_name": f"RB {tag}",
    }).json()["data"]["id"]
    r = client.post(f"/api/v1/models/{mb}/permissions", headers=auth, json={
        "contract_id": str(cid), "media_scope": ["web"],
    })
    assert r.status_code == 400, r.text
    assert "モデル" in r.json()["detail"]


@db_only
def test_preview_denied_to_viewer(client, auth):
    pid, mid, check_id = _build_chain(client, auth)
    gen = client.post("/api/v1/generations", headers=auth, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    oid = client.get(f"/api/v1/generations/{gen['generation_id']}/outputs",
                     headers=auth).json()["data"][0]["id"]
    # Create a viewer and log in as them.
    tag = uuid.uuid4().hex[:6]
    client.post("/api/v1/users", headers=auth, json={
        "name": f"v{tag}", "email": f"v{tag}@example.com",
        "password": "ViewerPass123", "role": "viewer",
    })
    vtok = client.post("/api/v1/auth/login", json={
        "email": f"v{tag}@example.com", "password": "ViewerPass123"}).json()["data"]["access_token"]
    vauth = {"Authorization": f"Bearer {vtok}"}
    r = client.get(f"/api/v1/outputs/{oid}/preview", headers=vauth)
    assert r.status_code == 403, r.text
