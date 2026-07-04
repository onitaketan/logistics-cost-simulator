# MVP Backlog

## P0: Must Have

| ID | Task | Owner | Acceptance Criteria |
|---|---|---|---|
| P0-001 | Auth & login | Backend/Frontend | User can login and logout |
| P0-002 | RBAC | Backend | Role controls access to APIs |
| P0-003 | User management | Admin | Admin can create/suspend users |
| P0-004 | Model CRUD | Backend/Frontend | Model can be registered and viewed |
| P0-005 | Adult verification | Legal/Admin | Model without adult verification cannot generate |
| P0-006 | Contract registration | Legal | Contract period and AI permissions are stored |
| P0-007 | Consent file upload | Backend | Contract/consent PDFs can be stored securely |
| P0-008 | Permission scope | Legal | Media/region/product/exposure permissions are stored |
| P0-009 | Asset upload | Creative/Legal | Reference images can be uploaded with usage type |
| P0-010 | Project CRUD | Sales | Projects can be created and viewed |
| P0-011 | Project requirements | Sales | Usage and expression conditions are stored |
| P0-012 | Model assignment | Sales | Models can be assigned to projects |
| P0-013 | Compliance check | Backend | OK/Conditional/NG/Prohibited is returned |
| P0-014 | Generate lock | Backend | Generation cannot run without valid compliance check |
| P0-015 | AI adapter | AI | Generation engine is behind an adapter interface |
| P0-016 | Generation job | Backend | Jobs can be queued and status checked |
| P0-017 | Output storage | Backend | Generated images are stored with hash |
| P0-018 | Output list | Frontend | Outputs are visible by project |
| P0-019 | Review | Frontend/Backend | Review comment and status can be saved |
| P0-020 | Approval | Frontend/Backend | Approval levels can approve/reject |
| P0-021 | Delivery | Sales | Approved outputs can be delivered/registered |
| P0-022 | Audit log | Backend | Critical actions are logged |

## P1: Should Have

| ID | Task | Acceptance Criteria |
|---|---|---|
| P1-001 | Prohibited terms dictionary | Prompt warning/block works |
| P1-002 | Download restrictions | Only allowed roles can download |
| P1-003 | CSV audit export | Admin can export logs |
| P1-004 | Prompt templates | Templates can be selected |
| P1-005 | Output compare UI | Two/four outputs can be compared |
| P1-006 | Revision generation | Selected output can be revised |
| P1-007 | Contract expiry alerts | Dashboard shows contracts expiring soon |

## P2: Later

| ID | Task |
|---|---|
| P2-001 | Agency approval portal |
| P2-002 | Person approval portal |
| P2-003 | C2PA metadata |
| P2-004 | Invisible watermark |
| P2-005 | Self-hosted GPU |
| P2-006 | Video generation |
| P2-007 | Multilingual UI |
| P2-008 | Face consistency scoring |
