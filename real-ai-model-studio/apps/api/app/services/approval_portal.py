"""External approval portal service (P2-001/P2-002).

Issues single-use, expiring, hash-stored tokens so an agency or the person can
record an approval decision on ONE output without a system login. Kept small and
DB-light: the router owns orchestration/audit, this owns token handling and the
active-state check.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.workflow import ApprovalRequest


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue(
    db, *, output_id: str, level: str, contact_name: str | None,
    contact_email: str | None, expires_in_days: int, created_by: str | None,
) -> tuple[ApprovalRequest, str]:
    """Create a request row and return (row, raw_token). The raw token is shown
    to the issuer ONCE (embedded in the link); only its hash is persisted."""
    token = secrets.token_urlsafe(32)
    ar = ApprovalRequest(
        output_id=output_id,
        level=level,
        token_hash=hash_token(token),
        contact_name=contact_name,
        contact_email=contact_email,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        created_by=created_by,
        status="pending",
    )
    db.add(ar)
    db.flush()
    return ar, token


def resolve(db, token: str) -> ApprovalRequest | None:
    return db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.token_hash == hash_token(token))
    )


def is_open(ar: ApprovalRequest) -> bool:
    """True when the request can still be viewed/decided (pending & unexpired)."""
    if ar.status != "pending":
        return False
    expires = ar.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)
