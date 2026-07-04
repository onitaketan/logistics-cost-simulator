# 03 API Specification

## 1. Base

```text
/api/v1
```

## 2. Common Response

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

## 3. Auth

### POST /auth/login

```json
{
  "email": "user@example.com",
  "password": "password",
  "otp_code": "123456"
}
```

### POST /auth/logout

Logout current session.

## 4. Users

### GET /users

Query:

```text
?role=legal&status=active
```

### POST /users

```json
{
  "name": "佐藤花子",
  "email": "sato@example.com",
  "role": "legal",
  "department": "Legal"
}
```

### PATCH /users/{user_id}

Update user.

## 5. Models

### GET /models

Query:

```text
?status=available&swimwear_allowed=true&agency_name=ABC
```

### POST /models

```json
{
  "stage_name": "Model A",
  "real_name": "山田花子",
  "agency_name": "ABC Agency",
  "birth_date": "1998-01-01",
  "adult_verified": true,
  "notes": "本人確認済み"
}
```

### GET /models/{model_id}

Get model detail.

### PATCH /models/{model_id}

Update model.

## 6. Contracts

### POST /models/{model_id}/contracts

```json
{
  "contract_number": "CON-2026-001",
  "contract_type": "base",
  "contract_start": "2026-07-01",
  "contract_end": "2027-06-30",
  "ai_generation_allowed": true,
  "ai_training_allowed": true,
  "synthetic_identity_allowed": true,
  "post_contract_use_allowed": false,
  "deletion_policy": "契約終了後30日以内に学習用データを停止・削除"
}
```

### POST /contracts/{contract_id}/files

FormData:

```text
file
file_type=contract|consent|agency_approval
```

## 7. Permissions

### POST /models/{model_id}/permissions

```json
{
  "contract_id": "uuid",
  "media_scope": ["web", "sns", "ec", "print"],
  "region_scope": ["japan", "asia"],
  "product_scope": ["beverage", "beauty", "apparel"],
  "prohibited_product_scope": ["finance", "medical", "political"],
  "swimwear_allowed": true,
  "underwear_allowed": false,
  "bath_allowed": "conditional",
  "exposure_level_max": 3,
  "face_edit_allowed": false,
  "body_edit_allowed": false,
  "hair_edit_allowed": true,
  "makeup_edit_allowed": true,
  "video_allowed": false,
  "secondary_use_allowed": false,
  "approval_required_level": "legal"
}
```

## 8. Assets

### POST /models/{model_id}/assets

FormData:

```text
file
asset_type=face|body|expression|pose|reference|ng
usage_type=training|reference|review_only|prohibited
tags=["front","smile"]
```

### GET /models/{model_id}/assets

Get model assets.

### DELETE /assets/{asset_id}

Soft delete or suspend asset.

## 9. Projects

### GET /projects

Get project list.

### POST /projects

```json
{
  "project_name": "宇宙背景 飲料広告",
  "client_name": "Client A",
  "brand_name": "Brand X",
  "product_name": "Premium Soda",
  "product_category": "beverage",
  "deadline": "2026-08-31"
}
```

### POST /projects/{project_id}/requirements

```json
{
  "media": ["web", "sns"],
  "region": ["japan"],
  "usage_start": "2026-09-01",
  "usage_end": "2026-12-31",
  "output_type": "image",
  "scene_type": "space",
  "outfit_type": "normal",
  "exposure_level": 0,
  "pose_description": "商品を持って正面を向く",
  "expression_description": "上品な笑顔",
  "background_description": "宇宙ステーションの窓辺"
}
```

### POST /projects/{project_id}/models

```json
{
  "model_id": "uuid",
  "usage_role": "main"
}
```

## 10. Compliance

### POST /projects/{project_id}/compliance-check

```json
{
  "model_id": "uuid"
}
```

Response:

```json
{
  "check_status": "conditional",
  "risk_level": "middle",
  "violations": [
    {
      "field": "bath_allowed",
      "message": "入浴表現は条件付き許可です。本人/事務所確認が必要です。"
    }
  ],
  "required_approvals": ["legal", "agency"],
  "check_summary": "生成は可能ですが、法務および事務所確認が必要です。"
}
```

## 11. Generations

### POST /generations

```json
{
  "project_id": "uuid",
  "model_id": "uuid",
  "compliance_check_id": "uuid",
  "ai_engine_id": "uuid",
  "prompt_text": "許諾範囲内の広告用画像を生成する。上品な宇宙背景で、商品を手に持つ。",
  "negative_prompt_text": "nudity, explicit, humiliating, illegal, minor-looking",
  "generation_params": {
    "aspect_ratio": "4:5",
    "width": 1024,
    "height": 1280,
    "output_count": 4,
    "style": "premium advertising"
  }
}
```

Response:

```json
{
  "generation_id": "uuid",
  "status": "queued"
}
```

### GET /generations/{generation_id}

Get generation status.

### GET /generations/{generation_id}/outputs

Get generation outputs.

## 12. Outputs

### PATCH /outputs/{output_id}/status

```json
{
  "output_status": "selected"
}
```

### POST /outputs/{output_id}/revise

```json
{
  "revision_prompt": "背景をより高級感のある照明に変更。人物の顔と体型は変更しない。",
  "target_area": "background"
}
```

## 13. Reviews

### POST /outputs/{output_id}/reviews

```json
{
  "review_type": "legal",
  "status": "revise",
  "comment": "利用媒体は問題ないが、衣装表現を少し控えめにしてください。"
}
```

## 14. Approvals

### POST /outputs/{output_id}/approvals

```json
{
  "approval_level": "legal",
  "approval_status": "approved",
  "approval_comment": "契約範囲内のため承認。"
}
```

## 15. Deliveries

### POST /deliveries

```json
{
  "project_id": "uuid",
  "output_id": "uuid",
  "delivered_to": "Client A",
  "delivery_method": "download_link",
  "usage_media": ["web", "sns"],
  "usage_region": ["japan"],
  "usage_start": "2026-09-01",
  "usage_end": "2026-12-31"
}
```

## 16. Audit Logs

### GET /audit-logs

Query:

```text
?target_type=output&action_type=download&from=2026-07-01&to=2026-07-31
```
