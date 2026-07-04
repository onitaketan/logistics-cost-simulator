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
- [x] Storage: local backend 実装（実書き込み・SHA-256・HMAC署名URL・traversal防御）+ `/files` 署名アクセス
- [x] **統合テスト（実Postgres）**: 生成が API層とDB層の両方でブロックされることを実証
- [x] フロント実結線（全画面をAPIへ結線・認証ガード・生成ポーリング・承認の不足表示・監査フィルタ）
- [x] API入力バリデーション（Literal enum / 範囲 / 空文字拒否 / 期間整合）＋日本語エラー＋ページング
- [x] 判定の作り込み（禁止/要注意辞書の拡充・**モデル固有NGルール**統合）＋判定テスト60件
- [x] デモデータ scripts/seed_demo.py（OK/Conditional/NG/Prohibited を網羅する仮テスト用データ）
- [ ] Storage: S3/R2（SSE-KMS）バックエンドの結線（interfaceは用意済み・boto3差込）
- [ ] 生成の非同期化（Celery/Redis ワーカーへ移譲）※**仮テスト後**に実施（API契約変更を伴うため）
- [ ] 本人/事務所 承認ポータル（P2）

## Testing

```bash
cd apps/api
# DB不要のユニット（判定・承認・Storage・判定マトリクス）: 105件
pytest tests/test_compliance_engine.py tests/test_approval_service.py \
       tests/test_storage_service.py tests/test_compliance_rules_matrix.py
# 統合テスト（実Postgres必須。schema適用+seed済みのDBを指す DATABASE_URL を渡す）: 3件（DBなしなら自動skip）
DATABASE_URL=postgresql+psycopg://... pytest tests/test_integration_flow.py
# 仮テスト用のデモデータ投入:
DATABASE_URL=... python scripts/seed_demo.py
```

合計 **108 テスト green**（ユニット105 + 実Postgres統合3）。

### Frontend type-check

```bash
npm install            # ルートで実行（npm workspaces）
npm run typecheck      # = tsc --noEmit（apps/web）。src 配下エラー0で通過
```

> ドライバ注意: 本番は `psycopg` (v3) を想定。CI/ローカルで v3 のC拡張が壊れている場合は
> `postgresql+psycopg2://...` でも動作します（ORMはドライバ非依存）。

> 本スキャフォールドは Phase 1 の「土台」。判定・ロック・監査の**設計と骨格**を固めることを目的とし、
> 一部 router は永続化を TODO として残しています。運用前に弁護士・専門家確認が必須（README原本の注意参照）。
