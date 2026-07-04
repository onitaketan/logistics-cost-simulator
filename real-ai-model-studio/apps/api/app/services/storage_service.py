"""Storage abstraction. Every stored file gets a SHA-256 hash (CLAUDE.md).

MVP implements a local backend; S3/R2 slot in behind the same interface. Raw
images must never be publicly reachable — reads are via short-lived signed URLs
(SIGNED_URL_TTL_SECONDS). This scaffold returns placeholders for the remote path.
"""

from __future__ import annotations

import hashlib

from app.core.config import get_settings


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store(data: bytes, *, key: str, encrypt: bool = True) -> tuple[str, str]:
    """Persist bytes; return (file_path, file_hash).

    TODO(Phase 1): implement local disk + S3/R2 (SSE) backends. For now returns a
    logical path so upstream code and the DB contract can be exercised.
    """
    settings = get_settings()
    file_hash = compute_hash(data)
    file_path = f"{settings.storage_provider}://{settings.storage_bucket}/{key}"
    return file_path, file_hash


def signed_url(file_path: str) -> str:
    """Return a short-lived read URL. Placeholder until storage backend is wired."""
    ttl = get_settings().signed_url_ttl_seconds
    return f"{file_path}?ttl={ttl}&sig=PLACEHOLDER"
