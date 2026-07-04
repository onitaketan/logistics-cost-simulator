"""Unit tests for the compliance engine — the safety-critical core.

Covers the MVP completion criteria in docs/01_requirements.md §4:
  * no adult verification -> cannot generate
  * expired contract -> cannot generate
  * out-of-scope category -> cannot generate
  * swimwear/underwear/bath -> requires extra approval
"""

from datetime import date

import pytest

from app.services.compliance_engine import (
    ContractInput,
    ModelInput,
    PermissionInput,
    RequirementInput,
    Status,
    evaluate,
)
from app.services.prompt_filter import screen

TODAY = date(2026, 7, 4)


def _model(**kw):
    base = dict(adult_verified=True, birth_date=date(1998, 1, 1), status="available")
    base.update(kw)
    return ModelInput(**base)


def _contract(**kw):
    base = dict(
        contract_end=date(2027, 6, 30),
        ai_generation_allowed=True,
        ai_training_allowed=True,
        post_contract_use_allowed=False,
    )
    base.update(kw)
    return ContractInput(**base)


def _perm(**kw):
    base = dict(
        media_scope={"web", "sns"},
        region_scope={"japan"},
        product_scope={"beverage", "apparel"},
        prohibited_product_scope={"finance"},
        swimwear_allowed=False,
        underwear_allowed=False,
        bath_allowed="no",
        exposure_level_max=2,
        overseas_allowed=False,
        secondary_use_allowed=False,
        video_allowed=False,
        age_appearance_change_allowed=False,
        approval_required_level="legal",
    )
    base.update(kw)
    return PermissionInput(**base)


def _req(**kw):
    base = dict(
        media={"web"},
        region={"japan"},
        product_category="beverage",
        output_type="image",
        outfit_type="normal",
        exposure_level=0,
        usage_end=date(2026, 12, 31),
    )
    base.update(kw)
    return RequirementInput(**base)


def test_happy_path_ok():
    r = evaluate(_model(), _contract(), _perm(), _req(), TODAY)
    assert r.status == Status.OK
    assert r.required_approvals == ["legal"]  # from permission base level


def test_no_adult_verification_is_prohibited():
    r = evaluate(_model(adult_verified=False), _contract(), _perm(), _req(), TODAY)
    assert r.status == Status.PROHIBITED
    assert any(v.field == "adult_verified" for v in r.violations)


def test_minor_is_prohibited():
    r = evaluate(_model(birth_date=date(2010, 1, 1)), _contract(), _perm(), _req(), TODAY)
    assert r.status == Status.PROHIBITED


def test_expired_contract_is_ng():
    r = evaluate(_model(), _contract(contract_end=date(2025, 1, 1)), _perm(), _req(), TODAY)
    assert r.status == Status.NG
    assert any(v.field == "contract_end" for v in r.violations)


def test_ai_generation_not_allowed_is_ng():
    r = evaluate(_model(), _contract(ai_generation_allowed=False), _perm(), _req(), TODAY)
    assert r.status == Status.NG


def test_media_out_of_scope_is_ng():
    r = evaluate(_model(), _contract(), _perm(), _req(media={"outdoor"}), TODAY)
    assert r.status == Status.NG
    assert any(v.field == "media" for v in r.violations)


def test_region_out_of_scope_is_ng():
    r = evaluate(_model(), _contract(), _perm(), _req(region={"eu"}), TODAY)
    assert r.status == Status.NG


def test_prohibited_category_for_model_is_ng():
    r = evaluate(_model(), _contract(), _perm(), _req(product_category="finance"), TODAY)
    assert r.status == Status.NG


def test_out_of_product_scope_is_conditional():
    r = evaluate(_model(), _contract(), _perm(), _req(product_category="travel"), TODAY)
    assert r.status == Status.CONDITIONAL


def test_swimwear_allowed_is_conditional_with_legal():
    perm = _perm(swimwear_allowed=True, exposure_level_max=3)
    req = _req(outfit_type="swimwear", exposure_level=3)
    r = evaluate(_model(), _contract(), perm, req, TODAY)
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals


def test_swimwear_not_allowed_is_ng():
    req = _req(outfit_type="swimwear", exposure_level=3)
    r = evaluate(_model(), _contract(), _perm(exposure_level_max=3), req, TODAY)
    assert r.status == Status.NG


def test_bath_requires_legal_and_agency():
    perm = _perm(bath_allowed="conditional", exposure_level_max=4)
    req = _req(outfit_type="bath", exposure_level=4)
    r = evaluate(_model(), _contract(), perm, req, TODAY)
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals and "agency" in r.required_approvals


def test_explicit_exposure_is_prohibited():
    r = evaluate(_model(), _contract(), _perm(exposure_level_max=4),
                 _req(exposure_level=5), TODAY)
    assert r.status == Status.PROHIBITED


def test_exposure_over_max_is_ng():
    r = evaluate(_model(), _contract(), _perm(exposure_level_max=1),
                 _req(exposure_level=2), TODAY)
    assert r.status == Status.NG


def test_usage_beyond_contract_is_conditional():
    r = evaluate(_model(), _contract(contract_end=date(2026, 10, 1)),
                 _perm(), _req(usage_end=date(2026, 12, 31)), TODAY)
    assert r.status == Status.CONDITIONAL


def test_prohibited_prompt_flag_forces_prohibited():
    flags = screen("beautiful nude explicit photo")
    r = evaluate(_model(), _contract(), _perm(), _req(prompt_flags=flags), TODAY)
    assert r.status == Status.PROHIBITED


def test_warning_prompt_flag_is_conditional():
    flags = screen("上品だが少しセクシーな雰囲気")
    r = evaluate(_model(), _contract(), _perm(), _req(prompt_flags=flags), TODAY)
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals


def test_result_serializes():
    d = evaluate(_model(), _contract(), _perm(), _req(), TODAY).as_dict()
    assert d["check_status"] == "ok"
    assert set(d) == {"check_status", "risk_level", "violations",
                      "required_approvals", "check_summary"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
