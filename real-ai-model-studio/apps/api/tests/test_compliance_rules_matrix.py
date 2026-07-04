"""Expanded compliance rule matrix (docs/05_compliance_rules.md).

Complements tests/test_compliance_engine.py with:
  * product category matrix (§6)
  * exposure boundaries 0..5 (§3, §4)
  * swimwear / underwear / bath approval requirements (§3, §9)
  * media / region scope combinations (§2)
  * overseas / secondary_use / video / usage-beyond-contract (§2)
  * prompt prohibited/warning terms (§7, §8)
  * NEW: model-specific NG rules (model_ng_rules) via model_ng_hits + prompt_filter

All engine tests are pure (no DB). TODAY is fixed so results are deterministic.
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
from app.services.prompt_filter import (
    PROHIBITED_TERMS,
    WARNING_TERMS,
    screen,
    screen_with_model_ng,
)

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
        product_scope={"beverage", "apparel", "travel"},
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


def _run(**overrides):
    """Run with an open permission (broad scope) unless overridden, so a single
    varied field drives the outcome."""
    model = overrides.pop("model", _model())
    contract = overrides.pop("contract", _contract())
    perm = overrides.pop("perm", None)
    req = overrides.pop("req", None)
    return evaluate(model, contract, perm or _perm(), req or _req(**overrides), TODAY)


# ---------------------------------------------------------------------------
# Product category matrix (docs 05 §6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", ["beverage", "apparel", "travel"])
def test_in_scope_categories_are_ok(category):
    perm = _perm(product_scope={"beverage", "apparel", "travel"})
    assert _run(perm=perm, req=_req(product_category=category)).status == Status.OK


@pytest.mark.parametrize("category", ["medical", "医療", "finance", "金融"])
def test_medical_finance_are_conditional_when_scope_open(category):
    # product_scope empty means "no explicit allow-list" -> fall through to
    # category-level handling; medical/finance are high-risk -> Conditional.
    perm = _perm(product_scope=set(), prohibited_product_scope=set())
    r = _run(perm=perm, req=_req(product_category=category))
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals


@pytest.mark.parametrize("category", ["political", "政治", "religion", "宗教",
                                      "gambling", "ギャンブル"])
def test_political_religion_gambling_are_ng(category):
    perm = _perm(product_scope=set(), prohibited_product_scope=set())
    assert _run(perm=perm, req=_req(product_category=category)).status == Status.NG


@pytest.mark.parametrize("category", ["adult", "成人向け", "illegal", "違法商材"])
def test_adult_illegal_are_prohibited(category):
    perm = _perm(product_scope=set(), prohibited_product_scope=set())
    r = _run(perm=perm, req=_req(product_category=category))
    assert r.status == Status.PROHIBITED


def test_model_prohibited_scope_beats_open_list():
    r = _run(req=_req(product_category="finance"))  # finance in prohibited scope
    assert r.status == Status.NG


# ---------------------------------------------------------------------------
# Exposure boundaries 0..5 (docs 05 §3, §4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level,expected", [
    (0, Status.OK),
    (1, Status.OK),
    (2, Status.OK),
    (3, Status.NG),          # exceeds max=2
    (4, Status.NG),          # exceeds max=2
    (5, Status.PROHIBITED),  # explicit -> absolute
])
def test_exposure_levels_against_max_2(level, expected):
    assert _run(req=_req(exposure_level=level)).status == expected


def test_exposure_at_max_is_ok():
    perm = _perm(exposure_level_max=2)
    assert _run(perm=perm, req=_req(exposure_level=2)).status == Status.OK


def test_exposure_explicit_prohibited_even_if_max_high():
    perm = _perm(exposure_level_max=4)
    assert _run(perm=perm, req=_req(exposure_level=5)).status == Status.PROHIBITED


# ---------------------------------------------------------------------------
# Swimwear / underwear / bath approvals (docs 05 §3, §9)
# ---------------------------------------------------------------------------

def test_swimwear_allowed_requires_legal():
    perm = _perm(swimwear_allowed=True, exposure_level_max=3)
    r = _run(perm=perm, req=_req(outfit_type="swimwear", exposure_level=3))
    assert r.status == Status.CONDITIONAL and "legal" in r.required_approvals


def test_swimwear_denied_is_ng():
    perm = _perm(swimwear_allowed=False, exposure_level_max=3)
    r = _run(perm=perm, req=_req(outfit_type="swimwear", exposure_level=3))
    assert r.status == Status.NG


def test_underwear_allowed_requires_legal_and_agency():
    perm = _perm(underwear_allowed=True, exposure_level_max=4)
    r = _run(perm=perm, req=_req(outfit_type="underwear", exposure_level=4))
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals and "agency" in r.required_approvals


def test_underwear_denied_is_ng():
    perm = _perm(underwear_allowed=False, exposure_level_max=4)
    r = _run(perm=perm, req=_req(outfit_type="underwear", exposure_level=4))
    assert r.status == Status.NG


def test_bath_no_is_ng():
    perm = _perm(bath_allowed="no", exposure_level_max=4)
    r = _run(perm=perm, req=_req(outfit_type="bath", exposure_level=4))
    assert r.status == Status.NG


@pytest.mark.parametrize("bath", ["yes", "conditional"])
def test_bath_yes_conditional_requires_legal_agency(bath):
    perm = _perm(bath_allowed=bath, exposure_level_max=4)
    r = _run(perm=perm, req=_req(outfit_type="bath", exposure_level=4))
    assert r.status == Status.CONDITIONAL
    assert "legal" in r.required_approvals and "agency" in r.required_approvals


# ---------------------------------------------------------------------------
# Media / region scope combinations (docs 05 §2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("media,expected", [
    ({"web"}, Status.OK),
    ({"sns"}, Status.OK),
    ({"web", "sns"}, Status.OK),
    ({"outdoor"}, Status.NG),
    ({"web", "outdoor"}, Status.NG),  # partial out-of-scope still NG
])
def test_media_scope(media, expected):
    assert _run(req=_req(media=media)).status == expected


@pytest.mark.parametrize("region,expected", [
    ({"japan"}, Status.OK),
    ({"asia"}, Status.NG),
    ({"japan", "eu"}, Status.NG),
])
def test_region_scope(region, expected):
    perm = _perm(region_scope={"japan"})
    assert _run(perm=perm, req=_req(region=region)).status == expected


# ---------------------------------------------------------------------------
# Overseas / secondary_use / video / usage beyond contract (docs 05 §2)
# ---------------------------------------------------------------------------

def test_overseas_not_allowed_is_ng():
    assert _run(req=_req(overseas=True)).status == Status.NG


def test_overseas_allowed_is_ok():
    perm = _perm(overseas_allowed=True)
    assert _run(perm=perm, req=_req(overseas=True)).status == Status.OK


def test_secondary_use_not_allowed_is_ng():
    assert _run(req=_req(secondary_use=True)).status == Status.NG


def test_secondary_use_allowed_is_ok():
    perm = _perm(secondary_use_allowed=True)
    assert _run(perm=perm, req=_req(secondary_use=True)).status == Status.OK


def test_video_not_allowed_is_ng():
    assert _run(req=_req(output_type="video")).status == Status.NG


def test_video_allowed_is_ok():
    perm = _perm(video_allowed=True)
    assert _run(perm=perm, req=_req(output_type="video")).status == Status.OK


def test_usage_beyond_contract_is_conditional():
    r = _run(contract=_contract(contract_end=date(2026, 10, 1)),
             req=_req(usage_end=date(2026, 12, 31)))
    assert r.status == Status.CONDITIONAL and "legal" in r.required_approvals


def test_training_requested_without_permission_is_ng():
    r = _run(contract=_contract(ai_training_allowed=False),
             req=_req(training_requested=True))
    assert r.status == Status.NG


def test_age_appearance_change_without_permission_is_ng():
    assert _run(req=_req(age_appearance_change=True)).status == Status.NG


# ---------------------------------------------------------------------------
# Prompt prohibited / warning terms (docs 05 §7, §8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "explicit nude photo",
    "全裸で撮影",
    "未成年に見える演出",
    "性行為を示唆",
    "屈辱的なポーズ",
    "薬物を使用",
    "暴力的で残虐",
    "この政党に投票してください",
    "がんが治ると訴求",
])
def test_prohibited_prompts_force_prohibited(text):
    flags = screen(text)
    assert any(f.startswith("prohibited:") for f in flags), flags
    assert _run(req=_req(prompt_flags=flags)).status == Status.PROHIBITED


@pytest.mark.parametrize("text", [
    "少しセクシーな雰囲気",
    "濡れ感のある髪",
    "ベッドの上でリラックス",
    "大胆な構図",
    "provocative pose",
])
def test_warning_prompts_are_conditional(text):
    flags = screen(text)
    assert any(f.startswith("warn:") for f in flags), flags
    r = _run(req=_req(prompt_flags=flags))
    assert r.status == Status.CONDITIONAL and "legal" in r.required_approvals


def test_clean_prompt_has_no_flags():
    assert screen("上品な宇宙背景で商品を持つ爽やかな広告") == set()


def test_prohibited_beats_warning_in_same_prompt():
    flags = screen("セクシーで全裸の演出")  # warn:セクシー + prohibited:全裸
    r = _run(req=_req(prompt_flags=flags))
    assert r.status == Status.PROHIBITED


def test_dictionaries_meaningfully_expanded():
    # guardrail: keep the coverage from regressing to the tiny MVP list.
    assert len(PROHIBITED_TERMS) >= 80
    assert len(WARNING_TERMS) >= 20


# ---------------------------------------------------------------------------
# NEW: model-specific NG rules (model_ng_rules)
# ---------------------------------------------------------------------------

def test_screen_with_model_ng_flags_model_word():
    flags = screen_with_model_ng("大きなタトゥーを見せる", {"タトゥー"})
    assert "ng_word:タトゥー" in flags


def test_screen_with_model_ng_no_words_matches_base_screen():
    assert screen_with_model_ng("上品な広告", set()) == screen("上品な広告")


def test_screen_with_model_ng_still_catches_prohibited():
    flags = screen_with_model_ng("全裸のタトゥー", {"タトゥー"})
    assert "ng_word:タトゥー" in flags
    assert any(f.startswith("prohibited:") for f in flags)


def test_model_ng_hit_is_ng():
    r = _run(req=_req(model_ng_hits={"ng_pose:土下座"}))
    assert r.status == Status.NG
    assert any(v.field == "model_ng" for v in r.violations)


def test_model_ng_message_is_japanese():
    r = _run(req=_req(model_ng_hits={"ng_word:タトゥー"}))
    v = next(v for v in r.violations if v.field == "model_ng")
    assert "モデル固有のNG" in v.message


def test_no_model_ng_hits_is_backward_compatible():
    # default empty set -> no change to a clean OK case
    assert _run(req=_req()).status == Status.OK


def test_model_ng_does_not_downgrade_below_prohibited():
    # if the case is already prohibited, an NG hit must not "improve" it
    flags = screen("全裸")
    r = _run(req=_req(prompt_flags=flags, model_ng_hits={"ng_word:タトゥー"}))
    assert r.status == Status.PROHIBITED


def test_model_ng_word_end_to_end_from_prompt():
    # simulate the router: screen prompt with a model's NG word, split flags,
    # feed both channels to the engine.
    all_flags = screen_with_model_ng("笑顔でタトゥーを強調", {"タトゥー"})
    prompt_flags = {f for f in all_flags if not f.startswith("ng_word:")}
    ng_hits = {f for f in all_flags if f.startswith("ng_word:")}
    r = _run(req=_req(prompt_flags=prompt_flags, model_ng_hits=ng_hits))
    assert r.status == Status.NG


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
