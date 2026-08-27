"""Offline, deterministic tests for the AI engine adapters and registry.

No network and no DB: every HTTP call is served by an in-process
``httpx.MockTransport`` injected into an ``httpx.AsyncClient``. Async coroutines
are driven with ``asyncio.run`` (the project has no pytest-asyncio plugin).
"""

import asyncio

import httpx
import pytest

from app.services.ai_engines import get_adapter
from app.services.ai_engines.base import (
    AIEngineAdapter,
    AIEngineError,
    GeneratedImage,
)
from app.services.ai_engines.openai_adapter import OpenAIAdapter
from app.services.ai_engines.replicate_adapter import ReplicateAdapter


def _run(coro):
    return asyncio.run(coro)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------- registry
def test_registry_returns_instances(monkeypatch):
    # External engines resolve only once OFFLINE_MODE is explicitly opted out
    # (offline-by-default spec); see test_offline_mode.py for the guard itself.
    from app.core import config

    monkeypatch.setenv("OFFLINE_MODE", "false")
    config.get_settings.cache_clear()
    try:
        assert isinstance(get_adapter("openai"), OpenAIAdapter)
        assert isinstance(get_adapter("replicate"), ReplicateAdapter)
        # mock must survive
        assert isinstance(get_adapter("mock"), AIEngineAdapter)
    finally:
        config.get_settings.cache_clear()


def test_registry_unknown_key_raises_value_error():
    with pytest.raises(ValueError):
        get_adapter("does-not-exist")


# ----------------------------------------------------------------------- OpenAI
def test_openai_generate_returns_expected_count_and_sizes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content)
        n = seen["payload"]["n"]
        return httpx.Response(
            200,
            json={"data": [{"url": f"https://img.example/{i}.png"} for i in range(n)]},
        )

    adapter = OpenAIAdapter(client=_client(handler), api_key="test-key")
    params = {"output_count": 3, "width": 512, "height": 768}
    images = _run(adapter.generate_image("a portrait", params))

    assert len(images) == 3
    assert all(isinstance(img, GeneratedImage) for img in images)
    assert all(img.width == 512 and img.height == 768 for img in images)
    assert images[0].file_path == "https://img.example/0.png"
    # params correctly mapped onto the request
    assert seen["path"].endswith("/images/generations")
    assert seen["payload"]["size"] == "512x768"
    assert seen["payload"]["n"] == 3


def test_openai_handles_b64_entries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": "AAAA"}]})

    adapter = OpenAIAdapter(client=_client(handler), api_key="k")
    images = _run(adapter.generate_image("p", {"output_count": 1}))
    assert len(images) == 1
    assert images[0].file_path == "openai://b64/0.png"


def test_openai_error_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad prompt"}})

    adapter = OpenAIAdapter(client=_client(handler), api_key="k")
    with pytest.raises(AIEngineError) as exc:
        _run(adapter.generate_image("p", {"output_count": 1}))
    assert "bad prompt" in str(exc.value)


def test_openai_missing_key_raises():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200, json={"data": []})

    adapter = OpenAIAdapter(client=_client(handler), api_key="")
    with pytest.raises(AIEngineError):
        _run(adapter.generate_image("p", {"output_count": 1}))


def test_openai_reads_api_key_from_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_ENGINE_API_KEY", "from-env")
    adapter = OpenAIAdapter()
    assert adapter._api_key == "from-env"


# -------------------------------------------------------------------- Replicate
def test_replicate_create_poll_and_collect_outputs():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "status": "processing",
                    "urls": {"get": "https://api.replicate.test/v1/predictions/abc"},
                },
            )
        # GET poll: pending once, then succeeded
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(200, json={"status": "processing", "urls": {"get": "https://api.replicate.test/v1/predictions/abc"}})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "output": ["https://out.example/0.png", "https://out.example/1.png"],
            },
        )

    adapter = ReplicateAdapter(
        client=_client(handler), api_token="tok", poll_interval=0
    )
    images = _run(adapter.generate_image("p", {"output_count": 2, "width": 1024, "height": 1024}))
    assert len(images) == 2
    assert images[1].file_path == "https://out.example/1.png"
    assert all(img.width == 1024 and img.height == 1024 for img in images)


def test_replicate_failed_prediction_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"status": "failed", "error": "nsfw filtered"})
        return httpx.Response(200, json={"status": "failed", "error": "nsfw filtered"})

    adapter = ReplicateAdapter(client=_client(handler), api_token="tok", poll_interval=0)
    with pytest.raises(AIEngineError) as exc:
        _run(adapter.generate_image("p", {"output_count": 1}))
    assert "nsfw filtered" in str(exc.value)


def test_replicate_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    adapter = ReplicateAdapter(client=_client(handler), api_token="tok", poll_interval=0)
    with pytest.raises(AIEngineError):
        _run(adapter.generate_image("p", {"output_count": 1}))


def test_replicate_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "rep-env")
    adapter = ReplicateAdapter()
    assert adapter._api_token == "rep-env"
