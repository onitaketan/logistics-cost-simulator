"""Role-Based Access Control matrix.

Roles: admin, legal, sales, creative, approver, viewer (docs/01_requirements.md).
Permissions are coarse-grained capabilities checked by API dependencies. The
matrix is intentionally explicit and data-driven so it can be unit-tested and
audited. Default is deny.
"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    LEGAL = "legal"
    SALES = "sales"
    CREATIVE = "creative"
    APPROVER = "approver"
    VIEWER = "viewer"


class Perm(StrEnum):
    # user & system
    USER_MANAGE = "user.manage"
    AUDIT_VIEW = "audit.view"
    SETTINGS_MANAGE = "settings.manage"
    # model / contract / permission
    MODEL_VIEW = "model.view"
    MODEL_EDIT = "model.edit"
    CONTRACT_MANAGE = "contract.manage"      # contracts, permissions, adult verification
    ASSET_UPLOAD = "asset.upload"
    # project
    PROJECT_VIEW = "project.view"
    PROJECT_EDIT = "project.edit"
    # compliance & generation
    COMPLIANCE_RUN = "compliance.run"
    GENERATE = "generate"
    # review / approval / delivery
    REVIEW = "review"
    APPROVE_INTERNAL = "approve.internal"
    APPROVE_LEGAL = "approve.legal"
    APPROVE_ADMIN = "approve.admin"
    DELIVER = "deliver"
    DOWNLOAD = "download"


_MATRIX: dict[Role, set[Perm]] = {
    Role.ADMIN: set(Perm),  # everything, EXCEPT overriding Prohibited (enforced in engine)
    Role.LEGAL: {
        Perm.MODEL_VIEW, Perm.MODEL_EDIT, Perm.CONTRACT_MANAGE, Perm.ASSET_UPLOAD,
        Perm.PROJECT_VIEW, Perm.COMPLIANCE_RUN, Perm.REVIEW,
        Perm.APPROVE_INTERNAL, Perm.APPROVE_LEGAL, Perm.AUDIT_VIEW, Perm.DOWNLOAD,
    },
    Role.SALES: {
        Perm.MODEL_VIEW, Perm.PROJECT_VIEW, Perm.PROJECT_EDIT,
        Perm.COMPLIANCE_RUN, Perm.DELIVER,
    },
    Role.CREATIVE: {
        Perm.MODEL_VIEW, Perm.ASSET_UPLOAD, Perm.PROJECT_VIEW,
        Perm.COMPLIANCE_RUN, Perm.GENERATE, Perm.REVIEW,
    },
    Role.APPROVER: {
        Perm.MODEL_VIEW, Perm.PROJECT_VIEW, Perm.REVIEW, Perm.APPROVE_INTERNAL,
    },
    Role.VIEWER: {
        Perm.MODEL_VIEW, Perm.PROJECT_VIEW,
    },
}


def has_permission(role: str, perm: Perm) -> bool:
    try:
        return perm in _MATRIX[Role(role)]
    except ValueError:
        return False
