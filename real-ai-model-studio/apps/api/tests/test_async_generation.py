"""Unit tests for the THIRD compliance checkpoint: revalidate_before_run.

The worker must NOT trust the enqueue-time gate — time passes between enqueue
and execution, so it re-reads compliance state from the DB at run time. These
tests exercise that function directly against a real Postgres:

  (a) passes for an ok check + valid contract;
  (b) blocks when the check is flipped to ng after enqueue;
  (c) blocks when the linked contract has expired.

Requires DATABASE_URL pointing at a Postgres with the schema + seed applied.
Skipped automatically when no database is reachable (mirrors
tests/test_integration_flow.py).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.generation import ComplianceCheck, Generation  # noqa: E402
from app.models.model import Model, ModelContract  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.generation_service import GenerationBlocked, revalidate_before_run  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="no database available")


def _seed(db, *, check_status: str, contract_end: date):
    """Insert project + model + contract + ok/conditional check + queued generation.

    Returns the generation id. The contract id is recorded on the check's
    matched_permissions so revalidate resolves the same contract the check used.
    """
    tag = uuid.uuid4().hex[:8]

    project = Project(project_name=f"revalidate-{tag}")
    # adult_verified stays False: revalidate_before_run inspects the compliance
    # check + contract, not the model flag, and True would need verification evidence.
    model = Model(stage_name=f"m-{tag}", real_name=f"r-{tag}")
    db.add_all([project, model])
    db.flush()

    contract = ModelContract(
        model_id=model.id,
        contract_number=f"CON-{tag}",
        contract_type="base",
        contract_start=date.today() - timedelta(days=30),
        contract_end=contract_end,
        ai_generation_allowed=True,
        ai_training_allowed=True,
    )
    db.add(contract)
    db.flush()

    check = ComplianceCheck(
        project_id=project.id,
        model_id=model.id,
        check_status=check_status,
        matched_permissions={"contract_id": str(contract.id)},
    )
    db.add(check)
    db.flush()

    generation = Generation(
        project_id=project.id,
        model_id=model.id,
        compliance_check_id=check.id,
        prompt_text="x",
        generation_params={"output_count": 1},
        status="queued",
    )
    db.add(generation)
    db.flush()
    return generation.id, check.id


def test_revalidate_passes_for_ok_check_and_valid_contract():
    db = SessionLocal()
    try:
        gen_id, _ = _seed(db, check_status="ok", contract_end=date.today() + timedelta(days=365))
        db.commit()
        # Should not raise.
        assert revalidate_before_run(db, gen_id) is None
    finally:
        db.rollback()
        db.close()


def test_revalidate_blocks_when_check_flipped_to_ng():
    db = SessionLocal()
    try:
        gen_id, check_id = _seed(
            db, check_status="conditional", contract_end=date.today() + timedelta(days=365)
        )
        db.commit()

        # Simulate the check being downgraded after the job was enqueued. The
        # generations gate trigger only fires on the generations table, so
        # flipping the check row itself is allowed.
        db.execute(
            text("UPDATE compliance_checks SET check_status = 'ng' WHERE id = :id"),
            {"id": str(check_id)},
        )
        db.commit()

        with pytest.raises(GenerationBlocked):
            revalidate_before_run(db, gen_id)
    finally:
        db.rollback()
        db.close()


def test_revalidate_blocks_when_contract_expired():
    db = SessionLocal()
    try:
        # Check is ok (so the generation row inserts past the DB trigger), but the
        # linked contract already ended -> revalidate must refuse.
        gen_id, _ = _seed(db, check_status="ok", contract_end=date.today() - timedelta(days=1))
        db.commit()

        with pytest.raises(GenerationBlocked):
            revalidate_before_run(db, gen_id)
    finally:
        db.rollback()
        db.close()
