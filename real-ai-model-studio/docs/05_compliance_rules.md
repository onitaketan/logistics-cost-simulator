# 05 Compliance Rules

## 1. Judgement Status

| Status | Meaning | Handling |
|---|---|---|
| OK | 生成可能 | 通常フロー |
| Conditional | 条件付き可能 | 追加承認後に利用可 |
| NG | 生成不可 | 生成ボタン無効 |
| Prohibited | 絶対禁止 | 管理者でも解除不可 |

## 2. Base Rules

| No | Item | Condition | Result |
|---:|---|---|---|
| 1 | 成人確認 | adult_verified=false | Prohibited |
| 2 | 年齢不明 | birth_date is null or adult verification missing | NG |
| 3 | 契約有効性 | contract_end < today | NG |
| 4 | AI生成許可 | ai_generation_allowed=false | NG |
| 5 | AI学習許可 | training requested and ai_training_allowed=false | NG |
| 6 | 利用媒体 | project.media not in permission.media_scope | NG |
| 7 | 利用地域 | project.region not in permission.region_scope | NG |
| 8 | 商品カテゴリ | project.category in prohibited_product_scope | NG |
| 9 | 商品カテゴリ | project.category not in product_scope | Conditional or NG |
| 10 | 使用期間 | usage_end > contract_end | Conditional |
| 11 | 二次利用 | secondary_use=true and not allowed | NG |
| 12 | 海外配信 | overseas=true and not allowed | NG |
| 13 | 動画利用 | output_type=video and not allowed | NG |

## 3. Expression Rules

| Expression | Condition | Result |
|---|---|---|
| 通常広告 | exposure_level 0-1 | OK |
| リゾート | exposure_level 1-2 | OK or Conditional |
| スポーツ | exposure_level 1-2 | OK |
| 水着 | swimwear_allowed=false | NG |
| 水着 | swimwear_allowed=true | Conditional |
| 下着 | underwear_allowed=false | NG |
| 下着 | underwear_allowed=true | Conditional |
| 入浴 | bath_allowed=false | NG |
| 入浴 | bath_allowed=conditional | Conditional |
| 明示的ヌード | any | Prohibited |
| 性行為示唆 | any | Prohibited |
| 屈辱的表現 | any | Prohibited |
| 犯罪・薬物・暴力・差別 | any | Prohibited |

## 4. Exposure Levels

| Level | Definition | Default Result |
|---:|---|---|
| 0 | 通常衣装 | OK |
| 1 | ノースリーブ、脚出し等 | OK |
| 2 | スポーツ、リゾート軽露出 | OK/Conditional |
| 3 | 水着 | Conditional |
| 4 | 下着、入浴、ボディライン強調 | Conditional |
| 5 | 明示的性的表現 | Prohibited |

## 5. Age and Appearance Rules

| Rule | Condition | Result |
|---|---|---|
| 実年齢18歳未満 | true | Prohibited |
| 成人確認なし | true | NG or Prohibited |
| 未成年に見える演出 | true | Prohibited |
| 制服風 × 露出表現 | true | Prohibited |
| 幼く見せる加工 | true | Prohibited |
| 年齢を若く見せる指示 | age_appearance_change_allowed=false | NG |

## 6. Product Category Rules

| Category | Default Result |
|---|---|
| 飲料 | OK |
| 食品 | OK |
| 美容 | OK/Conditional |
| アパレル | OK |
| 水着 | Conditional |
| 下着 | Conditional |
| 旅行 | OK |
| 温泉旅館 | Conditional |
| 健康食品 | Conditional |
| 医療 | Conditional/NG |
| 金融 | Conditional/NG |
| 政治 | NG |
| 宗教 | NG |
| 成人向け | Prohibited |
| ギャンブル | NG |
| 違法商材 | Prohibited |

## 7. Prompt Blocking Terms

Block prompts containing terms or instructions related to:

- minors or minor-like sexualization
- explicit nudity
- sexual acts
- humiliation
- coercion
- restraint in sexualized context
- crime
- illegal drugs
- violence
- discrimination
- political endorsement
- religious endorsement
- medical efficacy claims
- false personal recommendation

## 8. Warning Terms

Terms that require warning and possible legal review:

- セクシー
- 濡れ感
- ベッド
- 密着
- 透け感
- 大胆
- 挑発的
- 悩殺

These are not automatically prohibited, but must be evaluated by context, contract and permission settings.

## 9. Approval Requirements

| Condition | Required Approval |
|---|---|
| 通常広告 | Creative lead |
| 初回利用モデル | Creative + Legal |
| 水着 | Legal |
| 下着 | Legal + Person/Agency |
| 入浴 | Legal + Person/Agency |
| 海外配信 | Legal + Agency |
| 医療/健康食品 | Legal |
| 金融 | Legal + Admin |
| 屋外広告 | Legal + Agency |
| 大型広告 | Admin |

## 10. Post-generation Checks

Every selected output must be checked for:

- face consistency
- body modification beyond permission
- outfit compliance
- exposure level
- background risk
- hand/finger errors
- text/logo errors
- false endorsement
- product claim risk
- dignity/brand image risk
