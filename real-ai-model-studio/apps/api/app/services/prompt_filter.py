"""Prompt term screening (docs/05_compliance_rules.md §7, §8).

MVP is a dictionary matcher. Terms are seeded here but are intended to move into
a DB table (P1-001) so Legal can manage them without a deploy. Output is a set of
flags consumed by the compliance engine:
  * "prohibited:<term>"  -> engine forces Prohibited
  * "warn:<term>"        -> engine forces Conditional + legal review
"""

from __future__ import annotations

# doc 05 §7 — categories that must be blocked outright.
PROHIBITED_TERMS: set[str] = {
    # English
    "minor", "underage", "child", "loli", "schoolgirl sexual", "nude", "naked",
    "explicit", "sexual act", "intercourse", "humiliation", "coercion", "rape",
    "bondage sexual", "crime", "cocaine", "heroin", "violence gore", "kill",
    # Japanese
    "未成年", "児童", "全裸", "性行為", "屈辱", "強制", "拘束", "薬物", "覚醒剤",
}

# doc 05 §8 — not blocked, but require warning / possible legal review.
WARNING_TERMS: set[str] = {
    "セクシー", "濡れ感", "ベッド", "密着", "透け感", "大胆", "挑発的", "悩殺",
    "sexy", "wet look", "bed", "seductive", "provocative",
}


def screen(text: str | None) -> set[str]:
    if not text:
        return set()
    lowered = text.lower()
    flags: set[str] = set()
    for term in PROHIBITED_TERMS:
        if term.lower() in lowered:
            flags.add(f"prohibited:{term}")
    for term in WARNING_TERMS:
        if term.lower() in lowered:
            flags.add(f"warn:{term}")
    return flags
