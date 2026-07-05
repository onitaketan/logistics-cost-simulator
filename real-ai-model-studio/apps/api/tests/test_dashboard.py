"""Dashboard expiring-contracts endpoint (P1-007) against a real Postgres.

Creates a model with a near-expiry contract and a far-expiry contract via the
API, then asserts the near one appears with the expected days_left and the far
one does not. Skipped automatically when no database is reachable (mirrors
tests/test_integration_flow.py).
"""

import uuid
from datetime import date, timedelta

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


def _make_model(client, auth) -> str:
    tag = uuid.uuid4().hex[:8]
    m = client.post("/api/v1/models", headers=auth, json={
        "stage_name": f"Model {tag}", "real_name": f"Real {tag}",
        "agency_name": "ABC", "birth_date": "1998-01-01",
    }).json()["data"]
    return m["id"]


def _make_contract(client, auth, model_id: str, end: date) -> dict:
    tag = uuid.uuid4().hex[:8]
    return client.post(f"/api/v1/models/{model_id}/contracts", headers=auth, json={
        "contract_number": f"CON-{tag}", "contract_type": "base",
        "contract_start": "2026-01-01", "contract_end": end.isoformat(),
        "ai_generation_allowed": True, "ai_training_allowed": True,
    }).json()["data"]


def test_expiring_contracts_lists_near_only(client, auth):
    today = date.today()
    mid = _make_model(client, auth)
    near = _make_contract(client, auth, mid, today + timedelta(days=10))
    far = _make_contract(client, auth, mid, today + timedelta(days=400))

    r = client.get("/api/v1/dashboard/expiring-contracts?days=30", headers=auth)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]

    by_id = {row["contract_id"]: row for row in rows}
    assert near["id"] in by_id, "near-expiry contract should be listed"
    assert far["id"] not in by_id, "far-expiry contract should not be listed"

    near_row = by_id[near["id"]]
    assert near_row["days_left"] == 10
    assert near_row["stage_name"]  # joined stage_name present
    assert near_row["model_id"] == mid
    assert near_row["contract_number"] == near["contract_number"]

    # Ordered by contract_end ascending (non-decreasing days_left).
    days = [row["days_left"] for row in rows]
    assert days == sorted(days)


def test_expiring_contracts_days_clamped(client, auth):
    # days=1000 clamps to 365; a ~400-day contract must NOT appear.
    today = date.today()
    mid = _make_model(client, auth)
    far = _make_contract(client, auth, mid, today + timedelta(days=400))

    r = client.get("/api/v1/dashboard/expiring-contracts?days=1000", headers=auth)
    assert r.status_code == 422 or r.status_code == 200
    if r.status_code == 200:
        ids = {row["contract_id"] for row in r.json()["data"]}
        assert far["id"] not in ids
