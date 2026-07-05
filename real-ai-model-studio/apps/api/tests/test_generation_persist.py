"""The worker's image-persistence glue (offline, no DB, no network).

Proves that when an adapter returns real image bytes, the worker stores them via
the storage service and records the sha256 of the ACTUAL bytes — not a URL string
(CLAUDE.md #6 + the file_hash rule). The mock placeholder path is also covered.
"""

import hashlib
import importlib

import pytest

from app.services.ai_engines.base import GeneratedImage


@pytest.fixture()
def worker(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    from app.core import config
    config.get_settings.cache_clear()
    import app.services.storage_service as s
    importlib.reload(s)
    import app.workers.generation_worker as w
    importlib.reload(w)
    return w, s


def test_inline_bytes_are_stored_and_hashed(worker):
    w, storage = worker
    raw = b"\x89PNG\r\n real image bytes"
    img = GeneratedImage(file_path="openai://b64/0.png", width=1024, height=1280, data=raw)

    uri, file_hash = w._persist_image(img, "gen-123", 0)

    assert uri.endswith("generations/gen-123/0.png")     # stored in OUR storage
    assert file_hash == hashlib.sha256(raw).hexdigest()  # hash of the real bytes
    assert storage.read(uri) == raw                      # bytes actually persisted


def test_mock_placeholder_keeps_path(worker):
    w, _ = worker
    img = GeneratedImage(file_path="mock://generated/0.png", width=1024, height=1024)
    uri, file_hash = w._persist_image(img, "gen-9", 0)
    assert uri == "mock://generated/0.png"
    assert file_hash == hashlib.sha256(b"mock://generated/0.png").hexdigest()


def test_source_url_download_is_stored(worker, monkeypatch):
    w, storage = worker
    raw = b"downloaded-bytes"

    class _Resp:
        content = raw
        def raise_for_status(self):  # noqa: D401
            return None

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())

    img = GeneratedImage(file_path="https://provider.example/x.png",
                         width=512, height=512, source_url="https://provider.example/x.png")
    uri, file_hash = w._persist_image(img, "gen-7", 2)
    assert uri.endswith("generations/gen-7/2.png")
    assert file_hash == hashlib.sha256(raw).hexdigest()
    assert storage.read(uri) == raw
