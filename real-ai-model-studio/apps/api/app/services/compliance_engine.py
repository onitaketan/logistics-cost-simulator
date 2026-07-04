"""Compliance engine — the single source of truth for "may we generate this?".

Implements docs/05_compliance_rules.md. This module is PURE (no DB, no I/O) so it
can be exhaustively unit-tested and audited. It is the ONLY place that decides
generation permission; UI and DB constraints are additional layers, not the
decision-maker (see CLAUDE.md).

Design rules:
  * fail-closed: unknown / missing data resolves to the more restrictive result.
  * status precedence: prohibited > ng > conditional > ok.
  * every downgrade records a Violation with a human-readable Japanese message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum, StrEnum


class Status(StrEnum):
    OK = "ok"
    CONDITIONAL = "conditional"
    NG = "ng"
    PROHIBITED = "prohibited"


class Risk(StrEnum):
    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"
    PROHIBITED = "prohibited"


# severity ordering for "take the worst" merges
_ORDER = {Status.OK: 0, Status.CONDITIONAL: 1, Status.NG: 2, Status.PROHIBITED: 3}


class Exposure(IntEnum):
    NORMAL = 0
    LIGHT = 1
    RESORT = 2
    SWIMWEAR = 3
    UNDERWEAR_BATH = 4
    EXPLICIT = 5


# Categories that are absolutely forbidden regardless of contract (doc 05 §6).
PROHIBITED_CATEGORIES = {"adult", "成人向け", "illegal", "違法商材"}
# Categories that are never OK without legal handling (doc 05 §6).
NG_CATEGORIES = {"political", "政治", "religion", "宗教", "gambling", "ギャンブル"}
CONDITIONAL_CATEGORIES = {
    "medical", "医療", "finance", "金融", "health_food", "健康食品",
    "onsen", "温泉旅館", "swimwear", "水着", "underwear", "下着",
}


@dataclass(frozen=True)
class Violation:
    field: str
    message: str
    result: Status


@dataclass(frozen=True)
class ModelInput:
    adult_verified: bool
    birth_date: date | None
    status: str = "available"


@dataclass(frozen=True)
class ContractInput:
    contract_end: date
    ai_generation_allowed: bool
    ai_training_allowed: bool
    post_contract_use_allowed: bool = False


@dataclass(frozen=True)
class PermissionInput:
    media_scope: set[str]
    region_scope: set[str]
    product_scope: set[str]
    prohibited_product_scope: set[str]
    swimwear_allowed: bool
    underwear_allowed: bool
    bath_allowed: str  # yes | no | conditional
    exposure_level_max: int
    overseas_allowed: bool
    secondary_use_allowed: bool
    video_allowed: bool
    age_appearance_change_allowed: bool
    approval_required_level: str = "legal"


@dataclass(frozen=True)
class RequirementInput:
    media: set[str]
    region: set[str]
    product_category: str
    output_type: str  # image | video
    outfit_type: str  # normal | swimwear | underwear | bath | ...
    exposure_level: int
    usage_end: date | None
    secondary_use: bool = False
    overseas: bool = False
    training_requested: bool = False
    age_appearance_change: bool = False
    prompt_flags: set[str] = field(default_factory=set)  # detected prohibited/warning flags


@dataclass
class ComplianceResult:
    status: Status
    risk_level: Risk
    violations: list[Violation]
    required_approvals: list[str]
    summary: str

    def as_dict(self) -> dict:
        return {
            "check_status": self.status.value,
            "risk_level": self.risk_level.value,
            "violations": [
                {"field": v.field, "message": v.message, "result": v.result.value}
                for v in self.violations
            ],
            "required_approvals": self.required_approvals,
            "check_summary": self.summary,
        }


def _worst(a: Status, b: Status) -> Status:
    return a if _ORDER[a] >= _ORDER[b] else b


def evaluate(
    model: ModelInput,
    contract: ContractInput,
    permission: PermissionInput,
    requirement: RequirementInput,
    today: date,
) -> ComplianceResult:
    """Return the overall judgement. Pure function — same inputs, same output."""
    violations: list[Violation] = []
    approvals: set[str] = set()
    status = Status.OK

    def add(field_: str, msg: str, result: Status) -> None:
        nonlocal status
        violations.append(Violation(field_, msg, result))
        status = _worst(status, result)

    # ---- 1. Absolute prohibitions (cannot be overridden, even by admin) ----
    if requirement.exposure_level >= Exposure.EXPLICIT:
        add("exposure_level", "明示的性的表現は絶対禁止です。", Status.PROHIBITED)
    if requirement.product_category in PROHIBITED_CATEGORIES:
        add("product_category", "禁止カテゴリ（成人向け/違法商材等）です。", Status.PROHIBITED)
    for flag in sorted(requirement.prompt_flags):
        if flag.startswith("prohibited:"):
            add("prompt", f"禁止語句が検出されました（{flag}）。", Status.PROHIBITED)
    if not model.adult_verified:
        # doc 05 §1: adult_verified=false -> Prohibited
        add("adult_verified", "成人確認が未完了のため生成できません。", Status.PROHIBITED)
    if model.birth_date is not None and _age(model.birth_date, today) < 18:
        add("birth_date", "18歳未満は絶対禁止です。", Status.PROHIBITED)
    if requirement.age_appearance_change and not permission.age_appearance_change_allowed:
        add("age_appearance", "年齢を若く見せる指示は許諾されていません。", Status.NG)

    # short-circuit: prohibited never recovers
    if status == Status.PROHIBITED:
        return _finalize(status, violations, approvals)

    # ---- 2. Base rules (doc 05 §2) ----
    if model.birth_date is None:
        add("birth_date", "生年月日が不明のため年齢確認ができません。", Status.NG)
    if contract.contract_end < today:
        add("contract_end", "契約期間が終了しています。", Status.NG)
    if not contract.ai_generation_allowed:
        add("ai_generation_allowed", "AI生成が契約上許可されていません。", Status.NG)
    if requirement.training_requested and not contract.ai_training_allowed:
        add("ai_training_allowed", "AI学習利用が許可されていません。", Status.NG)

    missing_media = requirement.media - permission.media_scope
    if missing_media:
        add("media", f"許可されていない媒体です: {sorted(missing_media)}", Status.NG)
    missing_region = requirement.region - permission.region_scope
    if missing_region:
        add("region", f"許可されていない地域です: {sorted(missing_region)}", Status.NG)

    if requirement.overseas and not permission.overseas_allowed:
        add("overseas", "海外配信が許可されていません。", Status.NG)
    if requirement.secondary_use and not permission.secondary_use_allowed:
        add("secondary_use", "二次利用が許可されていません。", Status.NG)
    if requirement.output_type == "video" and not permission.video_allowed:
        add("output_type", "動画利用が許可されていません。", Status.NG)

    # ---- 3. Product category (doc 05 §6) ----
    if requirement.product_category in permission.prohibited_product_scope:
        add("product_category", "本モデルの禁止カテゴリに該当します。", Status.NG)
    elif requirement.product_category in NG_CATEGORIES:
        add("product_category", "政治/宗教/ギャンブル等はNGカテゴリです。", Status.NG)
    elif permission.product_scope and requirement.product_category not in permission.product_scope:
        add("product_category", "許諾カテゴリ外のため追加確認が必要です。", Status.CONDITIONAL)
    elif requirement.product_category in CONDITIONAL_CATEGORIES:
        add("product_category", "高リスクカテゴリのため法務確認が必要です。", Status.CONDITIONAL)
        approvals.add("legal")

    # ---- 4. Usage period (doc 05 §2 no.10) ----
    if requirement.usage_end and requirement.usage_end > contract.contract_end:
        add("usage_end", "利用終了日が契約終了日を超えています。", Status.CONDITIONAL)
        approvals.add("legal")

    # ---- 5. Exposure & outfit (doc 05 §3, §4) ----
    _evaluate_exposure(requirement, permission, add, approvals)

    # ---- 6. Warning terms in prompt (doc 05 §8) — never auto-block, flag review ----
    warn_flags = {f for f in requirement.prompt_flags if f.startswith("warn:")}
    if warn_flags:
        add("prompt", f"要注意語句が含まれます（法務確認推奨）: {sorted(warn_flags)}", Status.CONDITIONAL)
        approvals.add("legal")

    # ---- 7. Base approval from permission setting ----
    if status in (Status.OK, Status.CONDITIONAL):
        approvals.add(_base_approval(permission.approval_required_level))

    return _finalize(status, violations, approvals)


def _evaluate_exposure(req, perm, add, approvals) -> None:
    level = req.exposure_level
    if level > perm.exposure_level_max:
        add("exposure_level",
            f"露出レベル{level}は許諾上限{perm.exposure_level_max}を超えています。", Status.NG)

    outfit = req.outfit_type
    if outfit == "swimwear" or level == Exposure.SWIMWEAR:
        if not perm.swimwear_allowed:
            add("swimwear", "水着表現は許諾されていません。", Status.NG)
        else:
            add("swimwear", "水着表現は条件付き。法務承認が必要です。", Status.CONDITIONAL)
            approvals.add("legal")
    if outfit == "underwear" or level == Exposure.UNDERWEAR_BATH:
        if outfit == "underwear" and not perm.underwear_allowed:
            add("underwear", "下着表現は許諾されていません。", Status.NG)
        elif outfit == "underwear":
            add("underwear", "下着表現は条件付き。法務+本人/事務所承認が必要です。", Status.CONDITIONAL)
            approvals.update({"legal", "agency"})
    if outfit == "bath":
        if perm.bath_allowed == "no":
            add("bath", "入浴表現は許諾されていません。", Status.NG)
        else:  # yes or conditional -> still requires approval
            add("bath", "入浴表現は条件付き。法務+本人/事務所承認が必要です。", Status.CONDITIONAL)
            approvals.update({"legal", "agency"})


def _base_approval(level: str) -> str:
    return {"internal": "internal", "legal": "legal",
            "agency": "agency", "person": "person"}.get(level, "legal")


def _finalize(status: Status, violations: list[Violation], approvals: set[str]) -> ComplianceResult:
    risk = _risk_for(status, violations)
    order = ["internal", "legal", "agency", "person", "admin"]
    required = [a for a in order if a in approvals]
    summary = _summary(status, required)
    return ComplianceResult(status, risk, violations, required, summary)


def _risk_for(status: Status, violations: list[Violation]) -> Risk:
    if status == Status.PROHIBITED:
        return Risk.PROHIBITED
    if status == Status.NG:
        return Risk.HIGH
    if status == Status.CONDITIONAL:
        return Risk.MIDDLE
    return Risk.LOW


def _summary(status: Status, approvals: list[str]) -> str:
    if status == Status.PROHIBITED:
        return "絶対禁止に該当するため生成できません（管理者でも解除不可）。"
    if status == Status.NG:
        return "許諾範囲外のため生成できません。案件条件を見直してください。"
    if status == Status.CONDITIONAL:
        who = "・".join(approvals) if approvals else "追加"
        return f"生成は可能ですが、{who} の承認が必要です。"
    return "許諾範囲内です。通常フローで生成できます。"


def _age(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
