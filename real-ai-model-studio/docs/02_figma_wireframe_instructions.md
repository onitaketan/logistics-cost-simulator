# 02 Figma Wireframe Instructions

## 1. Design Concept

高級芸能事務所の管理画面、広告制作スタジオ、法務管理システムを統合したUIにする。

- 白、薄いグレー、濃紺、黒を基調
- OKはグリーン、注意はアンバー、NGはレッド
- 派手にしすぎず、上品で信頼感のある画面
- モデル画像は小さめに表示し、権限者のみ拡大可能
- 承認状態・契約期限・リスク状態が一目でわかるUI

## 2. Figma Pages

```text
00_Design System
01_Login
02_Dashboard
03_Model Management
04_Contract & Permission
05_Project Management
06_Compliance Check
07_Generation Studio
08_Review & Approval
09_Delivery Management
10_Audit Log
11_Admin Settings
```

## 3. Common Components

### Header

- Logo
- Current page title
- Notification icon
- User name
- Role badge
- Logout

### Sidebar

- Dashboard
- Models
- Projects
- Generation Studio
- Review
- Delivery
- Audit Log
- Settings

### Status Badges

| Badge | Meaning |
|---|---|
| Available | 利用可能 |
| Expiring Soon | 契約期限注意 |
| Suspended | 停止中 |
| Review Required | 承認必要 |
| Approved | 承認済 |
| Rejected | 却下 |
| Prohibited | 生成禁止 |

## 4. Dashboard

### KPI Cards

- Active Models
- Projects In Progress
- Pending Approvals
- High Risk Items
- Expiring Contracts

### Tables

- Pending approvals
- High risk projects
- Recent generations
- Contracts expiring within 30 days

## 5. Model List

### Layout

Left filter panel + right model card grid.

### Filters

- Agency
- Status
- Adult verified
- Swimwear allowed
- Underwear allowed
- Bath allowed
- Overseas allowed
- Video allowed
- Contract end date

### Model Card

- Profile image
- Stage name
- Agency
- Contract end
- Permission badges
- Status
- Detail button

## 6. Model Detail

Tabs:

- Overview
- Contract
- Permissions
- Assets
- NG Rules
- History

### Permissions Matrix

| Item | Allowed | Approval | Notes |
|---|---|---|---|
| AI generation | yes/no | internal/legal |  |
| AI training | yes/no | legal |  |
| Swimwear | yes/no/conditional | legal |  |
| Underwear | yes/no/conditional | person/agency |  |
| Bath | yes/no/conditional | person/agency |  |
| Body edit | yes/no/conditional | legal |  |
| Overseas | yes/no | agency |  |

## 7. Project Registration

Step UI:

1. Basic project info
2. Usage conditions
3. Expression conditions
4. Model selection
5. Compliance check

## 8. Compliance Check

Three-column layout:

- Left: project requirements
- Center: model permissions
- Right: judgement result

Judgement result:

- OK
- Conditional OK
- NG
- Prohibited

Show reasons clearly. Example:

```text
生成不可
理由：対象モデルの契約では海外SNS広告が許可されていません。
対応案：利用地域を日本国内に限定するか、事務所の追加承認を取得してください。
```

## 9. Generation Studio

Layout:

- Left: project/model/permission summary
- Center: output preview
- Right: generation settings
- Bottom: generation history

Generate button must be disabled when:

- Adult verification is false
- Contract expired
- AI generation is not allowed
- Compliance check is NG or Prohibited
- Required approval setting is missing

## 10. Review & Approval

Layout:

- Left: image preview
- Right: project conditions, permission conditions, judgement history
- Bottom: comments and approval buttons

Buttons:

- Approve
- Conditional approve
- Request revision
- Reject

## 11. Audit Log

Filters:

- User
- Model
- Project
- Action type
- Date range
- Risk level
- Download status

Log table:

- Date/time
- User
- Action
- Target
- Details
- IP address
