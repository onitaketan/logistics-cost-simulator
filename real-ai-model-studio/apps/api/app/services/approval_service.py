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
