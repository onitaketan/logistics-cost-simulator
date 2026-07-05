"""Staging acceptance test for REAL image generation (end-to-end over HTTP).

Run this against a DEPLOYED, running API whose AI_ENGINE points at a real provider
(OpenAI / Replicate / an OpenAI-compatible gateway). It exercises the full path a
real generation takes and asserts the safety-critical invariants — WITHOUT needing
to know the provider's output bytes in advance:

  login -> model(adult)/contract/permission -> project/requirement -> compliance OK
  -> POST /generations -> poll to completed -> outputs stored in OUR storage
  -> approve -> signed download returns bytes whose sha256 == output.file_hash
  -> bytes are a real image (PNG/JPEG/WebP magic)

It also does a NEGATIVE check: a model with no adult verification must be blocked.

Usage (on/near the API host):
  export RAMS_API_BASE=http://localhost:8000/api/v1
  export RAMS_ADMIN_EMAIL=admin@example.com RAMS_ADMIN_PASSWORD='ChangeMe123!'
  python scripts/verify_live_generation.py

Exit code 0 = all checks passed. Non-zero = a check failed (message printed).
No secrets are read here; the provider key lives in the API process's env.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("RAMS_API_BASE", "http://localhost:8000/api/v1")
EMAIL = os.environ.get("RAMS_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("RAMS_ADMIN_PASSWORD", "ChangeMe123!")
POLL_TIMEOUT = int(os.environ.get("RAMS_POLL_TIMEOUT", "180"))

_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF", b"GIF8")


def _fail(msg: str):
    print(f"  ✗ {msg}")
    sys.exit(1)


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=60.0)
    tag = uuid.uuid4().hex[:6]

    r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        _fail(f"login failed: {r.status_code} {r.text}")
    H = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    print("  ✓ login")

    def new_model(*, verified: bool) -> str:
        mid = c.post("/models", headers=H, json={
            "stage_name": f"live{tag}{'v' if verified else 'u'}",
            "real_name": f"本名{tag}", "birth_date": "1996-05-01",
        }).json()["data"]["id"]
        if verified:
            c.post(f"/models/{mid}/adult-verification", headers=H, json={"adult_verified": True})
        ct = c.post(f"/models/{mid}/contracts", headers=H, json={
            "contract_number": f"C-{tag}-{mid[:4]}", "contract_start": "2026-01-01",
            "contract_end": "2027-12-31", "ai_generation_allowed": True,
        }).json()["data"]
        c.post(f"/models/{mid}/permissions", headers=H, json={
            "contract_id": ct["id"], "media_scope": ["web"], "region_scope": ["japan"],
            "product_scope": ["beverage"], "exposure_level_max": 2,
            "approval_required_level": "internal",
        })
        return mid

    def new_project() -> str:
        pid = c.post("/projects", headers=H, json={
            "project_name": f"live案件{tag}", "product_category": "beverage",
        }).json()["data"]["id"]
        c.post(f"/projects/{pid}/requirements", headers=H,
               json={"media": ["web"], "region": ["japan"], "exposure_level": 0})
        return pid

    # ---- NEGATIVE: unverified model must be blocked -------------------------
    mid_u = new_model(verified=False)
    pid = new_project()
    chk_u = c.post(f"/projects/{pid}/compliance-check", headers=H,
                   json={"model_id": mid_u}).json()["data"]
    if chk_u["check_status"] not in ("ng", "prohibited"):
        _fail(f"unverified model was not blocked: {chk_u['check_status']}")
    blocked = c.post("/generations", headers=H, json={
        "project_id": pid, "model_id": mid_u,
        "compliance_check_id": chk_u["compliance_check_id"],
        "prompt_text": "x", "generation_params": {"output_count": 1},
    })
    if blocked.status_code != 422:
        _fail(f"generation not blocked for unverified model: {blocked.status_code}")
    print("  ✓ unverified model blocked at compliance + generation (422)")

    # ---- HAPPY PATH: real generation --------------------------------------
    mid = new_model(verified=True)
    chk = c.post(f"/projects/{pid}/compliance-check", headers=H,
                 json={"model_id": mid, "prompt_text": "上品な広告写真"}).json()["data"]
    if chk["check_status"] != "ok":
        _fail(f"expected OK compliance, got {chk['check_status']}: {chk.get('violations')}")
    print("  ✓ compliance OK")

    g = c.post("/generations", headers=H, json={
        "project_id": pid, "model_id": mid, "compliance_check_id": chk["compliance_check_id"],
        "prompt_text": "a premium beverage on a clean studio background, product photography",
        "generation_params": {"output_count": 1, "width": 1024, "height": 1024},
    })
    if g.status_code != 200:
        _fail(f"generation request failed: {g.status_code} {g.text}")
    gid = g.json()["data"]["generation_id"]

    deadline = time.time() + POLL_TIMEOUT
    status = g.json()["data"]["status"]
    while status not in ("completed", "failed") and time.time() < deadline:
        time.sleep(2)
        status = c.get(f"/generations/{gid}", headers=H).json()["data"]["status"]
    if status != "completed":
        _fail(f"generation did not complete (status={status})")
    print(f"  ✓ generation completed (job {gid[:8]})")

    outs = c.get(f"/generations/{gid}/outputs", headers=H).json()["data"]
    if not outs:
        _fail("no outputs produced")
    o = outs[0]
    if not str(o["file_path"]).startswith(("local://", "s3://")):
        _fail(f"output not stored in our storage (provider URL leaked?): {o['file_path']}")
    print(f"  ✓ output stored in our storage: {o['file_path']}")

    # approve so download is permitted, then fetch the real bytes
    c.post(f"/outputs/{o['id']}/approvals", headers=H,
           json={"approval_level": "internal", "approval_status": "approved"})
    dl = c.get(f"/outputs/{o['id']}/download", headers=H)
    if dl.status_code != 200:
        _fail(f"download refused after approval: {dl.status_code} {dl.text}")
    url = dl.json()["data"]["download_url"]
    resp = c.get(url) if url.startswith("http") else c.get(BASE.rsplit("/api/", 1)[0] + url)
    if resp.status_code != 200:
        _fail(f"signed download fetch failed: {resp.status_code}")
    body = resp.content

    if hashlib.sha256(body).hexdigest() != o["file_hash"]:
        _fail("downloaded bytes do NOT match output.file_hash (integrity broken)")
    if not body.startswith(_IMAGE_MAGIC):
        _fail(f"downloaded bytes are not a known image format (magic={body[:8]!r})")
    print(f"  ✓ signed download OK: {len(body)} bytes, sha256==file_hash, real image ({body[:4]!r})")

    print("\nLIVE GENERATION VERIFICATION: PASS")


if __name__ == "__main__":
    main()
