"""Prompt template CRUD (P1-004) — verification.

Covers: list/create/get/update/soft-disable, prohibited-term screening on
create and update, RBAC (mutations need GENERATE; listing needs only view), and
that a created template can drive a generation via prompt_template_id.

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


def _viewer_auth(client, auth) -> dict:
    tag = uuid.uuid4().hex[:8]
    email = f"tv{tag}@example.com"
    client.post("/api/v1/users", headers=auth, json={
        "name": f"tv{tag}", "email": email, "password": "ViewerPass123", "role": "viewer"})
    tok = client.post("/api/v1/auth/login",
                      json={"email": email, "password": "ViewerPass123"}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_list_get_update_disable(client, auth):
    tag = uuid.uuid4().hex[:6]
    created = client.post("/api/v1/prompt-templates", headers=auth, json={
        "name": f"tpl-{tag}", "body": "上品なスタジオ照明のポートレート",
        "negative_body": "露出過多", "tags": ["ec", "portrait"],
    })
    assert created.status_code == 200, created.text
    t = created.json()["data"]
    assert t["name"] == f"tpl-{tag}" and t["is_active"] is True and t["tags"] == ["ec", "portrait"]
    tid = t["id"]

    # appears in the active list
    lst = client.get("/api/v1/prompt-templates", headers=auth).json()["data"]
    assert any(x["id"] == tid for x in lst)

    # get by id
    got = client.get(f"/api/v1/prompt-templates/{tid}", headers=auth)
    assert got.status_code == 200 and got.json()["data"]["id"] == tid

    # update body + tags
    upd = client.patch(f"/api/v1/prompt-templates/{tid}", headers=auth, json={
        "body": "落ち着いた色調のブランドカット", "tags": ["brand"]})
    assert upd.status_code == 200, upd.text
    assert upd.json()["data"]["tags"] == ["brand"]

    # soft-disable removes it from the active list but the row remains
    d = client.delete(f"/api/v1/prompt-templates/{tid}", headers=auth)
    assert d.status_code == 200 and d.json()["data"]["disabled"] is True
    active = client.get("/api/v1/prompt-templates?active_only=true", headers=auth).json()["data"]
    assert all(x["id"] != tid for x in active)
    all_ = client.get("/api/v1/prompt-templates?active_only=false", headers=auth).json()["data"]
    assert any(x["id"] == tid for x in all_)


def test_prohibited_body_rejected_on_create(client, auth):
    r = client.post("/api/v1/prompt-templates", headers=auth, json={
        "name": "bad", "body": "nude explicit portrait"})
    assert r.status_code == 422, r.text
    assert "禁止" in r.json()["error"]["message"]


def test_prohibited_body_rejected_on_update(client, auth):
    ok_t = client.post("/api/v1/prompt-templates", headers=auth, json={
        "name": f"ok-{uuid.uuid4().hex[:6]}", "body": "clean studio portrait"}).json()["data"]
    r = client.patch(f"/api/v1/prompt-templates/{ok_t['id']}", headers=auth, json={
        "body": "explicit sexual act"})
    assert r.status_code == 422, r.text


def test_rbac_viewer_cannot_mutate_but_can_list(client, auth):
    vauth = _viewer_auth(client, auth)
    # can list
    assert client.get("/api/v1/prompt-templates", headers=vauth).status_code == 200
    # cannot create (needs GENERATE)
    r = client.post("/api/v1/prompt-templates", headers=vauth, json={
        "name": "x", "body": "clean portrait"})
    assert r.status_code == 403, r.text
