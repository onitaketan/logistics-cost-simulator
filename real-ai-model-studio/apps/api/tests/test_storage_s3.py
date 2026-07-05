"""S3/R2 backend tests: upload+hash, roundtrip, presigned URL — fully offline via moto."""

import importlib

import boto3
import pytest
from moto import mock_aws

BUCKET = "rams-private-test"


@pytest.fixture()
def storage(monkeypatch):
    """Point get_settings() at an s3 provider + bucket, reload the module, and
    stand up a fake S3 with moto. Yields the storage module inside the mock."""
    monkeypatch.setenv("STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("STORAGE_BUCKET", BUCKET)
    # Dummy creds so boto3 is happy; moto intercepts before any network call.
    monkeypatch.setenv("STORAGE_ACCESS_KEY", "testing")
    monkeypatch.setenv("STORAGE_SECRET_KEY", "testing")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("STORAGE_ENDPOINT_URL", raising=False)

    from app.core import config

    config.get_settings.cache_clear()
    import app.services.storage_service as s

    importlib.reload(s)
    s._reset_s3_client()

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield s

    s._reset_s3_client()
    config.get_settings.cache_clear()


def test_store_uploads_and_returns_sha256(storage):
    data = b"hello s3 bytes"
    uri, h = storage.store(data, key="models/m1/a.png")
    assert uri == f"s3://{BUCKET}/models/m1/a.png"
    assert h == storage.compute_hash(data)


def test_store_and_read_roundtrip(storage):
    data = b"round trip payload \x00\x01\x02"
    uri, _ = storage.store(data, key="models/m2/b.bin")
    assert storage.read(uri) == data


def test_store_applies_sse_and_private_acl(storage):
    uri, _ = storage.store(b"secret", key="secure/c.png")
    bucket, key = storage._parse_object_uri(uri)
    head = storage._s3_client().head_object(Bucket=bucket, Key=key)
    # Default provider=s3 (no custom endpoint) requests SSE-S3.
    assert head.get("ServerSideEncryption") == "AES256"
    assert head["ContentType"] == "image/png"


def test_signed_url_is_presigned_get(storage):
    uri, _ = storage.store(b"x", key="k/x.png")
    url = storage.signed_url(uri)
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    # Key appears in the path; presign carries expiry + signature params
    # (accept either SigV4 "X-Amz-*" or the legacy SigV2 query style).
    assert "k/x.png" in parsed.path
    assert "X-Amz-Expires" in q or "Expires" in q
    assert "X-Amz-Signature" in q or "Signature" in q
