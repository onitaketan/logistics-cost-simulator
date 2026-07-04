"""Storage backend tests (local): hashing, roundtrip, signed-token, traversal guard."""

import importlib

import pytest


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    from app.core import config
    config.get_settings.cache_clear()
    import app.services.storage_service as s
    importlib.reload(s)
    return s


def test_hash_is_sha256(storage):
    assert storage.compute_hash(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_store_and_read_roundtrip(storage):
    uri, h = storage.store(b"hello bytes", key="models/m1/a.png")
    assert uri.endswith("/models/m1/a.png")
    assert h == storage.compute_hash(b"hello bytes")
    assert storage.read(uri) == b"hello bytes"


def test_signed_token_valid_then_verifies(storage):
    uri, _ = storage.store(b"x", key="k/x.png")
    url = storage.signed_url(uri)
    # parse exp & sig back out
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(url).query)
    assert storage.verify_signed_token(uri, int(q["exp"][0]), q["sig"][0]) is True


def test_signed_token_rejects_tampering(storage):
    uri, _ = storage.store(b"x", key="k/x.png")
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(storage.signed_url(uri)).query)
    assert storage.verify_signed_token(uri, int(q["exp"][0]), "deadbeef") is False


def test_signed_token_expired(storage):
    uri, _ = storage.store(b"x", key="k/x.png")
    # exp in the past must not verify even with a correct-shaped sig
    assert storage.verify_signed_token(uri, 1, "anything") is False


def test_path_traversal_blocked(storage):
    with pytest.raises(ValueError):
        storage.store(b"x", key="../../etc/passwd")
