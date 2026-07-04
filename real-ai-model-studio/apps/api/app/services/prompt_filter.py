"""Prompt term screening (docs/05_compliance_rules.md §7, §8).

MVP is a dictionary matcher. Terms are seeded here but are intended to move into
a DB table (P1-001) so Legal can manage them without a deploy. Output is a set of
flags consumed by the compliance engine:
  * "prohibited:<term>"     -> engine forces Prohibited
  * "warn:<term>"           -> engine forces Conditional + legal review
  * "ng_word:<word>"        -> engine records an NG (model-specific NG rule hit)

The prohibited / warning dictionaries cover doc 05 §7 and §8. They are grouped by
theme (minors, nudity, sexual acts, humiliation, coercion, restraint, crime,
drugs, violence, discrimination, political/religious endorsement, medical
efficacy claims, false personal recommendation) so Legal can review each bucket.
Both Japanese and English surface forms are listed because prompts are authored
in either language.
"""

from __future__ import annotations

# doc 05 §7 — categories that must be blocked outright (Prohibited).
PROHIBITED_TERMS: set[str] = {
    # --- minors / minor-like sexualization ---
    "minor", "underage", "child", "children", "kid", "toddler", "infant",
    "loli", "lolita", "shota", "preteen", "teen sexual", "schoolgirl sexual",
    "school uniform sexual", "childlike", "underage looking",
    "未成年", "児童", "幼女", "幼児", "少女", "小学生", "中学生", "ロリ", "ロリータ",
    "幼く見せる", "幼く見える", "制服 露出", "制服エロ", "ランドセル",
    # --- explicit nudity ---
    "nude", "naked", "full nudity", "topless", "bottomless", "nipple", "nipples",
    "genital", "genitalia", "vagina", "penis", "exposed breasts", "bare breasts",
    "全裸", "裸", "ヌード", "乳首", "陰部", "性器", "露出狂",
    # --- sexual acts ---
    "explicit", "explicit sexual", "sexual act", "sex act", "intercourse",
    "penetration", "masturbation", "oral sex", "orgasm", "ejaculation",
    "porn", "pornographic", "hardcore", "hentai", "creampie",
    "性行為", "性的行為", "セックス", "自慰", "射精", "挿入", "絶頂", "ポルノ", "アダルト動画",
    # --- humiliation ---
    "humiliation", "humiliate", "degradation", "degrading", "debasement",
    "屈辱", "辱め", "陵辱", "凌辱", "羞恥", "奴隷",
    # --- coercion ---
    "coercion", "coerce", "non-consensual", "nonconsensual", "forced sexual",
    "rape", "molest", "assault sexual",
    "強制", "無理やり", "レイプ", "強姦", "性的暴行", "痴漢", "同意なし",
    # --- restraint in sexualized context ---
    "bondage sexual", "sexual bondage", "sexual restraint", "tied up sexual",
    "gagged sexual", "sm play",
    "拘束 性的", "緊縛", "性的拘束", "監禁 性的",
    # --- crime ---
    "crime scene", "murder", "terrorism", "human trafficking", "kidnapping",
    "counterfeit", "smuggling",
    "犯罪", "殺人", "テロ", "人身売買", "誘拐", "密輸", "偽造",
    # --- illegal drugs ---
    "cocaine", "heroin", "methamphetamine", "meth", "marijuana", "cannabis",
    "narcotics", "illegal drug", "drug injection", "overdose",
    "薬物", "覚醒剤", "麻薬", "大麻", "コカイン", "ヘロイン", "違法薬物", "注射器 薬物",
    # --- violence ---
    "violence gore", "gore", "gory", "bloodbath", "dismemberment", "mutilation",
    "torture", "beheading", "kill", "killing", "self-harm", "suicide",
    "暴力", "残虐", "流血", "拷問", "切断", "自傷", "自殺", "惨殺",
    # --- discrimination ---
    "racial slur", "ethnic slur", "hate speech", "nazi", "swastika",
    "white supremacy", "genocide",
    "差別", "ヘイト", "人種差別", "民族浄化", "ナチス", "鉤十字",
    # --- political endorsement ---
    "vote for", "political endorsement", "elect", "campaign for candidate",
    "political party support",
    "政党支持", "候補者支持", "投票を呼びかけ", "選挙応援", "この政党に投票",
    # --- religious endorsement ---
    "religious endorsement", "convert to religion", "join our religion",
    "改宗", "入信", "この宗教を信じ", "布教",
    # --- medical efficacy claims ---
    "cures cancer", "guaranteed cure", "medical efficacy", "clinically proven cure",
    "treats disease", "miracle cure",
    "がんが治る", "病気が治る", "必ず治る", "効果を保証", "医療効果", "効能を保証",
    "副作用なし", "確実に痩せる", "必ず痩せる",
    # --- false personal recommendation ---
    "fake testimonial", "false endorsement", "fabricated review",
    "本人が推薦", "本人推薦", "愛用しています と偽り", "偽の推薦", "虚偽の推薦", "実際には使っていない",
}

# doc 05 §8 — not blocked, but require warning / possible legal review (Conditional).
WARNING_TERMS: set[str] = {
    # doc 05 §8 canonical list
    "セクシー", "濡れ感", "ベッド", "密着", "透け感", "大胆", "挑発的", "悩殺",
    # additional Japanese suggestive-but-not-prohibited surface forms
    "色っぽい", "妖艶", "艶やか", "際どい", "肌見せ", "谷間", "ボディライン", "しなやか",
    "誘惑", "官能的", "セクシーポーズ", "薄着", "ランジェリー風", "寝そべり",
    # English equivalents
    "sexy", "wet look", "bed", "seductive", "provocative", "sensual", "alluring",
    "cleavage", "revealing", "suggestive", "lingerie style", "flirtatious",
}


def screen(text: str | None) -> set[str]:
    """Screen free text against the prohibited/warning dictionaries."""
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


def screen_with_model_ng(text: str | None, model_ng_words: set[str]) -> set[str]:
    """Screen text like ``screen`` and additionally flag model-specific NG words.

    ``model_ng_words`` are per-model NG terms (from the ``model_ng_rules`` table,
    e.g. words the person or agency explicitly refused). A hit yields a
    ``"ng_word:<word>"`` flag that the compliance engine records as an NG
    violation — restrictive, but not an absolute Prohibited (unless the same text
    also trips a prohibited term such as sexualized-minor, which still wins by
    status precedence).
    """
    flags = screen(text)
    if not text or not model_ng_words:
        return flags
    lowered = text.lower()
    for word in model_ng_words:
        w = (word or "").strip()
        if w and w.lower() in lowered:
            flags.add(f"ng_word:{w}")
    return flags
