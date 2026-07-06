# 07 仮テスト手順書 / Trial Runbook

社内関係者による仮テスト（UAT）を実施するための手順・検証項目・記録様式。
実装状況は `README.md`、判定ルールは `docs/05_compliance_rules.md` を参照。

> 本システムの中核価値は「作れるか」ではなく「作ってよいか」。仮テストでは
> **許諾外・危険表現が UI/API/DB のどの層でもブロックされること**を重点的に確認する。

---

## 1. 起動手順

### 1.1 前提
- Docker（推奨）または PostgreSQL 16 / Python 3.11+ / Node.js 20+

### 1.2 バックエンド + DB

```bash
cd real-ai-model-studio
cp .env.example .env          # 必要に応じ CORS_ORIGINS 等を調整

# DB
docker compose up -d postgres redis      # もしくは既存の PostgreSQL を使用
cd apps/api
pip install -e .
for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done   # スキーマ（番号順に全適用）
python scripts/seed.py                              # 初期admin/エンジン/scope辞書
python scripts/seed_demo.py                         # 仮テスト用デモデータ
uvicorn app.main:app --host 0.0.0.0 --port 8000     # http://localhost:8000/docs
```

> ドライバ注意: 本番は `psycopg`(v3) 前提。環境により v3 C拡張が不調の場合は
> `DATABASE_URL` を `postgresql+psycopg2://...?client_encoding=utf8` に切替可（ORMは非依存）。

### 1.3 フロントエンド

```bash
cd real-ai-model-studio
npm install
npm run typecheck            # 任意（tsc --noEmit）
cd apps/web && npm run dev   # http://localhost:3000
```

`apps/web` は `NEXT_PUBLIC_API_BASE_URL`（既定 `http://localhost:8000/api/v1`）で API を参照。

---

## 2. ログインアカウント

`scripts/seed.py` が作成する初期管理者：

| 役割 | email | password |
|---|---|---|
| Admin | `admin@example.com` | `ChangeMe123!`（**初回に必ず変更**） |

他ロール（legal / sales / creative / approver / viewer）は Admin ログイン後、
Settings もしくは `POST /api/v1/users` で作成する。ロール別の権限は
`docs/01_requirements.md §1` と RBAC 実装（`app/core/rbac.py`）を参照。

---

## 3. デモデータのシナリオ（期待される判定結果）

`scripts/seed_demo.py` は判定4区分を網羅するデータを投入する。仮テストでは
**各案件×対象モデルで判定を実行し、期待結果と一致するか**を確認する。

### モデル
| 芸名 | 特徴 |
|---|---|
| デモ 花子 | 成人確認済・広い許諾（NG指定: タトゥー/土下座/たばこ） |
| デモ みずき | 水着=条件付き・露出上限3 |
| デモ 未確認みく | **成人確認なし** |
| デモ 期限切れ玲 | 契約終了済（2024-12-31） |

### 案件 → 期待結果
| 案件 | 対象モデル | 期待判定 | 理由 |
|---|---|---|---|
| 宇宙飲料 通常広告 | デモ 花子 | **OK** | 許諾範囲内 |
| リゾート水着 キャンペーン | デモ みずき | **Conditional** | 水着=法務承認要 |
| 金融サービス 広告 | デモ 花子 | **NG** | モデルの禁止カテゴリ |
| 成人向け 商材 | （任意） | **Prohibited** | 絶対禁止カテゴリ |
| 謝罪キャンペーン | デモ 花子 | **NG** | モデル固有NG（土下座） |
| （未確認みく を任意案件で判定） | デモ 未確認みく | **Prohibited** | 成人確認なし |
| （期限切れ玲 を任意案件で判定） | デモ 期限切れ玲 | **NG** | 契約終了 |

---

## 4. 仮テスト チェックリスト

`docs/01_requirements.md §4「MVP完了条件」`を検証項目に落とし込んだもの。
各項目で **UI操作** と **結果** を記録する（§6 の様式）。

### 4.1 認証・権限
- [ ] 正しい資格情報でログインできる／誤ると弾かれる
- [ ] viewer ロールでモデル編集・生成ボタンが使えない（RBAC）
- [ ] creative は契約/許諾の登録ができない（法務のみ）

### 4.2 モデル・契約・許諾
- [ ] モデルを新規登録できる（本名必須）
- [ ] 成人確認を実施でき、確認前は生成に進めない
- [ ] 契約・許諾・素材を画面から登録できる
- [ ] 学習用素材は「同意確認」なしでアップロードできない

### 4.3 案件・判定（最重要）
- [ ] §3 の各シナリオで判定結果が期待どおり（OK/Conditional/NG/Prohibited）
- [ ] **成人未確認モデルは Prohibited になり生成不可**
- [ ] **契約期限切れモデルは NG**
- [ ] **許諾外カテゴリ/媒体/地域は NG**
- [ ] **水着/下着/入浴は Conditional となり追加承認が要求される**
- [ ] 禁止語句を含むプロンプトは Prohibited、要注意語は Conditional
- [ ] 判定を通過しない限り「生成する」ボタンが押せない

### 4.4 生成・レビュー・承認・納品
- [ ] OK/Conditional の案件で生成ジョブが作成され、出力一覧が見える
      （※現状は mock エンジン＝実画像ではなくプレースホルダ）
- [ ] レビュー・承認を登録でき、**必要承認が全て揃うまで「承認済」にならない**
- [ ] 未承認の出力は納品・ダウンロードできない
- [ ] 承認済の出力のみ納品登録できる

### 4.5 監査ログ
- [ ] ログイン・作成・生成・承認・納品・ダウンロードが監査ログに残る
- [ ] 監査ログ画面でアクション種別・対象で絞り込める

### 4.6 多層防御の確認（任意・技術者向け）
- [ ] API を直接叩いても、NG/Prohibited 判定に紐づく生成は 422 で拒否される
- [ ] DB へ直接 INSERT/UPDATE しても、判定が ok/conditional 以外の生成はトリガで拒否される
      （`tests/test_integration_flow.py` が自動検証）

---

## 5. 既知の制約（仮テスト時点）

仮テストの既定構成は開発向けの安全側（`AI_ENGINE=mock` / `CELERY_TASK_ALWAYS_EAGER=true` /
`STORAGE_PROVIDER=local`）だが、以下はいずれも**実装済み**で、環境変数で切り替えられる（§8、docs/08 §3）。

- **AIエンジンは差し替え可能**：`mock`（既定・プレースホルダ）に加え **`openai` / `replicate` アダプタを実装済み**。
  `AI_ENGINE` で選択する（`self_hosted` は選択肢のみで未実装）。
- **生成は非同期実行に対応**：Celery/Redis worker による**実キュー非同期化を実装済み**（docker compose の
  `worker` が消費）。既定はインライン実行（`CELERY_TASK_ALWAYS_EAGER=true`）だが、`false` + worker 常駐で
  本番同等に queued→running→completed で回り、**実行直前に判定を再検証**する。API契約は据え置き。
- **ストレージは S3/R2 に対応**：`STORAGE_PROVIDER=s3|r2` の**バックエンドを実装済み**（暗号化・presigned URL）。
  既定は `local`（開発専用）。生画像はいずれも短命署名URL経由でのみ取得可。
- 本人/事務所の**外部承認ポータルを実装済み**（P2-001/P2-002。トークン式・単回・期限付きリンク）。
  運用手順は docs/08 §4.4「外部承認ポータル運用」を参照。

> なお **実本番キーでの実生成（課金発生）はリポジトリ内では未実施**（ステージング＋検証予算で先行実施。手順は §8）。

---

## 6. 記録様式（コピーして使用）

```
# 仮テスト記録  日付: ____  実施者: ____  ロール: ____

| 項番 | 操作 | 期待 | 実結果 | 判定(OK/NG) | 所見 |
|------|------|------|--------|-------------|------|
| 4.3  | 未確認みく×任意案件で判定 | Prohibited | | | |
| ...  |      |      |        |             |      |

## 発見した問題（重大度: 高/中/低）
- 

## 仕様確認事項
- 
```

---

## 8. 実AIエンジンの結合確認（本番キー投入）

MVP/仮テストは mock エンジン。実際の画像生成に切り替える手順。**本番APIキーは課金が
発生する**ため、まず社内のステージング環境と検証用予算で行うこと。キーは絶対にコミット
しない（`.env` は `.gitignore` 済み）。

### 8.1 キー投入とエンジン切替
```bash
# .env に設定（例: OpenAI）
AI_ENGINE=openai
AI_ENGINE_API_KEY=sk-...            # Replicate の場合は REPLICATE_API_TOKEN=...
# 生成画像の保管先も本番想定に（推奨: S3/R2。生画像を暗号化保管）
STORAGE_PROVIDER=s3                 # or r2 + STORAGE_ENDPOINT_URL / STORAGE_ACCESS_KEY / STORAGE_SECRET_KEY
```
DB の `ai_engines` テーブルに対象エンジンを登録し、生成時にそのエンジンを選ぶこともできる
（`generations.ai_engine_id`）。未指定時は `settings.ai_engine` が使われる。

### 8.2 まず疎通スモーク（DB不要・最小コスト）
```bash
cd apps/api
python scripts/live_ai_smoke.py "a premium beverage on a clean studio background"
# -> returned N image(s) / SMOKE OK  が出れば、キー・接続・アダプタは正常
```

### 8.3 opt-in の結合テスト（実課金・既定はskip）
```bash
RAMS_LIVE_AI=1 AI_ENGINE=openai AI_ENGINE_API_KEY=sk-... \
  pytest tests/test_live_ai.py -q
```

### 8.4 アプリ経由の実生成（本番同等フロー）
1. 非同期で回す場合は `CELERY_TASK_ALWAYS_EAGER=false` にして Redis と worker を起動
   （`docker compose up worker` / `celery -A app.workers.celery_app worker -l info`）。
2. UI で 判定OK/条件付き の案件からプロンプト生成 → ジョブが queued→running→completed。
3. **確認ポイント（重要）**:
   - `generation_outputs.file_path` が **自社ストレージのURI**（`s3://...` / `local://...`）に
     なっていること（プロバイダの一時URLがそのまま保存されていない）。
   - `generation_outputs.file_hash` が**実画像バイトのSHA-256**であること。
   - 生画像は `/api/v1/outputs/{id}/download`（承認済のみ・短命署名URL）経由でのみ取得でき、
     直接URLでは取得できないこと。
   - 実行直前にワーカーが判定を再検証すること（投入後に判定をNGへ変えると生成されない）。
4. レビュー→多段承認→納品まで通し、監査ログに generate/approve/deliver/download が残ることを確認。

### 8.5 ワンコマンド受け入れテスト（推奨・実デプロイAPIに対して）
デプロイ済みAPI（`AI_ENGINE` が実プロバイダを指す）に対し、全経路を自動検証する。
プロバイダの出力バイトを事前に知らなくても、**署名DLで取得したバイトのSHA-256が
`file_hash` と一致し、実画像であること**まで確認する（成人未確認モデルのブロックも検証）。
```bash
cd apps/api
export RAMS_API_BASE=http://<api-host>:8000/api/v1
export RAMS_ADMIN_EMAIL=admin@example.com RAMS_ADMIN_PASSWORD='***'
python scripts/verify_live_generation.py
# -> LIVE GENERATION VERIFICATION: PASS （exit 0）
```
この環境（開発）では擬似プロバイダを使い本スクリプトの正当性を確認済み。ステージングでは
`AI_ENGINE=openai` + 実キー + egress 許可のもとで同じコマンドを実行するだけ。

> プロバイダ側のコンテンツポリシーでも拒否され得る（多層）。ただし**本システムの判定が
> 一次ゲート**であり、プロバイダ拒否に依存しない設計。

---

## 7. 事故・逸脱発生時（`legal/02_operation_policy.md §6` 準拠）

許諾範囲外の生成・利用が判明した場合、または本人/事務所から停止要請があった場合：

1. 対象画像の利用を直ちに停止（output_status を rejected/停止）
2. ダウンロード・納品先を監査ログで確認
3. 監査ログで生成〜納品の証跡を保全
4. 本人/事務所/広告主への連絡方針を決定
5. 修正・削除・再発防止策を実施

> 運用開始前に、契約条項・肖像権・個人情報・広告表現・AI規制について
> **弁護士・専門家の確認を必須**とする（README 原本の注意）。
