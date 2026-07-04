-- Real AI Model Studio — initial schema (Phase 1 Foundation)
-- Design principle: the database is the LAST line of defense. Generation cannot exist
-- without a compliance check; contracts/permissions are never hard-deleted in normal ops.
--
-- Apply: psql "$DATABASE_URL" -f migrations/0001_init.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Enums (kept as CHECK constraints for portability; scope vocabularies live in
-- reference tables so Legal can manage them without a migration).
-- ---------------------------------------------------------------------------

CREATE TABLE scope_vocabulary (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        varchar(32)  NOT NULL,   -- media | region | product | expression
    code        varchar(64)  NOT NULL,   -- canonical value e.g. 'web','japan','beverage'
    label_ja    varchar(128) NOT NULL,
    is_active   boolean      NOT NULL DEFAULT true,
    UNIQUE (kind, code)
);

-- ---------------------------------------------------------------------------
-- Users & RBAC
-- ---------------------------------------------------------------------------

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           varchar(128) NOT NULL,
    email          varchar(255) NOT NULL UNIQUE,
    password_hash  text         NOT NULL,
    role           varchar(16)  NOT NULL
                     CHECK (role IN ('admin','legal','sales','creative','approver','viewer')),
    department     varchar(128),
    totp_secret    text,                       -- nullable until 2FA enrolled
    status         varchar(16)  NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended')),
    last_login_at  timestamptz,
    created_at     timestamptz  NOT NULL DEFAULT now(),
    updated_at     timestamptz  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Models (real people) — adult-only, soft-delete via status
-- ---------------------------------------------------------------------------

CREATE TABLE models (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_name           varchar(128) NOT NULL,
    real_name            varchar(128) NOT NULL,
    agency_name          varchar(128),
    agency_contact_name  varchar(128),
    agency_contact_email varchar(255),
    birth_date           date,
    adult_verified       boolean     NOT NULL DEFAULT false,
    adult_verified_at    timestamptz,
    adult_verified_by    uuid REFERENCES users(id),
    status               varchar(16) NOT NULL DEFAULT 'available'
                           CHECK (status IN ('available','suspended','expired')),
    profile_image_path   text,
    notes                text,
    deleted_at           timestamptz,          -- soft delete
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    -- adult_verified=true must record when/who verified
    CONSTRAINT adult_verified_needs_evidence
        CHECK (adult_verified = false OR adult_verified_at IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- Contracts & permissions — NEVER hard-deleted in ordinary operation
-- ---------------------------------------------------------------------------

CREATE TABLE model_contracts (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id                  uuid NOT NULL REFERENCES models(id),
    contract_number           varchar(64) NOT NULL,
    contract_type             varchar(32) NOT NULL
                                CHECK (contract_type IN ('base','individual','additional_consent')),
    contract_start            date NOT NULL,
    contract_end              date NOT NULL,
    renewal_type              varchar(16) CHECK (renewal_type IN ('auto','negotiation','end')),
    contract_file_path        text,
    consent_file_path         text,
    agency_approval_file_path text,
    ai_generation_allowed     boolean NOT NULL DEFAULT false,
    ai_training_allowed       boolean NOT NULL DEFAULT false,
    synthetic_identity_allowed boolean NOT NULL DEFAULT false,
    post_contract_use_allowed boolean NOT NULL DEFAULT false,
    deletion_policy           text,
    created_by                uuid REFERENCES users(id),
    created_at                timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT contract_dates_valid CHECK (contract_end >= contract_start)
);

CREATE TABLE model_permissions (
    id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id                      uuid NOT NULL REFERENCES models(id),
    contract_id                   uuid NOT NULL REFERENCES model_contracts(id),
    media_scope                   jsonb NOT NULL DEFAULT '[]',   -- ["web","sns","ec","print","outdoor","video"]
    region_scope                  jsonb NOT NULL DEFAULT '[]',   -- ["japan","asia","eu","global"]
    product_scope                 jsonb NOT NULL DEFAULT '[]',   -- allowed categories
    prohibited_product_scope      jsonb NOT NULL DEFAULT '[]',   -- prohibited categories
    swimwear_allowed              boolean NOT NULL DEFAULT false,
    underwear_allowed             boolean NOT NULL DEFAULT false,
    bath_allowed                  varchar(12) NOT NULL DEFAULT 'no'
                                    CHECK (bath_allowed IN ('yes','no','conditional')),
    exposure_level_max            integer NOT NULL DEFAULT 0
                                    CHECK (exposure_level_max BETWEEN 0 AND 4),
    face_edit_allowed             boolean NOT NULL DEFAULT false,
    body_edit_allowed             boolean NOT NULL DEFAULT false,
    hair_edit_allowed             boolean NOT NULL DEFAULT false,
    makeup_edit_allowed           boolean NOT NULL DEFAULT false,
    age_appearance_change_allowed boolean NOT NULL DEFAULT false,
    video_allowed                 boolean NOT NULL DEFAULT false,
    secondary_use_allowed         boolean NOT NULL DEFAULT false,
    overseas_allowed              boolean NOT NULL DEFAULT false,
    approval_required_level       varchar(16) NOT NULL DEFAULT 'legal'
                                    CHECK (approval_required_level IN ('internal','legal','agency','person')),
    notes                         text,
    created_at                    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE model_assets (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id                   uuid NOT NULL REFERENCES models(id),
    asset_type                 varchar(16) NOT NULL
                                 CHECK (asset_type IN ('face','body','expression','pose','ng','reference')),
    file_path                  text NOT NULL,
    original_filename          varchar(255),
    file_hash                  varchar(128) NOT NULL,   -- required for every stored file
    usage_type                 varchar(16) NOT NULL
                                 CHECK (usage_type IN ('training','reference','review_only','prohibited')),
    consent_confirmed          boolean NOT NULL DEFAULT false,
    photographer_right_confirmed boolean NOT NULL DEFAULT false,
    quality_score              integer,
    tags                       jsonb NOT NULL DEFAULT '[]',
    is_encrypted               boolean NOT NULL DEFAULT true,
    deleted_at                 timestamptz,             -- soft delete by default
    uploaded_by                uuid REFERENCES users(id),
    created_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE model_ng_rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id    uuid NOT NULL REFERENCES models(id),
    rule_type   varchar(32) NOT NULL,   -- ng_word | ng_pose | ng_scene | ng_product
    value       text NOT NULL,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Projects & requirements
-- ---------------------------------------------------------------------------

CREATE TABLE projects (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_name     varchar(255) NOT NULL,
    client_name      varchar(255),
    brand_name       varchar(255),
    product_name     varchar(255),
    product_category varchar(64),
    owner_user_id    uuid REFERENCES users(id),
    project_status   varchar(16) NOT NULL DEFAULT 'draft'
                       CHECK (project_status IN ('draft','generating','review','approved','delivered','closed')),
    risk_level       varchar(16) CHECK (risk_level IN ('low','middle','high','prohibited')),
    deadline         date,
    deleted_at       timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_requirements (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id             uuid NOT NULL REFERENCES projects(id),
    media                  jsonb NOT NULL DEFAULT '[]',
    region                 jsonb NOT NULL DEFAULT '[]',
    usage_start            date,
    usage_end              date,
    output_type            varchar(16) NOT NULL DEFAULT 'image'
                             CHECK (output_type IN ('image','video')),
    scene_type             varchar(32),
    outfit_type            varchar(32) NOT NULL DEFAULT 'normal',
    exposure_level         integer NOT NULL DEFAULT 0
                             CHECK (exposure_level BETWEEN 0 AND 5),
    secondary_use          boolean NOT NULL DEFAULT false,
    overseas               boolean NOT NULL DEFAULT false,
    pose_description        text,
    expression_description  text,
    background_description  text,
    reference_files        jsonb NOT NULL DEFAULT '[]',
    client_notes           text,
    legal_notes            text
);

CREATE TABLE project_models (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid NOT NULL REFERENCES projects(id),
    model_id    uuid NOT NULL REFERENCES models(id),
    usage_role  varchar(32) NOT NULL DEFAULT 'main',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, model_id)
);

-- ---------------------------------------------------------------------------
-- Compliance checks — authorize (or forbid) generation
-- ---------------------------------------------------------------------------

CREATE TABLE compliance_checks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          uuid NOT NULL REFERENCES projects(id),
    model_id            uuid NOT NULL REFERENCES models(id),
    check_status        varchar(16) NOT NULL
                          CHECK (check_status IN ('ok','conditional','ng','prohibited')),
    risk_level          varchar(16) CHECK (risk_level IN ('low','middle','high','prohibited')),
    matched_permissions jsonb NOT NULL DEFAULT '{}',
    violations          jsonb NOT NULL DEFAULT '[]',
    required_approvals  jsonb NOT NULL DEFAULT '[]',
    check_summary       text,
    engine_version      varchar(32) NOT NULL DEFAULT 'v1',
    checked_by          uuid REFERENCES users(id),
    checked_at          timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Generation — AI engines, jobs, outputs
-- ---------------------------------------------------------------------------

CREATE TABLE ai_engines (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(64) NOT NULL,
    adapter_key varchar(32) NOT NULL,   -- mock | openai | replicate | self_hosted
    training_capable boolean NOT NULL DEFAULT false,
    is_active   boolean NOT NULL DEFAULT true,
    config      jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prompt_templates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(128) NOT NULL,
    body        text NOT NULL,
    negative_body text,
    tags        jsonb NOT NULL DEFAULT '[]',
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE generations (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           uuid NOT NULL REFERENCES projects(id),
    model_id             uuid NOT NULL REFERENCES models(id),
    -- HARD GATE: a generation cannot exist without a compliance check.
    compliance_check_id  uuid NOT NULL REFERENCES compliance_checks(id),
    ai_engine_id         uuid REFERENCES ai_engines(id),
    prompt_text          text NOT NULL,
    negative_prompt_text text,
    prompt_template_id   uuid REFERENCES prompt_templates(id),
    generation_params    jsonb NOT NULL DEFAULT '{}',
    output_count         integer NOT NULL DEFAULT 1,
    status               varchar(16) NOT NULL DEFAULT 'queued'
                           CHECK (status IN ('queued','running','completed','failed')),
    generated_by         uuid REFERENCES users(id),
    generated_at         timestamptz NOT NULL DEFAULT now()
);

-- DB-level enforcement: the linked compliance check must be ok/conditional at
-- insert/update time. (App layer re-validates too — defense in depth.)
CREATE OR REPLACE FUNCTION enforce_generation_gate() RETURNS trigger AS $$
DECLARE
    cc_status text;
    cc_project uuid;
    cc_model uuid;
BEGIN
    SELECT check_status, project_id, model_id
      INTO cc_status, cc_project, cc_model
      FROM compliance_checks WHERE id = NEW.compliance_check_id;

    IF cc_status IS NULL THEN
        RAISE EXCEPTION 'compliance_check % not found', NEW.compliance_check_id;
    END IF;
    IF cc_status NOT IN ('ok','conditional') THEN
        RAISE EXCEPTION 'generation blocked: compliance status is %', cc_status;
    END IF;
    IF cc_project <> NEW.project_id OR cc_model <> NEW.model_id THEN
        RAISE EXCEPTION 'compliance_check does not match project/model';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_generation_gate
    BEFORE INSERT OR UPDATE ON generations
    FOR EACH ROW EXECUTE FUNCTION enforce_generation_gate();

CREATE TABLE generation_outputs (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id          uuid NOT NULL REFERENCES generations(id),
    file_path              text NOT NULL,
    file_hash              varchar(128) NOT NULL,
    thumbnail_path         text,
    width                  integer,
    height                 integer,
    output_status          varchar(16) NOT NULL DEFAULT 'candidate'
                             CHECK (output_status IN ('candidate','selected','rejected','approved','delivered')),
    visual_risk_score      integer,
    face_consistency_score integer,
    quality_score          integer,
    watermark_applied      boolean NOT NULL DEFAULT false,
    c2pa_metadata_applied  boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Review, approval, delivery
-- ---------------------------------------------------------------------------

CREATE TABLE output_reviews (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id   uuid NOT NULL REFERENCES generation_outputs(id),
    reviewer_id uuid REFERENCES users(id),
    review_type varchar(16) NOT NULL,   -- internal | legal | agency | person
    status      varchar(16) NOT NULL
                  CHECK (status IN ('approved','conditional','revise','rejected')),
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE approvals (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id        uuid NOT NULL REFERENCES generation_outputs(id),
    approver_id      uuid REFERENCES users(id),
    approval_level   varchar(16) NOT NULL
                       CHECK (approval_level IN ('internal','legal','agency','person','admin')),
    approval_status  varchar(16) NOT NULL
                       CHECK (approval_status IN ('approved','rejected','revoked')),
    approval_comment text,
    approved_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE deliveries (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     uuid NOT NULL REFERENCES projects(id),
    output_id      uuid NOT NULL REFERENCES generation_outputs(id),
    delivered_to   varchar(255),
    delivery_method varchar(32),
    usage_media    jsonb NOT NULL DEFAULT '[]',
    usage_region   jsonb NOT NULL DEFAULT '[]',
    usage_start    date,
    usage_end      date,
    status         varchar(16) NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','ended','revoked')),
    delivered_by   uuid REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Audit log — append-only trail for every critical action
-- ---------------------------------------------------------------------------

CREATE TABLE audit_logs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid REFERENCES users(id),
    action_type varchar(16) NOT NULL
                  CHECK (action_type IN ('login','logout','create','update','delete',
                                         'generate','download','approve','review','deliver')),
    target_type varchar(32),   -- model | project | output | contract | permission | delivery
    target_id   uuid,
    before_data jsonb,
    after_data  jsonb,
    ip_address  varchar(64),
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_contracts_model        ON model_contracts(model_id);
CREATE INDEX idx_contracts_end          ON model_contracts(contract_end);
CREATE INDEX idx_permissions_model      ON model_permissions(model_id);
CREATE INDEX idx_assets_model           ON model_assets(model_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_requirements_project   ON project_requirements(project_id);
CREATE INDEX idx_project_models_project ON project_models(project_id);
CREATE INDEX idx_checks_project_model   ON compliance_checks(project_id, model_id);
CREATE INDEX idx_generations_project    ON generations(project_id);
CREATE INDEX idx_outputs_generation     ON generation_outputs(generation_id);
CREATE INDEX idx_approvals_output       ON approvals(output_id);
CREATE INDEX idx_audit_target           ON audit_logs(target_type, target_id);
CREATE INDEX idx_audit_user_time        ON audit_logs(user_id, created_at);

COMMIT;
