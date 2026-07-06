# 08 運用マニュアル / Operations Manual

Real AI Model Studio（以下「本システム」）の**定常運用（steady-state operations）**を担う
運用担当者・システム管理者向けのランブックである。

- 対象読者: システム管理者（admin）、インフラ運用担当、法務運用（legal）の各担当。
- 位置づけ: 本書は Phase 5（Hardening）の運用ドキュメント（`CLAUDE.md` 参照）。
  UAT（仮テスト）の手順は `docs/07_trial_runbook.md`、判定ルールの定義は
  `docs/05_compliance_rules.md`、運用ポリシーは `legal/02_operation_policy.md` を参照。
- 本書の記載コマンド・パス・エンドポイントは、リポジトリに実在するものだけを対象とする。
  運用者が別途用意すべきインフラ（S3/R2、バックアップ保管先、監視基盤等）は「ガイダンス」として記す。

> 大原則: 本システムの価値は「作れるか」ではなく「作ってよいか」。生成可否は UI ではなく
> **API / DB / worker の全レイヤーで強制**される。運用でこの多層防御を無効化しない。

---

## 1. システム構成概要

`docker-compose.yml` に定義された構成要素と関係。

| サービス | 実体 | 役割 |
|---|---|---|
| `postgres` | `postgres:16` | 本システムの正本データストア。ユーザー・モデル・契約・許諾・案件・判定・生成・監査ログを保持。生成ゲートの**DBトリガ**もここに存在する |
| `redis` | `redis:7` | Celery のブローカ兼リザルトバックエンド。非同期生成ジョブのキュー |
| `api` | `./apps/api`（FastAPI） | 認証・RBAC・コンプライアンス判定・生成ロック・監査記録の本体。`http://localhost:8000`、OpenAPI は `/docs`。APIプレフィックスは `/api/v1` |
| `worker` | `./apps/api`（Celery worker） | 生成ジョブの実行主体。`celery -A app.workers.celery_app worker` を起動。**実行直前に判定を再検証**する（第3チェックポイント） |
| storage | local / S3 / R2 | 生成画像・参照画像の実体保管。`STORAGE_PROVIDER` で切替（`local`|`s3`|`r2`）。生画像は公開せず**短命署名URL経由のみ**取得可 |
| web frontend | `apps/web`（Next.js） | 表示専用。判定ロジックを持たず、API 結果を描画するだけ。`NEXT_PUBLIC_API_BASE_URL` で API を参照 |

関係図（データフロー）:

```text
[web (Next.js)] --HTTPS--> [api (FastAPI /api/v1)]
                                  |  判定・生成ロック・監査
                                  +--> [postgres]  (正本 + 生成ゲートDBトリガ)
                                  +--> [redis]     (ジョブ投入)
                                            |
                                       [worker]  --判定再検証--> [postgres]
                                            |
                                            +--> [storage(local/S3/R2)]  (実画像を暗号化保管)
```

補足:
- `web` は判定を持たない。生成可否・承認充足の判断はすべて `api`/`postgres` 側で確定する。
- 開発既定では `CELERY_TASK_ALWAYS_EAGER=true` によりジョブは api プロセス内でインライン実行され、
  `worker`/`redis` は不要。**本番は `false` にして `worker` を常駐**させる（§2、§8.4 手順は docs/07 §8.4）。

---

## 2. 起動・停止・再起動手順

### 2.1 Docker Compose（推奨・本番同等）

```bash
cd real-ai-model-studio
cp .env.example .env        # 未作成時のみ。§3 に従い本番値へ更新すること

# 全サービス起動（postgres, redis, api, worker）
docker compose up -d

# 状態確認
docker compose ps
docker compose logs -f api          # api ログ追尾
docker compose logs -f worker       # worker ログ追尾

# 停止（コンテナ停止、データ(pgdata)は保持）
docker compose stop

# 再起動
docker compose restart api worker

# 完全停止（コンテナ削除。※ volume pgdata は残る）
docker compose down
```

> `postgres` は名前付きボリューム `pgdata` に永続化される。`docker compose down -v` は
> **DBを消去する**ため定常運用では使用しないこと（バックアップと明確な意図がある場合のみ）。

DBスキーマの初期適用: `postgres` サービスは初回起動時、`./apps/api/migrations` を
`/docker-entrypoint-initdb.d` にマウントし、`*.sql` を**アルファベット順（=番号順）に自動適用**する
（`docker-compose.yml` 参照）。したがって空のボリュームでの初回起動時に全マイグレーションが適用される。
既存ボリュームには自動適用されない点に注意（§5）。

### 2.2 ローカル venv（README のパス）

Docker を使わず api を直接起動する構成。

```bash
cd real-ai-model-studio
cp .env.example .env
docker compose up -d postgres redis          # DBとRedisだけコンテナで
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .
for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done   # スキーマ適用（番号順）
python scripts/seed.py                        # 初期admin / mockエンジン / scope辞書
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 非同期生成を実運用する場合は別プロセスで worker を起動:
celery -A app.workers.celery_app worker -l info
```

フロントエンド:

```bash
cd real-ai-model-studio
npm install
cd apps/web && npm run dev            # http://localhost:3000
```

### 2.3 起動後の疎通確認

```bash
curl -s http://localhost:8000/health          # {"success":true,"data":{"status":"ok","env":"..."}}
```

`env` が想定の環境（`local`/`staging`/`production` 等）であること、`status:ok` を確認する（§10）。

---

## 3. 環境変数と機密管理

設定は `.env`（`app/core/config.py` の `Settings` が読み込む）。`.env` は `.gitignore` 済みで
**絶対にコミットしない**。以下は `.env.example` と `config.py` の全項目。

### 3.1 API

| 変数 | 既定 | 説明 |
|---|---|---|
| `APP_ENV` | `local` | 実行環境。`local` 以外にすると本番シークレット強制が有効化される（3.4） |
| `API_SECRET_KEY` | `change-me...` | **JWT署名鍵**。全認証呼び出しを保護する最重要機密。長いランダム値を設定 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | アクセストークン有効期限（分） |
| `REQUIRE_2FA` | `false` | 2FA要求フラグ（`docs/06 §1` は2FA推奨） |
| `CORS_ORIGINS` | `http://localhost:3000` | ブラウザからの許可オリジン（カンマ区切り）。フロント/バック分離デプロイ時に設定 |

### 3.2 Database / Queue

| 変数 | 既定 | 説明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://rams:rams@localhost:5432/rams` | 接続文字列。本番は `psycopg`(v3) 前提。v3のC拡張が不調なら `postgresql+psycopg2://...` でも可（ORMは非依存） |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 接続。Celery のブローカ/バックエンド既定値の元 |
| `CELERY_BROKER_URL` | 未指定時 `REDIS_URL` | ブローカURL |
| `CELERY_RESULT_BACKEND` | 未指定時 `REDIS_URL` | リザルトバックエンドURL |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | `true`=インライン実行（Redis/worker不要、開発向け）。**本番は `false` + worker 常駐** |

### 3.3 Storage / AI エンジン / フロント

| 変数 | 既定 | 説明 |
|---|---|---|
| `STORAGE_PROVIDER` | `local` | `local`|`s3`|`r2`。**本番は S3/R2 推奨**（local は開発専用、実PIIに使わない） |
| `STORAGE_BUCKET` | `rams-private` | バケット名。非公開バケットにすること |
| `STORAGE_DIR` | `./storage` | local バックエンドのルート（開発専用） |
| `STORAGE_ENDPOINT_URL` | 空 | S3/R2 エンドポイント（R2やMinIO等で指定） |
| `STORAGE_ACCESS_KEY` | 空 | ストレージアクセスキー（機密） |
| `STORAGE_SECRET_KEY` | 空 | ストレージシークレットキー（機密） |
| `SIGNED_URL_TTL_SECONDS` | `120` | 生画像署名URLの有効秒数。短命を維持する |
| `AI_ENGINE` | `mock` | `mock`|`openai`|`replicate`|`self_hosted`。`self_hosted` は未実装（§12） |
| `AI_ENGINE_API_KEY` | 空 | AIエンジンAPIキー（機密。Replicate は `REPLICATE_API_TOKEN` 系。実キーは課金発生） |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000/api/v1` | フロントが参照するAPIベースURL |

### 3.4 API_SECRET_KEY のローテーションと起動時強制

`config.py::enforce_production_secrets()` により、**`APP_ENV != local` かつ `API_SECRET_KEY` が
空または `change-me` の場合、アプリは起動を拒否する**（fail-closed）。プレースホルダのままステージング/本番へ
出すと誰でも有効な admin トークンを偽造できるためである。

`API_SECRET_KEY` のローテーション手順:

```bash
# 十分に長いランダム値を生成し .env に設定
python -c "import secrets; print(secrets.token_urlsafe(48))"
# -> API_SECRET_KEY=<生成値> を .env に反映し、api / worker を再起動
docker compose restart api worker
```

**重要な運用上の副作用**: 署名鍵を変更すると、既存の発行済みトークンはすべて無効になる（全ユーザーが
再ログイン必要）。これは鍵漏洩時の**全トークン一括失効手段**として利用できる（§9）。

### 3.5 機密の取り扱い原則

- `API_SECRET_KEY` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` / `AI_ENGINE_API_KEY` は
  シークレットマネージャ（クラウドの Secrets Manager / Vault 等）で管理し、`.env` を平文で共有しない。
- 生成AIキーは課金が発生する。ステージングと本番でキーを分離し、egress・予算上限を設定する（docs/07 §8）。

---

## 4. ユーザー・権限管理運用

### 4.1 ロール（RBAC）

`app/core/rbac.py` の権限マトリクス。既定は deny（明示付与のみ許可）。

| ロール | 主な権限（要旨） |
|---|---|
| `admin` | 全権限。ただし **Prohibited を上書きして生成することはできない**（判定エンジンが強制） |
| `legal` | モデル/契約/許諾/成人確認の管理、判定実行、レビュー、内部+法務承認、監査閲覧、DL |
| `sales` | モデル/案件閲覧、案件編集、判定実行、納品 |
| `creative` | モデル閲覧、素材アップロード、判定実行、**生成**、レビュー |
| `approver` | モデル/案件閲覧、レビュー、内部承認 |
| `viewer` | モデル/案件の閲覧のみ |

権限に関わる重要点:
- 契約・許諾・成人確認の登録は `CONTRACT_MANAGE`（legal/admin のみ）。creative は登録できない。
- 監査閲覧（`AUDIT_VIEW`）は admin/legal のみ。
- 承認は内部/法務/管理で分離され、必要承認が全て揃うまで案件は `approved` にならない（承認ゲート）。

### 4.2 初期管理者とパスワードローテーション（必須）

`scripts/seed.py` が作成する初期 admin:

| 役割 | email | 初期パスワード |
|---|---|---|
| admin | `admin@example.com` | `ChangeMe123!` |

**この初期パスワードは開発用であり、いかなる実環境でも即時に変更すること**（seed のコメント参照）。
本番導入時は初回ログイン直後にパスワードを変更し、可能なら初期adminのメール自体を実運用者のものへ更新する。

### 4.3 ユーザーの発行・停止

`USER_MANAGE` 権限（admin）を持つユーザーが `/api/v1/users` で操作する（画面: Settings、または以下API）。

```bash
# 発行（例）
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <admin_token>" -H "Content-Type: application/json" \
  -d '{"name":"法務 太郎","email":"legal@example.com","role":"legal",
       "department":"Legal","password":"<初期PW>"}'

# ロール変更・パスワードリセット・停止（PATCH。password を送るとリセット扱い）
curl -s -X PATCH http://localhost:8000/api/v1/users/<user_id> \
  -H "Authorization: Bearer <admin_token>" -H "Content-Type: application/json" \
  -d '{"status":"suspended"}'
```

- ユーザーの `status` は `active` / `suspended`。退職・権限剥奪時は `suspended` にする（物理削除しない）。
- パスワードリセット時、監査ログには**リセットした事実（`password_reset: true`）のみ**記録され、
  パスワード値そのものは記録されない。
- ユーザー作成・更新は自動的に監査ログ（action_type=`create`/`update`, target_type=`user`）に残る。

---

## 5. DBマイグレーション適用手順

マイグレーションは `apps/api/migrations/` に**番号順のSQLファイル**として存在する。

現在のファイル:
- `0001_init.sql` — 全スキーマ（生成ロックのDBトリガ `trg_enforce_generation_gate` 含む）
- `0002_audit_view_action.sql` — `audit_logs.action_type` に `view` を追加

### 5.1 初回（空DB）への適用

- **Docker Compose**: `postgres` サービスが初回起動時に `migrations/` を initdb ディレクトリとして
  マウントし、`*.sql` を番号順に自動適用する（§2.1）。追加操作は不要。
- **手動 / venv 構成**:

```bash
cd apps/api
for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

### 5.2 既存DBへの追加マイグレーション適用

initdb の自動適用は**空ボリュームの初回のみ**。稼働中DBへ新しい番号のマイグレーション（例: `0002` 以降）を
適用するには、手動で当該ファイルだけを流す。

```bash
# 稼働中の postgres コンテナへ 0002 を適用する例
docker compose exec -T postgres \
  psql -U rams -d rams < apps/api/migrations/0002_audit_view_action.sql
# venv 構成の場合
psql "$DATABASE_URL" -f apps/api/migrations/0002_audit_view_action.sql
```

各マイグレーションは冪等になるよう書かれている（例: `0002` は `DROP CONSTRAINT IF EXISTS` →
再作成、`BEGIN`/`COMMIT` トランザクション内）。適用前に必ず §6 のバックアップを取得すること。
適用後は `docker compose restart api worker` でアプリを再起動する。

---

## 6. バックアップ・リストア

`docs/06 §4` の要件（**日次バックアップ**・DR手順）を満たすための運用。**必ずバックアップすべき3点**:

1. **PostgreSQL（正本DB）** — ユーザー・モデル・契約・許諾・案件・判定・生成・**監査ログ**。
2. **ストレージ（画像実体）** — 生成画像・参照画像（local の `STORAGE_DIR` または S3/R2 バケット）。
3. **暗号化・機密コンテキスト** — `API_SECRET_KEY`、ストレージキー、（S3使用時の）SSE-KMS 鍵参照。
   これらが失われると、署名URL検証・トークン・暗号化オブジェクトの復元ができない。

### 6.1 PostgreSQL バックアップ（pg_dump）

```bash
# カスタム形式（推奨。pg_restore で並列・選択リストア可能）
docker compose exec -T postgres \
  pg_dump -U rams -d rams -Fc > backup_$(date +%Y%m%d_%H%M%S).dump

# venv/直接接続の場合
pg_dump "$DATABASE_URL" -Fc -f backup_$(date +%Y%m%d).dump
```

日次で自動化し（cron / クラウドのスケジューラ）、バックアップは**暗号化して別リージョン/別アカウント**に保管する（ガイダンス）。

### 6.2 PostgreSQL リストア（pg_restore）

```bash
# 空のDBへリストア（--clean で既存を置換する場合は事前バックアップ必須）
docker compose exec -T postgres \
  pg_restore -U rams -d rams --clean --if-exists < backup_YYYYMMDD.dump
```

リストア後は `curl /health` と、判定・監査が読めることを確認する。

### 6.3 ストレージのバックアップ

- **local バックエンド**: `STORAGE_DIR`（既定 `./storage`）配下をアーカイブ。ただし local は開発専用であり、
  実PIIを扱う本番では S3/R2 を使うこと。
- **S3/R2**: バケットのバージョニング有効化＋クロスリージョン/別アカウントレプリケーション、または
  `aws s3 sync` / 互換CLIによる定期同期を運用側で用意する（ガイダンス）。
- DBとストレージは**同一時点で整合**するのが望ましい。生成出力の `file_hash`（実バイトのSHA-256）で
  リストア後の破損検知が可能。

---

## 7. 監査ログ運用

`app/services/audit_service.py` が中核アクションを自動記録する。記録対象の `action_type` は
`login, logout, create, update, delete, generate, download, approve, review, deliver, view`
（`0002` で `view` 追加）。ログイン・生成・レビュー・承認・納品・ダウンロード・閲覧が残る。

### 7.1 閲覧とCSVエクスポート

`AUDIT_VIEW` 権限（admin/legal）で参照する。

```bash
# 一覧（フィルタ: target_type, action_type, from, to, limit<=500）
curl -s "http://localhost:8000/api/v1/audit-logs?action_type=generate&from=2026-07-01&to=2026-07-31" \
  -H "Authorization: Bearer <token>"

# CSVエクスポート（同じフィルタ。limit<=100000。列: created_at,user_id,action_type,target_type,target_id,ip_address）
curl -s "http://localhost:8000/api/v1/audit-logs/export?from=2026-07-01&to=2026-07-31" \
  -H "Authorization: Bearer <token>" -o audit_logs.csv
```

### 7.2 保全ポリシー

- **監査行は決して削除しない**（追記専用として扱う）。法務・肖像権上の証跡である。
  停止・削除の運用は対象モデル/出力のステータス変更で行い、監査行自体は残す。
- 定期的にCSVエクスポートを取得し、DBバックアップとは別に長期保管する（ガイダンス）。
- 保持期間は契約・肖像権上の時効・社内規程に合わせて設定する。**契約終了後も一定期間は保持**すること
  （生成〜納品の証跡追跡のため）。具体年数は法務確認の上で定める。

---

## 8. コンプライアンス・生成ロックの運用上の注意

生成可否は**3層のゲート**で強制される。運用でいずれも無効化しない。

1. **リクエスト時（API層）**: `compliance_engine.py`（純粋関数・fail-closed）が
   OK/Conditional/NG/Prohibited を判定し、`generation_service.py` が ok/conditional 以外では
   生成ジョブを作らない。NG/Prohibited に紐づく生成要求は HTTP 422（`generation_blocked`）で拒否される。
2. **DBトリガ（DB層）**: `generations` への INSERT/UPDATE で `trg_enforce_generation_gate` が発火し、
   紐づく `compliance_check` の `check_status` が `ok`/`conditional` でなければ例外で拒否する。
   API を迂回して直接 INSERT しても防がれる。
3. **worker 実行時（第3チェックポイント）**: worker がジョブ実行直前に判定を**再検証**する。
   投入後に判定が NG へ変わった場合、生成されない。

### 8.1 禁止語・要注意語の辞書

`app/services/prompt_filter.py` に**ハードコード**された辞書:
- `PROHIBITED_TERMS`（未成年・ヌード・性的行為・屈辱・強制・拘束・犯罪・薬物・暴力・差別・政治/宗教勧誘・
  医療効能・虚偽推薦。日英両表記）→ ヒットで **Prohibited** 強制。
- `WARNING_TERMS`（セクシー/濡れ感/密着 等）→ ヒットで **Conditional**（法務レビュー要求）。
- モデル固有NG語（`model_ng_rules`）→ ヒットで **NG** 記録。

> 現状、辞書は**コード内固定**でありDB管理ではない（`docs/06 §6` が目指すDB移行=P1-001は未実装、§12）。
> 語句の追加・修正はコード変更＋デプロイが必要。法務からの追加要望はコード修正として管理する。

### 8.2 契約失効・許諾撤回時の挙動（fail-closed）

- **契約期限切れ**: モデルの契約が終了すると判定は **NG**（`docs/07 §3` のデモ「期限切れ玲」参照）。
  期限切れ後は該当モデルの新規生成が通らない。事前に §11 の契約期限アラートで検知し、更新か停止を決める。
- **成人未確認**: 成人確認がないモデルは **Prohibited**（生成不可）。
- **許諾撤回**: 許諾範囲の縮小・撤回を許諾/契約データへ反映すると、以後の判定が Conditional/NG/Prohibited へ
  倒れ、生成は**閉じる方向（fail-closed）**に動く。運用者は「許可を消す」だけでよく、生成は自動的に止まる。
- Prohibited は admin でも上書きできない（RBAC上も判定エンジン上も）。

---

## 9. インシデント対応

`legal/02_operation_policy.md §6` と `docs/07 §7` に準拠。**疑わしい場合は先に止める（fail-closed）**。

### 9.1 許諾撤回 / 停止要請 / テイクダウン

本人・事務所から停止要請、または許諾範囲外利用が判明した場合:

1. **生成を止める**: 対象モデルを停止する。モデルの `status` を `suspended` に変更（`PATCH /api/v1/models/{id}`,
   `CONTRACT_MANAGE`）。以後の判定が通らなくなり新規生成が止まる。契約失効なら `expired` 相当の状態にする。
2. **既存出力を止める**: 対象の生成出力を `rejected` にし、納品・ダウンロードを不可にする（承認済のみDL可の設計）。
3. **証跡保全**: `/api/v1/audit-logs`（および CSV エクスポート）で generate/approve/deliver/download を確認し、
   ダウンロード・納品先を特定する。**監査行は削除しない**（§7.2）。
4. **削除**: 原則は soft delete（モデルは `deleted_at` を設定して論理削除）。**法務判断による物理削除**が必要な場合のみ、
   法務承認の記録を残した上で対象画像・データを物理削除する（`CLAUDE.md` の削除方針、`docs/06 §2`）。
5. **連絡**: 本人/事務所/広告主への連絡方針を決定し、再発防止策を実施。

### 9.2 生成画像の外部流出

1. 流出した出力を `rejected` にし、署名URLの新規発行を止める（署名URLは `SIGNED_URL_TTL_SECONDS` で短命）。
2. 監査ログの `download`/`deliver` から流出経路・取得者を特定。
3. §9.1 の停止・保全・連絡フローに合流。必要に応じ物理削除。

### 9.3 鍵・トークンの漏洩

- **`API_SECRET_KEY` 漏洩（トークン偽造の恐れ）**: §3.4 の手順で `API_SECRET_KEY` をローテーションする。
  これにより**発行済みトークンが全て失効**し、全ユーザーが再ログインを要求される。実質的な全セッション強制ログアウト。
- **ストレージキー / AIエンジンキー漏洩**: 該当プロバイダ側でキーを失効・再発行し、`.env`（シークレットマネージャ）を
  更新して `api`/`worker` を再起動。漏洩期間のアクセスログを監査する。

---

## 10. 監視・ヘルスチェック

### 10.1 ヘルスエンドポイント

`GET /health`（プレフィックスなし）は `{"success":true,"data":{"status":"ok","env":"<APP_ENV>"}}` を返す。
ロードバランサ/監視の生死確認に使う。`env` が想定環境と一致することも確認する。

```bash
curl -sf http://localhost:8000/health || echo "API DOWN"
```

### 10.2 監視すべき指標（ガイダンス）

| 対象 | 監視内容 | 兆候・対応 |
|---|---|---|
| API | `/health` 応答・レイテンシ | 画面応答目標 3秒未満（`docs/06 §5`）。5xx増加は要調査 |
| DB接続 | `postgres` 生死・接続数・レプリカ遅延 | 接続不能なら api/worker が機能停止 |
| Redis | `redis` 生死・メモリ | ブローカ停止でジョブが滞留 |
| worker キュー滞留 | Celery のキュー深度・実行中/失敗数 | 滞留増は worker 不足/生成遅延。`docker compose logs -f worker` |
| ディスク（local storage） | `STORAGE_DIR` の空き容量 | local運用時は逼迫で書込失敗。S3/R2 では容量管理不要 |

- worker/Redis を使う本番では `CELERY_TASK_ALWAYS_EAGER=false` を前提に、キュー深度・失敗率を監視基盤へ連携する（ガイダンス）。
- 初期の可用性目標は業務時間帯（`docs/06 §4`）。監視アラートの当直体制はこれに合わせる。

---

## 11. 定期運用タスク

| 頻度 | タスク | 手順 |
|---|---|---|
| 日次 | DB + ストレージ バックアップ | §6。取得成否とサイズを確認 |
| 日次/常時 | 契約期限アラート確認 | ダッシュボード、または `GET /api/v1/dashboard/expiring-contracts?days=30`（`days` は 1..365 にクランプ）。期限が近い契約は更新か停止を判断 |
| 週次 | 監査ログレビュー | §7。生成・ダウンロード・承認・納品の異常な集中や権限外操作の兆候を確認。必要ならCSVで長期保管 |
| 定期（社内規程） | パスワードローテーション | admin 及び特権ユーザーのパスワード更新（§4.3 PATCH）。退職者は即時 `suspended` |
| 定期 | `API_SECRET_KEY` ローテーション | §3.4。実施時は全ユーザー再ログインを周知 |
| リリース時 | マイグレーション適用 | §5。適用前にバックアップ、適用後に再起動と `/health` 確認 |

契約期限アラート応答例:

```bash
curl -s "http://localhost:8000/api/v1/dashboard/expiring-contracts?days=30" \
  -H "Authorization: Bearer <token>"
# -> [{"stage_name":"...","contract_number":"...","contract_end":"...","days_left":N}, ...]（期限が近い順）
```

`days_left` が小さい契約から、更新手続きまたはモデル停止（§9.1）を進める。

---

## 12. 既知の制約

本書執筆時点（README の実装ステータス準拠）の正直な制約。運用で回避策を取ること。

- **本人/事務所 承認ポータル（外部ログイン）は未実装**（P2）。MVP では本人/事務所の承認は
  **法務（legal）が代理で確認・記録**して署名（サインオフ）する運用とする（`docs/07 §5`）。
  実運用では、契約・許諾登録時に本人/事務所承認の証跡（書面・メール等）を別途保管すること。
- **禁止語・要注意語辞書はコード内固定**（`prompt_filter.py`）。DB管理（P1-001, `docs/06 §6`）は未実装。
  語句の追加・修正はコード変更＋デプロイが必要で、法務が画面から編集することはできない。
- **self-hosted GPU アダプタは未実装**（`AI_ENGINE=self_hosted` は選択肢のみで実体なし）。
  実生成は `mock`（プレースホルダ）/ `openai` / `replicate` を使用する。
- **実本番キーでの実生成**は README 上まだ未完了項目（課金発生。ステージング＋検証予算で先行実施。手順 `docs/07 §8`）。
- local ストレージは開発専用（実PII不可）。本番は S3/R2 を使い、SSE/KMS 等の暗号化を有効化する。

> 運用開始前に、契約条項・肖像権・個人情報・広告表現・AI規制について
> **弁護士・専門家の確認を必須**とする（README 原本の注意）。本書は技術運用手順であり、
> 法的判断を代替しない。
