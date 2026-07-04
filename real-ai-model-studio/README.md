# Real AI Model Studio

社内専用・実在AIモデル生成基盤（MVP foundation scaffold）。

本人および所属事務所の明示的許諾に基づき、実在成人モデルのAI肖像を広告・販促・商談用途で
**「作ってよい範囲でだけ」** 安全に生成・編集・管理するための社内業務基盤。

> 設計原則: 「作れるか」ではなく「作ってよいか」。生成可否は UI ではなく **Backend / API / DB**
> の全レイヤーで強制する（`CLAUDE.md` を参照）。

## Monorepo layout

```text
real-ai-model-studio/
├── apps/
│   ├── api/            # FastAPI backend（判定・生成ロック・監査の本体）
│   └── web/            # Next.js frontend（判定は持たず、API結果の表示に徹する）
├── packages/
│   └── shared-types/   # フロント/バック共有の型・enum辞書
├── docker-compose.yml  # postgres + redis + api（ローカル開発）
└── .env.example
```

## Backbone（最重要3コンポーネント）

| コンポーネント | 役割 |
|---|---|
| `apps/api/app/services/compliance_engine.py` | 全生成可否判定（OK/Conditional/NG/Prohibited）。純粋関数・fail-closed |
| `apps/api/app/services/generation_service.py` | 判定通過(ok/conditional)を再検証しない限り生成ジョブを作らない生成ロック |
| `apps/api/app/services/audit_service.py` | create/update/delete/generate/download/approve を全て監査ログ化 |

## Quick start (local)

```bash
cp .env.example .env
docker compose up -d postgres redis
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .
psql "$DATABASE_URL" -f migrations/0001_init.sql   # スキーマ適用
python scripts/seed.py                              # 初期admin/mockエンジン/scope辞書を投入
uvicorn app.main:app --reload                       # http://localhost:8000/docs
pytest                                              # 判定エンジン・承認ゲートの単体テスト（24件）
```

## 実装ステータス（Phase 1 Foundation）

- [x] DB schema (migrations/0001_init.sql) — 生成ロック制約込み
- [x] Auth / RBAC 骨格（JWT + role 依存性）
- [x] Compliance engine（doc 05 のルール実装 + 単体テスト）
- [x] Generation service（判定ロック）/ AI adapter（base + mock）
- [x] Audit / Storage service
- [x] 全MVPエンドポイントの router 雛形（26 endpoints, SQLAlchemy 永続化結線済み）
- [x] 資産アップロード（file_hash / consent 検証）P0-009
- [x] 承認完了ゲート（必要承認が全て揃うまで approved にしない）+ 納品ロック
- [x] 初期データ投入 scripts/seed.py（admin / mock engine / scope 辞書）
- [x] Next.js フロント骨格 + APIクライアント + 共有型
- [ ] Storage 実装（S3/R2 SSE）・署名URLの本結線（現在はプレースホルダ）
- [ ] 生成の非同期化（Celery/Redis ワーカーへ移譲）
- [ ] 本人/事務所 承認ポータル（P2）

> 本スキャフォールドは Phase 1 の「土台」。判定・ロック・監査の**設計と骨格**を固めることを目的とし、
> 一部 router は永続化を TODO として残しています。運用前に弁護士・専門家確認が必須（README原本の注意参照）。
