"""Offline-by-default spec — verification.

生成物・プロンプトを一切オンラインに出さない既定仕様:
  * OFFLINE_MODE は既定で ON。外部エンジン (openai/replicate) は registry で拒否。
  * self_hosted / mock はオフラインでも解決できる（どちらもローカル完結）。
  * 起動時整合チェック: OFFLINE_MODE + 外部エンジン / s3・r2 保存は起動拒否。
  * OFFLINE_MODE=false を明示したときだけ外部が解禁される。
  * self_hosted アダプタは A1111 互換 API (/sdapi/v1/txt2img) から実画像バイトを返す。

No network, no DB — httpx.MockTransport / pure Settings objects only.
"""

import asyncio
import base64

import httpx
import pytest

from app.core import config
from app.core.config import Settings
from app.services.ai_engines import get_adapter
from app.services.ai_engines.base import AIEngineAdapter, AIEngineError
from app.services.ai_engines.self_hosted_adapter import SelfHostedAdapter

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _run(coro):
    return asyncio.run(coro)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------ registry guard
def test_external_engines_refused_by_default(monkeypatch):
    monkeypatch.delenv("OFFLINE_MODE", raising=False)
    config.get_settings.cache_clear()
    try:
        for key in ("openai", "replicate"):
            with pytest.raises(AIEngineError):
                get_adapter(key)
    finally:
        config.get_settings.cache_clear()


def test_local_engines_allowed_offline(monkeypatch):
    monkeypatch.delenv("OFFLINE_MODE", raising=False)
    config.get_settings.cache_clear()
    try:
        assert isinstance(get_adapter("mock"), AIEngineAdapter)
        assert isinstance(get_adapter("self_hosted"), SelfHostedAdapter)
    finally:
        config.get_settings.cache_clear()


def test_explicit_opt_out_allows_external(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    config.get_settings.cache_clear()
    try:
        assert isinstance(get_adapter("openai"), AIEngineAdapter)
    finally:
        config.get_settings.cache_clear()


# ------------------------------------------------------- startup consistency
def test_startup_refuses_external_engine_when_offline():
    s = Settings(offline_mode=True, ai_engine="openai")
    with pytest.raises(RuntimeError):
        s.enforce_offline_consistency()


def test_startup_refuses_cloud_storage_when_offline():
    s = Settings(offline_mode=True, storage_provider="s3")
    with pytest.raises(RuntimeError):
        s.enforce_offline_consistency()


def test_startup_allows_local_stack_when_offline():
    Settings(offline_mode=True, ai_engine="self_hosted",
             storage_provider="local").enforce_offline_consistency()
    Settings(offline_mode=True, ai_engine="mock").enforce_offline_consistency()


def test_startup_allows_external_when_opted_out():
    Settings(offline_mode=False, ai_engine="openai",
             storage_provider="s3").enforce_offline_consistency()


# ------------------------------------------------------ self_hosted adapter
def test_self_hosted_generate_returns_real_bytes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content)
        n = seen["payload"]["batch_size"]
        return httpx.Response(200, json={
            "images": [base64.b64encode(PNG_1PX).decode() for _ in range(n)],
            "info": "{\"seed\": 4242}",
        })

    adapter = SelfHostedAdapter(client=_client(handler), base_url="http://127.0.0.1:7860")
    images = _run(adapter.generate_image(
        "上品なスタジオ照明", {"output_count": 2, "width": 512, "height": 768,
                               "negative_prompt": "低品質"}))
    assert seen["path"] == "/sdapi/v1/txt2img"
    assert seen["payload"]["negative_prompt"] == "低品質"
    assert len(images) == 2
    assert all(img.data == PNG_1PX for img in images)
    assert images[0].width == 512 and images[0].height == 768
    assert images[0].seed == 4242


def test_self_hosted_requires_base_url(monkeypatch):
    monkeypatch.delenv("SELF_HOSTED_BASE_URL", raising=False)
    adapter = SelfHostedAdapter()
    with pytest.raises(AIEngineError):
        _run(adapter.generate_image("x", {}))


def test_self_hosted_server_error_is_engine_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    adapter = SelfHostedAdapter(client=_client(handler), base_url="http://127.0.0.1:7860")
    with pytest.raises(AIEngineError):
        _run(adapter.generate_image("x", {}))


def test_self_hosted_empty_images_is_engine_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"images": []})

    adapter = SelfHostedAdapter(client=_client(handler), base_url="http://127.0.0.1:7860")
    with pytest.raises(AIEngineError):
        _run(adapter.generate_image("x", {}))
