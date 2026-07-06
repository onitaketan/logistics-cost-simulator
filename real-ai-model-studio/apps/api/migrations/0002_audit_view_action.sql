-- 0002: allow 'view' in audit_logs.action_type.
-- Reviewers must visually inspect candidate images BEFORE approval (docs/05 §10),
-- and every access to model imagery must be audited (docs/06 §2). The preview
-- endpoint records those accesses as action_type='view'.

BEGIN;

ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_type_check;
ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_type_check
    CHECK (action_type IN ('login','logout','create','update','delete',
                           'generate','download','approve','review','deliver','view'));

COMMIT;
