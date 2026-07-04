"""Storage abstraction.

Every stored file gets a SHA-256 hash (CLAUDE.md). Raw images are never publicly
reachable: reads go through short-lived signed URLs. This module provides a real
local-filesystem backend for dev, and a clear seam for S3/R2 (SSE) in production.

Path convention: `store()` returns a logical URI `"<provider>://<bucket>/<key>"`.
For the local backend the bytes live under `STORAGE_DIR/<bucket>/<key>`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path
from urllib.parse import quote

from app.core.config import get_settings

# Local backend root (dev). Overridable via STORAGE_DIR env.
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "./storage")).resolve()


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_path(bucket: str, key: str) -> Path:
    # Prevent path traversal outside the bucket root.
    root = (STORAGE_DIR / bucket).resolve()
    target = (root / key).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("invalid storage key")
    return target


def store(data: bytes, *, key: str, encrypt: bool = True) -> tuple[str, str]:
    """Persist bytes; return (file_uri, file_hash).

    encrypt=True is a marker for at-rest encryption. Real SSE happens provider-side
    (S3 SSE-KMS / R2). The local backend stores plaintext but records the intent
    on the asset row; do not use the local backend for real personal data.
    """
    settings = get_settings()
    file_hash = compute_hash(data)
    uri = f"{settings.storage_provider}://{settings.storage_bucket}/{key}"

    if settings.storage_provider == "local":
        path = _local_path(settings.storage_bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    elif settings.storage_provider in ("s3", "r2"):
        raise NotImplementedError(
            "S3/R2 backend not wired yet — add boto3 client here (SSE-KMS, private ACL)."
        )
    else:
        raise ValueError(f"unknown storage provider: {settings.storage_provider}")

    return uri, file_hash


def read(file_uri: str) -> bytes:
    """Fetch stored bytes (used by the gated download-stream endpoint)."""
    settings = get_settings()
    if settings.storage_provider == "local":
        _, _, rest = file_uri.partition("://")
        bucket, _, key = rest.partition("/")
        return _local_path(bucket, key).read_bytes()
    raise NotImplementedError("read() only implemented for local backend")


def signed_url(file_uri: str) -> str:
    """Return a short-lived signed reference. Demonstrates the no-public-access rule.

    For local: an HMAC token with expiry (verify_signed_token) — a real object
    store would return a provider-presigned URL instead.
    """
    settings = get_settings()
    exp = int(time.time()) + settings.signed_url_ttl_seconds
    msg = f"{file_uri}|{exp}".encode()
    sig = hmac.new(settings.api_secret_key.encode(), msg, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"/api/v1/files?uri={quote(file_uri)}&exp={exp}&sig={token}"


def verify_signed_token(file_uri: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    settings = get_settings()
    msg = f"{file_uri}|{exp}".encode()
    expected = hmac.new(settings.api_secret_key.encode(), msg, hashlib.sha256).digest()
    expected_token = base64.urlsafe_b64encode(expected).decode().rstrip("=")
    return hmac.compare_digest(expected_token, sig)
