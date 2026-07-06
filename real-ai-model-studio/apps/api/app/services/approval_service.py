"""Approval completeness gate.

An output may only reach `approved` (and therefore be downloadable / deliverable)
once EVERY approval level required by its compliance check has an `approved`
record and NONE is `rejected`/`revoked`. A single sign-off is never enough when
the compliance engine demanded multiple (e.g. 水着 -> legal, 入浴 -> legal+agency).

Pure function so it is unit-testable without a DB.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalRecord:
    level: str          # internal | legal | agency | person | admin
    status: str         # approved | rejected | revoked


def evaluate_approvals(
    required: list[str], records: list[ApprovalRecord]
) -> tuple[bool, list[str]]:
    """Return (is_fully_approved, missing_levels).

    * Any rejected/revoked record at a required level blocks approval.
    * All required levels must have at least one `approved` and no active block.
    """
    required_set = set(required)
    # If the engine required nothing explicit, fall back to a single internal sign-off.
    if not required_set:
        required_set = {"internal"}

    approved: set[str] = set()
    blocked: set[str] = set()
    for r in records:
        if r.status == "approved":
            approved.add(r.level)
        elif r.status in ("rejected", "revoked"):
            blocked.add(r.level)

    # A block at any required level (even if later re-approved by a different row)
    # is resolved by presence of an approved row AND absence of an *active* block.
    # Callers pass the current effective records, so treat blocked-and-not-approved
    # as missing.
    effective_blocked = blocked - approved
    missing = sorted((required_set - approved) | (required_set & effective_blocked))
    return (len(missing) == 0, missing)


def recompute_output_status(db, output) -> tuple[str, list[str], list[str]]:
    """Recompute an output's status from ALL its approval rows and its compliance
    check's required levels, and persist the result (flush, not commit).

    Shared by the internal approval endpoint and the external portal so both
    channels drive the same completeness gate: an output reaches ``approved``
    only when every required level has an ``approved`` row and none is blocked;
    any rejected/revoked row forces ``rejected``. Returns
    ``(output_status, required, missing)``.
    """
    from sqlalchemy import select

    from app.models.generation import ComplianceCheck, Generation
    from app.models.workflow import Approval

    generation = db.get(Generation, output.generation_id)
    check = db.get(ComplianceCheck, generation.compliance_check_id) if generation else None
    required = list(check.required_approvals or []) if check else []

    records = [
        ApprovalRecord(level=a.approval_level, status=a.approval_status)
        for a in db.scalars(select(Approval).where(Approval.output_id == output.id)).all()
    ]
    fully_approved, missing = evaluate_approvals(required, records)

    if any(r.status in ("rejected", "revoked") for r in records):
        output.output_status = "rejected"
    elif fully_approved:
        output.output_status = "approved"
    # else: stays candidate/selected — not yet fully approved
    db.flush()
    return output.output_status, required, missing
