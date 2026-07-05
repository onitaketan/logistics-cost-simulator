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
import mimetypes
import os
import time
from pathlib import Path
from urllib.parse import quote

from app.core.config import get_settings

# Local backend root (dev). Overridable via STORAGE_DIR env.
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "./storage")).resolve()

# Lazily-created boto3 S3 client, so importing this module needs no credentials
# and the local backend never touches boto3.
_S3_CLIENT = None


def _s3_client():
    """Build (and cache) an S3-compatible boto3 client from settings.

    Works for both AWS S3 and Cloudflare R2 (R2 speaks the S3 API via a custom
    ``storage_endpoint_url``). Created lazily on first use.
    """
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3  # imported here so module import needs no boto3/credentials

        settings = get_settings()
        # No region field on Settings; allow an env override, else a sane default.
        region = os.environ.get("STORAGE_REGION", "us-east-1")
        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=region,
        )
    return _S3_CLIENT


def _reset_s3_client() -> None:
    """Drop the cached client (used by tests after changing settings)."""
    global _S3_CLIENT
    _S3_CLIENT = None


def _sse_algorithm(settings) -> str | None:
    """Server-side-encryption algorithm to request on upload, or None.

    S3 supports SSE-S3 (``AES256``) out of the box, so we default it on. R2 (and
    other custom endpoints) may reject the SSE header — R2 encrypts at rest
    transparently — so SSE is best-effort there and off by default. Either can be
    overridden with the ``STORAGE_SSE`` env var ("AES256", "aws:kms", or "none").
    """
    override = os.environ.get("STORAGE_SSE")
    if override is not None:
        override = override.strip()
        return None if override.lower() in ("", "none", "off", "0") else override
    # Default: SSE on for AWS S3, off for R2 / any custom endpoint.
    if settings.storage_provider == "s3" and not settings.storage_endpoint_url:
        return "AES256"
    return None


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
        uri = f"s3://{settings.storage_bucket}/{key}"
        extra: dict[str, str] = {"ACL": "private"}
        content_type, _ = mimetypes.guess_type(key)
        if content_type:
            extra["ContentType"] = content_type
        if encrypt:
            sse = _sse_algorithm(settings)
            if sse:
                extra["ServerSideEncryption"] = sse
        client = _s3_client()
        try:
            client.put_object(
                Bucket=settings.storage_bucket, Key=key, Body=data, **extra
            )
        except Exception:
            # SSE is best-effort on custom endpoints (R2 may reject the header);
            # retry once without it before giving up.
            if "ServerSideEncryption" in extra:
                extra.pop("ServerSideEncryption")
                client.put_object(
                    Bucket=settings.storage_bucket, Key=key, Body=data, **extra
                )
            else:
                raise
    else:
        raise ValueError(f"unknown storage provider: {settings.storage_provider}")

    return uri, file_hash


def _parse_object_uri(file_uri: str) -> tuple[str, str]:
    """Split ``<scheme>://<bucket>/<key>`` into (bucket, key)."""
    _, _, rest = file_uri.partition("://")
    bucket, _, key = rest.partition("/")
    return bucket, key


def read(file_uri: str) -> bytes:
    """Fetch stored bytes (used by the gated download-stream endpoint)."""
    settings = get_settings()
    if settings.storage_provider == "local":
        _, _, rest = file_uri.partition("://")
        bucket, _, key = rest.partition("/")
        return _local_path(bucket, key).read_bytes()
    if settings.storage_provider in ("s3", "r2"):
        bucket, key = _parse_object_uri(file_uri)
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    raise ValueError(f"unknown storage provider: {settings.storage_provider}")


def signed_url(file_uri: str) -> str:
    """Return a short-lived signed reference. Demonstrates the no-public-access rule.

    For local: an HMAC token with expiry (verify_signed_token). For s3/r2: a
    boto3 presigned GET URL that expires after ``signed_url_ttl_seconds`` — the
    object itself stays private, so this is the only way to read it.
    """
    settings = get_settings()

    if settings.storage_provider in ("s3", "r2"):
        bucket, key = _parse_object_uri(file_uri)
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=settings.signed_url_ttl_seconds,
        )

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
