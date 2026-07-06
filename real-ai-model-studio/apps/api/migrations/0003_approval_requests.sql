-- 0003: external approval portal (P2-001 / P2-002).
--
-- An internal user with legal-level approval permission issues a single-use,
-- expiring link so an agency or the person themselves can view ONE output and
-- record an approval decision without a system login. Only the SHA-256 hash of
-- the token is stored; the raw token exists only in the link. The decision is
-- written into the normal `approvals` table (approver_id NULL = external), so it
-- flows through the same approval-completeness gate.

CREATE TABLE approval_requests (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id      uuid NOT NULL REFERENCES generation_outputs(id),
    level          varchar(16) NOT NULL CHECK (level IN ('agency', 'person')),
    token_hash     varchar(64) NOT NULL UNIQUE,
    contact_name   varchar(128),
    contact_email  varchar(255),
    status         varchar(16) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'decided', 'revoked')),
    decision       varchar(16),
    decision_comment text,
    approver_name  varchar(128),
    expires_at     timestamptz NOT NULL,
    decided_at     timestamptz,
    created_by     uuid REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_approval_requests_output ON approval_requests(output_id);
CREATE INDEX idx_approval_requests_token  ON approval_requests(token_hash);
