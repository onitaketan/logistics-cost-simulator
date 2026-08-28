"""Reference-photo-driven generation (img2img basis) — verification.

Consent boundary (CLAUDE.md #6/#8): a generation may reference ONLY the selected
model's own, consented, generation-eligible assets. Covers:
  * request-time refusal: foreign-model asset / unconsented / review_only・ng;
  * happy path stores reference_asset_ids in generation_params;
  * worker loader re-validates and returns base64 of the REAL stored bytes;
  * self_hosted adapter switches to /sdapi/v1/img2img when refs are present;
  * asset preview endpoint requires the GENERATE capability.

DB-backed parts skip without Postgres; adapter test is pure MockTransport.
"""

import asyncio
import base64
import io
import uuid

import httpx
import pytest
from sqlalchemy import text

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_engines.self_hosted_adapter import SelfHostedAdapter  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ChangeMe123!"
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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
def auth(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _upload_asset(client, auth, mid, *, usage_type="reference", consent=True,
                  asset_type="face") -> str:
    r = client.post(f"/api/v1/models/{mid}/assets", headers=auth,
                    files={"file": ("ref.png", io.BytesIO(PNG_1PX), "image/png")},
                    data={"asset_type": asset_type, "usage_type": usage_type,
                          "consent_confirmed": "true" if consent else "false"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _chain(client, auth):
    """Compliant model+project chain -> (pid, mid, check_id)."""
    tag = uuid.uuid4().hex[:8]
    mid = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"M{tag}", "real_name": f"R{tag}", "birth_date": "1996-01-01",
    }).json()["data"]["id"]
    client.post(f"/api/v1/models/{mid}/adult-verification", headers=auth,
                json={"adult_verified": True})
    c = client.post(f"/api/v1/models/{mid}/contracts", headers=auth, json={
        "contract_number": f"C{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": "2027-12-31",
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]
    client.post(f"/api/v1/models/{mid}/permissions", headers=auth, json={
        "contract_id": c["id"], "media_scope": ["web"], "region_scope": ["japan"],
        "product_scope": ["beverage"], "exposure_level_max": 2,
        "approval_required_level": "internal"})
    pid = client.post("/api/v1/projects", headers=auth, json={
        "project_name": f"ref {tag}", "product_category": "beverage"}).json()["data"]["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", headers=auth, json={
        "media": ["web"], "region": ["japan"], "output_type": "image",
        "outfit_type": "normal", "exposure_level": 0})
    client.post(f"/api/v1/projects/{pid}/models", headers=auth,
                json={"model_id": mid, "usage_role": "main"})
    chk = client.post(f"/api/v1/projects/{pid}/compliance-check", headers=auth,
                      json={"model_id": mid, "prompt_text": "上品な背景"}).json()["data"]
    return pid, mid, chk["compliance_check_id"]


def _gen_payload(pid, mid, check_id, refs):
    return {
        "project_id": pid, "model_id": mid, "compliance_check_id": check_id,
        "prompt_text": "上品な背景で商品を持つ", "reference_asset_ids": refs,
        "generation_params": {"output_count": 1, "width": 512, "height": 512},
    }


@db_only
def test_reference_must_be_own_consented_eligible(client, auth):
    pid, mid, check_id = _chain(client, auth)
    _pid2, mid2, _chk2 = _chain(client, auth)  # a DIFFERENT model

    # another model's photo -> refused (consent boundary)
    foreign = _upload_asset(client, auth, mid2)
    r = client.post("/api/v1/generations", headers=auth,
                    json=_gen_payload(pid, mid, check_id, [foreign]))
    assert r.status_code == 422, r.text

    # unconsented -> refused
    uncons = _upload_asset(client, auth, mid, consent=False)
    r = client.post("/api/v1/generations", headers=auth,
                    json=_gen_payload(pid, mid, check_id, [uncons]))
    assert r.status_code == 422, r.text

    # review_only usage -> refused
    review_only = _upload_asset(client, auth, mid, usage_type="review_only")
    r = client.post("/api/v1/generations", headers=auth,
                    json=_gen_payload(pid, mid, check_id, [review_only]))
    assert r.status_code == 422, r.text


@db_only
def test_happy_path_stores_reference_ids_and_worker_loads_bytes(client, auth):
    pid, mid, check_id = _chain(client, auth)
    ref = _upload_asset(client, auth, mid)

    r = client.post("/api/v1/generations", headers=auth,
                    json=_gen_payload(pid, mid, check_id, [ref]))
    assert r.status_code == 200, r.text
    gid = r.json()["data"]["generation_id"]

    with engine.connect() as c:
        params = c.execute(text(
            "select generation_params from generations where id=:i"), {"i": gid}).scalar()
    assert params.get("reference_asset_ids") == [ref]

    # worker loader returns the REAL stored bytes, base64-encoded
    from app.db.session import SessionLocal
    from app.models.generation import Generation
    from app.workers.generation_worker import _load_reference_images_b64

    db = SessionLocal()
    try:
        gen_row = db.get(Generation, gid)
        loaded = _load_reference_images_b64(db, gen_row)
    finally:
        db.close()
    assert len(loaded) == 1
    assert base64.b64decode(loaded[0]) == PNG_1PX


@db_only
def test_asset_preview_requires_generate_capability(client, auth):
    _pid, mid, _chk = _chain(client, auth)
    ref = _upload_asset(client, auth, mid)

    # viewer (no GENERATE) -> 403
    tag = uuid.uuid4().hex[:6]
    client.post("/api/v1/users", headers=auth, json={
        "name": f"v{tag}", "email": f"v{tag}@example.com",
        "password": "ViewerPass123", "role": "viewer"})
    vtok = client.post("/api/v1/auth/login", json={
        "email": f"v{tag}@example.com", "password": "ViewerPass123"}).json()["data"]["access_token"]
    assert client.get(f"/api/v1/assets/{ref}/preview",
                      headers={"Authorization": f"Bearer {vtok}"}).status_code == 403
    # admin -> signed URL
    ok_ = client.get(f"/api/v1/assets/{ref}/preview", headers=auth)
    assert ok_.status_code == 200 and ok_.json()["data"]["preview_url"]


# ---- adapter: refs flip the call to img2img (pure, no DB) ----
def test_self_hosted_uses_img2img_when_refs_present():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={
            "images": [base64.b64encode(PNG_1PX).decode()], "info": "{\"seed\": 7}"})

    adapter = SelfHostedAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://127.0.0.1:7860")
    ref_b64 = base64.b64encode(PNG_1PX).decode()
    asyncio.run(adapter.generate_image("portrait", {
        "output_count": 1, "width": 512, "height": 512,
        "reference_images_b64": [ref_b64]}))
    assert seen["path"] == "/sdapi/v1/img2img"
    assert seen["payload"]["init_images"] == [ref_b64]
    assert 0 < seen["payload"]["denoising_strength"] <= 1
