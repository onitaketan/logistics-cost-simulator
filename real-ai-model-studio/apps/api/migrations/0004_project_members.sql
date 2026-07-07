-- 0004: project membership for data-scoped authorization.
--
-- Role permissions (rbac.py) say WHAT an action needs; membership says WHICH
-- projects a non-governance user may act on. admin/legal keep system-wide
-- visibility (compliance/legal oversight); everyone else is limited to projects
-- they own or are members of. The project creator is auto-added as a member.

CREATE TABLE project_members (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid NOT NULL REFERENCES projects(id),
    user_id         uuid NOT NULL REFERENCES users(id),
    role_in_project varchar(32),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, user_id)
);

CREATE INDEX idx_project_members_project ON project_members(project_id);
CREATE INDEX idx_project_members_user    ON project_members(user_id);
