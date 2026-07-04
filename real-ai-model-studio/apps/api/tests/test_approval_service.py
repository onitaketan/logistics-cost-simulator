"""Tests for the approval completeness gate."""

from app.services.approval_service import ApprovalRecord, evaluate_approvals


def test_no_required_falls_back_to_internal():
    ok, missing = evaluate_approvals([], [])
    assert ok is False and missing == ["internal"]
    ok, missing = evaluate_approvals([], [ApprovalRecord("internal", "approved")])
    assert ok is True and missing == []


def test_single_required_met():
    ok, missing = evaluate_approvals(["legal"], [ApprovalRecord("legal", "approved")])
    assert ok is True and missing == []


def test_multi_required_partial_is_not_approved():
    # 入浴: legal + agency 必須。legal だけでは不足。
    ok, missing = evaluate_approvals(
        ["legal", "agency"], [ApprovalRecord("legal", "approved")]
    )
    assert ok is False and missing == ["agency"]


def test_multi_required_all_met():
    ok, missing = evaluate_approvals(
        ["legal", "agency"],
        [ApprovalRecord("legal", "approved"), ApprovalRecord("agency", "approved")],
    )
    assert ok is True and missing == []


def test_rejection_blocks_even_if_others_approved():
    ok, missing = evaluate_approvals(
        ["legal", "agency"],
        [ApprovalRecord("legal", "approved"), ApprovalRecord("agency", "rejected")],
    )
    assert ok is False and "agency" in missing


def test_reapproval_after_block_clears_missing():
    # agency rejected then later approved -> approved wins (effective records)
    ok, missing = evaluate_approvals(
        ["legal", "agency"],
        [ApprovalRecord("legal", "approved"),
         ApprovalRecord("agency", "rejected"),
         ApprovalRecord("agency", "approved")],
    )
    assert ok is True and missing == []
