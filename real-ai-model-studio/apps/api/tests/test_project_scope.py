"""Project-scoped data authorization (migration 0004) — verification.

RBAC says WHAT; this says WHICH projects. Non-global roles (not admin/legal) may
only see/act on projects they own or are members of. Covers:
  * list filtering + get gate for a non-owner;
  * membership grant/revoke flips access;
  * only the owner/admin may manage members;
  * generation is refused for a non-member and allowed once added;
  * admin/legal keep system-wide visibility.

Requires a running Postgres (schema incl. 0004 + seed); skips without.
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
def admin(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _user(client, admin, role: str) -> tuple[str, dict]:
    tag = uuid.uuid4().hex[:8]
    email = f"{role}{tag}@example.com"
    uid = client.post("/api/v1/users", headers=admin, json={
        "name": f"{role}-{tag}", "email": email, "password": "RolePass123",
        "role": role}).json()["data"]["id"]
    tok = client.post("/api/v1/auth/login",
                      json={"email": email, "password": "RolePass123"}).json()["data"]["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def _project(client, auth, name="scoped") -> str:
    tag = uuid.uuid4().hex[:6]
    return client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"{name}-{tag}", "product_category": "beverage"}).json()["data"]["id"]


def test_non_owner_cannot_see_or_access_project(client, admin):
    _uid_a, a = _user(client, admin, "sales")
    _uid_b, b = _user(client, admin, "sales")
    pid = _project(client, a)

    # owner sees it; other sales user does not
    assert any(p["id"] == pid for p in client.get("/api/v1/projects", headers=a).json()["data"])
    assert all(p["id"] != pid for p in client.get("/api/v1/projects", headers=b).json()["data"])
    assert client.get(f"/api/v1/projects/{pid}", headers=a).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 403
    # admin (global) sees it
    assert client.get(f"/api/v1/projects/{pid}", headers=admin).status_code == 200


def test_membership_grants_and_revokes_access(client, admin):
    _uid_a, a = _user(client, admin, "sales")
    uid_b, b = _user(client, admin, "sales")
    pid = _project(client, a)

    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 403
    # owner adds B
    add = client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"user_id": uid_b})
    assert add.status_code == 200, add.text
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 200
    assert any(p["id"] == pid for p in client.get("/api/v1/projects", headers=b).json()["data"])
    # owner removes B
    rem = client.delete(f"/api/v1/projects/{pid}/members/{uid_b}", headers=a)
    assert rem.status_code == 200, rem.text
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 403


def test_only_owner_or_admin_manages_members(client, admin):
    _uid_a, a = _user(client, admin, "sales")
    uid_b, b = _user(client, admin, "sales")
    uid_c, _c = _user(client, admin, "sales")
    pid = _project(client, a)

    # non-member B cannot add members
    assert client.post(f"/api/v1/projects/{pid}/members", headers=b,
                       json={"user_id": uid_c}).status_code == 403
    # owner adds B as a member; B (member but not owner) still cannot manage members
    client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"user_id": uid_b})
    assert client.post(f"/api/v1/projects/{pid}/members", headers=b,
                       json={"user_id": uid_c}).status_code == 403
    # admin can
    assert client.post(f"/api/v1/projects/{pid}/members", headers=admin,
                       json={"user_id": uid_c}).status_code == 200
    # owner cannot be removed
    _uid_a_row = client.get(f"/api/v1/projects/{pid}/members", headers=a).json()["data"]
    owner = next(m for m in _uid_a_row if m["is_owner"])
    assert client.delete(f"/api/v1/projects/{pid}/members/{owner['user_id']}",
                         headers=a).status_code == 409


def test_add_member_by_email(client, admin):
    _uid_a, a = _user(client, admin, "sales")
    tag = uuid.uuid4().hex[:8]
    email = f"bymail{tag}@example.com"
    client.post("/api/v1/users", headers=admin, json={
        "name": f"bymail{tag}", "email": email, "password": "RolePass123", "role": "sales"})
    b_tok = client.post("/api/v1/auth/login",
                        json={"email": email, "password": "RolePass123"}).json()["data"]["access_token"]
    b = {"Authorization": f"Bearer {b_tok}"}
    pid = _project(client, a)
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 403
    add = client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"email": email})
    assert add.status_code == 200, add.text
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 200


def _build_model(client, admin) -> str:
    tag = uuid.uuid4().hex[:8]
    mid = client.post("/api/v1/models", headers=admin, json={
        "stage_name": f"M{tag}", "real_name": f"R{tag}", "birth_date": "1996-01-01",
    }).json()["data"]["id"]
    client.post(f"/api/v1/models/{mid}/adult-verification", headers=admin,
                json={"adult_verified": True})
    c = client.post(f"/api/v1/models/{mid}/contracts", headers=admin, json={
        "contract_number": f"C{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": "2027-12-31",
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]
    client.post(f"/api/v1/models/{mid}/permissions", headers=admin, json={
        "contract_id": c["id"], "media_scope": ["web"], "region_scope": ["japan"],
        "product_scope": ["beverage"], "exposure_level_max": 2,
        "approval_required_level": "internal"})
    return mid


def test_generation_is_project_scoped(client, admin):
    mid = _build_model(client, admin)
    _uid_a, a = _user(client, admin, "sales")      # owner, runs compliance
    _uid_c, c = _user(client, admin, "creative")   # generator, initially NOT a member
    uid_c = _uid_c

    pid = _project(client, a)
    client.post(f"/api/v1/projects/{pid}/requirements", headers=a, json={
        "media": ["web"], "region": ["japan"], "output_type": "image",
        "outfit_type": "normal", "exposure_level": 0})
    client.post(f"/api/v1/projects/{pid}/models", headers=a,
                json={"model_id": mid, "usage_role": "main"})
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=a,
                      json={"model_id": mid, "prompt_text": "上品な背景"}).json()["data"]
    check_id = chk["compliance_check_id"]

    gen_payload = {
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }
    # creative-C is not a member -> generation refused
    assert client.post("/api/v1/generations", headers=c, json=gen_payload).status_code == 403
    # add C as a member -> now allowed
    client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"user_id": uid_c})
    assert client.post("/api/v1/generations", headers=c, json=gen_payload).status_code == 200


def _scoped_generation(client, admin):
    """Sales-owned project with a creative member who generates one output.
    Returns (pid, owner_auth, member_auth, generation_id, output_id)."""
    mid = _build_model(client, admin)
    _a_id, a = _user(client, admin, "sales")       # owner
    c_id, c = _user(client, admin, "creative")     # member/generator
    pid = _project(client, a)
    client.post(f"/api/v1/projects/{pid}/requirements", headers=a, json={
        "media": ["web"], "region": ["japan"], "output_type": "image",
        "outfit_type": "normal", "exposure_level": 0})
    client.post(f"/api/v1/projects/{pid}/models", headers=a,
                json={"model_id": mid, "usage_role": "main"})
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=a,
                      json={"model_id": mid, "prompt_text": "上品な背景"}).json()["data"]
    client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"user_id": c_id})
    gen = client.post("/api/v1/generations", headers=c, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": chk["compliance_check_id"],
        "prompt_text": "上品な背景で商品を持つ",
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }).json()["data"]
    gid = gen["generation_id"]
    oid = client.get(f"/api/v1/generations/{gid}/outputs", headers=c).json()["data"][0]["id"]
    return pid, a, c, gid, oid


def test_output_review_and_approval_lists_are_scoped(client, admin):
    _pid, _a, c, _gid, oid = _scoped_generation(client, admin)
    _b_id, b = _user(client, admin, "sales")  # non-member
    # non-member cannot read the review/approval trail
    assert client.get(f"/api/v1/outputs/{oid}/reviews", headers=b).status_code == 403
    assert client.get(f"/api/v1/outputs/{oid}/approvals", headers=b).status_code == 403
    # the member can
    assert client.get(f"/api/v1/outputs/{oid}/reviews", headers=c).status_code == 200
    assert client.get(f"/api/v1/outputs/{oid}/approvals", headers=c).status_code == 200


def test_soft_deleted_project_hidden_from_member_generation_list(client, admin):
    pid, a, c, gid, _oid = _scoped_generation(client, admin)
    # member sees the generation while the project is live
    assert any(g["id"] == gid for g in client.get("/api/v1/generations", headers=c).json()["data"])
    # owner soft-deletes the project
    assert client.delete(f"/api/v1/projects/{pid}", headers=a).status_code == 200
    # member must no longer see the deleted project's generations
    assert all(g["id"] != gid for g in client.get("/api/v1/generations", headers=c).json()["data"])


def test_cannot_add_suspended_member(client, admin):
    _a_id, a = _user(client, admin, "sales")
    tag = uuid.uuid4().hex[:8]
    email = f"susp{tag}@example.com"
    u = client.post("/api/v1/users", headers=admin, json={
        "name": f"susp{tag}", "email": email, "password": "RolePass123", "role": "sales"}).json()["data"]
    client.patch(f"/api/v1/users/{u['id']}", headers=admin, json={"status": "suspended"})
    pid = _project(client, a)
    r = client.post(f"/api/v1/projects/{pid}/members", headers=a, json={"email": email})
    assert r.status_code == 409, r.text


def test_compliance_check_refused_for_non_member(client, admin):
    mid = _build_model(client, admin)
    _uid_a, a = _user(client, admin, "sales")
    _uid_b, b = _user(client, admin, "sales")
    pid = _project(client, a)
    client.post(f"/api/v1/projects/{pid}/requirements", headers=a, json={
        "media": ["web"], "region": ["japan"], "output_type": "image",
        "outfit_type": "normal", "exposure_level": 0})
    # b is not a member of a's project
    r = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=b,
                    json={"model_id": mid, "prompt_text": "x"})
    assert r.status_code == 403, r.text
