# 06 Non Functional Requirements

## 1. Security

- HTTPS only
- Role Based Access Control
- Optional IP restriction / VPN restriction
- 2FA recommended
- Encrypted storage for original and reference images
- File hash for all uploaded and generated files
- Download permission control
- Download audit log
- No public access to raw image files

## 2. Privacy & Data Protection

- Store only necessary personal data
- Separate identity data and generated assets where possible
- Log all access to model personal data
- Support data usage suspension
- Support legally approved physical deletion workflow

## 3. Auditability

- All critical actions must create audit logs
- Logs should include user, timestamp, target, action, IP, user agent, before/after data when applicable
- Contract and permission changes must be traceable
- Generation must store prompt, engine, parameters, compliance check ID and output IDs

## 4. Availability

- Initial target: internal business-hour availability
- Daily backup
- Disaster recovery procedure
- Storage lifecycle management

## 5. Performance

- Standard screen response target: under 3 seconds
- Generation time depends on AI engine
- Initial concurrent users: 10-30
- Heavy generation handled by queue worker

## 6. Maintainability

- AI engine adapter pattern
- Rule engine separated from UI
- Prompt templates managed in DB
- Prohibited terms managed in DB
- Permission logic testable by unit tests

## 7. Extensibility

Future support:

- Video generation
- Agency approval portal
- Person approval portal
- C2PA/Content Credentials
- Invisible watermark
- self-hosted GPU
- multilingual UI
- brand template library
