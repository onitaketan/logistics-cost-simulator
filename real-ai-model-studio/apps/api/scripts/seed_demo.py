"""Idempotent DEMO dataset seeder — realistic trial data (仮テスト用).

Creates several models with contracts/permissions/NG-rules and a handful of
projects+requirements that deliberately span all four compliance outcomes
(OK / Conditional / NG / Prohibited) when checked via the compliance engine.

Usage:
    psql "$DATABASE_URL" -f migrations/0001_init.sql   # schema first
    python scripts/seed.py                             # base seed (admin, engine, scopes)
    python scripts/seed_demo.py                        # then this demo data

Idempotent: guarded by stage_name, so re-running does not duplicate rows.
Nothing here is destructive.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.model import Model, ModelContract, ModelPermission
from app.models.project import Project, ProjectModel, ProjectRequirement
from app.models.user import User

# Every demo model's stage_name starts with this so the seed is easy to detect
# (and easy to clean up manually if needed).
DEMO_PREFIX = "デモ"


def _admin_id(db) -> object | None:
    user = db.query(User).filter(User.role == "admin").first()
    return user.id if user else None


def _add_model(db, *, stage_name, real_name, adult_verified, birth_date,
               agency_name="デモ事務所", status="available"):
    verified_at = date(2025, 1, 1) if adult_verified else None
    m = Model(
        stage_name=stage_name, real_name=real_name, agency_name=agency_name,
        agency_contact_name="担当A", agency_contact_email="agency@example.com",
        birth_date=birth_date, adult_verified=adult_verified,
        adult_verified_at=verified_at, status=status,
        notes="demo seed",
    )
    db.add(m)
    db.flush()
    return m


def _add_contract(db, model, *, contract_end, ai_generation=True, ai_training=True,
                  contract_start=date(2025, 1, 1), created_by=None):
    c = ModelContract(
        model_id=model.id, contract_number=f"DEMO-{model.stage_name[-4:]}",
        contract_type="base", contract_start=contract_start, contract_end=contract_end,
        renewal_type="negotiation", ai_generation_allowed=ai_generation,
        ai_training_allowed=ai_training, post_contract_use_allowed=False,
        created_by=created_by,
    )
    db.add(c)
    db.flush()
    return c


def _add_permission(db, model, contract, **kw):
    base = dict(
        media_scope=["web", "sns", "ec", "print"],
        region_scope=["japan", "asia"],
        product_scope=["beverage", "food", "apparel", "travel", "beauty"],
        prohibited_product_scope=["finance", "medical"],
        swimwear_allowed=False, underwear_allowed=False, bath_allowed="no",
        exposure_level_max=2, age_appearance_change_allowed=False,
        video_allowed=False, secondary_use_allowed=False, overseas_allowed=False,
        approval_required_level="internal",
    )
    base.update(kw)
    p = ModelPermission(model_id=model.id, contract_id=contract.id, **base)
    db.add(p)
    db.flush()
    return p


def _add_ng_rule(db, model, rule_type, value, note=""):
    db.execute(
        text("""INSERT INTO model_ng_rules (model_id, rule_type, value, note)
                VALUES (:m, :t, :v, :n)"""),
        {"m": str(model.id), "t": rule_type, "v": value, "n": note},
    )


def _add_project(db, *, name, product_category, owner_id, req, models):
    p = Project(
        project_name=name, client_name="デモクライアント", brand_name="デモブランド",
        product_name=name, product_category=product_category, owner_user_id=owner_id,
        project_status="draft", deadline=date(2026, 12, 31),
    )
    db.add(p)
    db.flush()
    reqbase = dict(
        media=["web"], region=["japan"], usage_start=date(2026, 9, 1),
        usage_end=date(2026, 12, 31), output_type="image", outfit_type="normal",
        exposure_level=0,
    )
    reqbase.update(req)
    db.add(ProjectRequirement(project_id=p.id, **reqbase))
    for m in models:
        db.add(ProjectModel(project_id=p.id, model_id=m.id, usage_role="main"))
    db.flush()
    return p


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Model).filter(
            Model.stage_name.like(f"{DEMO_PREFIX}%")
        ).first()
        if existing:
            print("demo data already present — nothing to do (idempotent).")
            return

        admin_id = _admin_id(db)

        # ---- Models -------------------------------------------------------
        # 1) fully verified, broad permissions
        hanako = _add_model(db, stage_name=f"{DEMO_PREFIX} 花子", real_name="山田花子",
                            adult_verified=True, birth_date=date(1995, 4, 1))
        c_h = _add_contract(db, hanako, contract_end=date(2027, 12, 31), created_by=admin_id)
        _add_permission(db, hanako, c_h)
        # model-specific NG rules (person/agency explicit refusals)
        _add_ng_rule(db, hanako, "ng_word", "タトゥー", "本人がタトゥー訴求を拒否")
        _add_ng_rule(db, hanako, "ng_pose", "土下座", "尊厳配慮のため土下座ポーズ禁止")
        _add_ng_rule(db, hanako, "ng_product", "たばこ", "たばこ商材は本人NG")

        # 2) swimwear allowed (conditional), higher exposure ceiling
        mizuki = _add_model(db, stage_name=f"{DEMO_PREFIX} みずき", real_name="佐藤みずき",
                            adult_verified=True, birth_date=date(1997, 8, 20))
        c_m = _add_contract(db, mizuki, contract_end=date(2027, 12, 31), created_by=admin_id)
        _add_permission(db, mizuki, c_m,
                        product_scope=["beverage", "apparel", "swimwear", "travel"],
                        swimwear_allowed=True, exposure_level_max=3,
                        approval_required_level="legal")

        # 3) unverified (adult_verified=false) -> generation prohibited
        miku = _add_model(db, stage_name=f"{DEMO_PREFIX} 未確認みく", real_name="鈴木みく",
                         adult_verified=False, birth_date=date(1999, 2, 2))
        c_k = _add_contract(db, miku, contract_end=date(2027, 12, 31), created_by=admin_id)
        _add_permission(db, miku, c_k)

        # 4) verified but contract expired -> NG
        rei = _add_model(db, stage_name=f"{DEMO_PREFIX} 期限切れ玲", real_name="高橋玲",
                        adult_verified=True, birth_date=date(1994, 11, 11), status="expired")
        c_r = _add_contract(db, rei, contract_start=date(2023, 1, 1),
                            contract_end=date(2024, 12, 31), created_by=admin_id)
        _add_permission(db, rei, c_r)

        # ---- Projects (span all four outcomes) ----------------------------
        projects: list[tuple[str, str]] = []

        p_ok = _add_project(
            db, name=f"{DEMO_PREFIX} 宇宙飲料 通常広告", product_category="beverage",
            owner_id=admin_id, models=[hanako],
            req=dict(exposure_level=0, outfit_type="normal",
                     pose_description="上品に商品を持つ"),
        )
        projects.append((p_ok.project_name, "OK (花子・飲料・通常広告)"))

        p_cond = _add_project(
            db, name=f"{DEMO_PREFIX} リゾート水着 キャンペーン", product_category="swimwear",
            owner_id=admin_id, models=[mizuki],
            req=dict(exposure_level=3, outfit_type="swimwear", scene_type="resort",
                     pose_description="ビーチで立つ"),
        )
        projects.append((p_cond.project_name, "Conditional (みずき・水着許諾→法務承認要)"))

        p_ng = _add_project(
            db, name=f"{DEMO_PREFIX} 金融サービス 広告", product_category="finance",
            owner_id=admin_id, models=[hanako],
            req=dict(exposure_level=0, outfit_type="normal"),
        )
        projects.append((p_ng.project_name, "NG (花子の禁止カテゴリ=金融)"))

        p_prohibited = _add_project(
            db, name=f"{DEMO_PREFIX} 成人向け 商材", product_category="adult",
            owner_id=admin_id, models=[hanako],
            req=dict(exposure_level=0, outfit_type="normal"),
        )
        projects.append((p_prohibited.project_name, "Prohibited (成人向けカテゴリ=絶対禁止)"))

        p_model_ng = _add_project(
            db, name=f"{DEMO_PREFIX} 謝罪キャンペーン", product_category="beverage",
            owner_id=admin_id, models=[hanako],
            req=dict(exposure_level=0, outfit_type="normal",
                     pose_description="土下座して深く謝罪するポーズ"),
        )
        projects.append((p_model_ng.project_name, "NG (花子のモデル固有NG=土下座ポーズ)"))

        db.commit()

        # ---- Summary ------------------------------------------------------
        print("demo data created:")
        print("  models:")
        print(f"    - {hanako.stage_name}: 成人確認済・広範許諾 (+NG rules: タトゥー/土下座/たばこ)")
        print(f"    - {mizuki.stage_name}: 水着 条件付き許諾 (exposure_max=3)")
        print(f"    - {miku.stage_name}: 成人未確認 (adult_verified=false)")
        print(f"    - {rei.stage_name}: 契約期限切れ (2024-12-31)")
        print("  projects (expected compliance outcome):")
        for name, outcome in projects:
            print(f"    - {name} -> {outcome}")
        print("seed_demo complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
