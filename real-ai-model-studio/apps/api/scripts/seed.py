"""Idempotent seed for local/dev bootstrap.

Usage:
    psql "$DATABASE_URL" -f migrations/0001_init.sql   # schema first
    python scripts/seed.py                             # then seed

Creates: an initial admin user, the mock AI engine, and the scope vocabulary
(media/region/product/expression) that the compliance UI and engine reference.
Nothing here is destructive; existing rows are left untouched.
"""

from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.generation import AIEngine, PromptTemplate
from app.models.user import User

# Starter prompt templates (P1-004). Deliberately generic/compliant — they seed
# the prompt field for Creative and are re-screened at the generation boundary.
PROMPT_TEMPLATES = [
    {"name": "商品を持つ上半身ポートレート",
     "body": "上品なスタジオ照明で、清潔感のある衣装のモデルが商品を自然に持つ上半身ポートレート。背景はシンプルで商品が引き立つ構図。",
     "negative_body": "露出過多, 過度な加工, 不自然な指",
     "tags": ["ec", "beverage", "portrait"]},
    {"name": "屋外ライフスタイル（自然光）",
     "body": "晴れた屋外で自然光を活かしたライフスタイルカット。モデルは通常の日常的な服装で、リラックスした自然な表情。",
     "negative_body": "露出過多, 誇張表現",
     "tags": ["sns", "lifestyle", "outdoor"]},
    {"name": "スタジオ・ブランドカット",
     "body": "無地背景のスタジオ撮影。ブランドの世界観に沿った落ち着いた色調で、商品とモデルのバランスの取れた広告向けカット。",
     "negative_body": "ロゴ改変, 過度なレタッチ",
     "tags": ["print", "brand", "studio"]},
]

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ChangeMe123!"  # dev only — rotate immediately in any real env

SCOPES = {
    "media": [("web", "Web"), ("sns", "SNS"), ("ec", "EC"), ("print", "紙媒体"),
              ("outdoor", "屋外広告"), ("video", "動画")],
    "region": [("japan", "日本"), ("asia", "アジア"), ("eu", "欧州"), ("global", "全世界")],
    "product": [("beverage", "飲料"), ("food", "食品"), ("beauty", "美容"),
                ("apparel", "アパレル"), ("swimwear", "水着"), ("underwear", "下着"),
                ("travel", "旅行"), ("onsen", "温泉旅館"), ("health_food", "健康食品"),
                ("medical", "医療"), ("finance", "金融"), ("political", "政治"),
                ("religion", "宗教"), ("gambling", "ギャンブル")],
    "expression": [("normal", "通常"), ("resort", "リゾート"), ("sports", "スポーツ"),
                   ("swimwear", "水着"), ("underwear", "下着"), ("bath", "入浴")],
}


def seed_scopes(conn) -> int:
    n = 0
    for kind, items in SCOPES.items():
        for code, label in items:
            conn.execute(
                text("""INSERT INTO scope_vocabulary (kind, code, label_ja)
                        VALUES (:k, :c, :l)
                        ON CONFLICT (kind, code) DO NOTHING"""),
                {"k": kind, "c": code, "l": label},
            )
            n += 1
    return n


def main() -> None:
    with engine.begin() as conn:
        seed_scopes(conn)

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == ADMIN_EMAIL).first():
            db.add(User(name="System Admin", email=ADMIN_EMAIL, role="admin",
                        department="System", password_hash=hash_password(ADMIN_PASSWORD)))
            print(f"created admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        if not db.query(AIEngine).filter(AIEngine.adapter_key == "mock").first():
            db.add(AIEngine(name="Mock Engine", adapter_key="mock", training_capable=False))
            print("created ai_engine: mock")
        for tpl in PROMPT_TEMPLATES:
            if not db.query(PromptTemplate).filter(PromptTemplate.name == tpl["name"]).first():
                db.add(PromptTemplate(**tpl))
                print(f"created prompt_template: {tpl['name']}")
        db.commit()
        print("seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
