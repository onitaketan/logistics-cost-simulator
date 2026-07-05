"""OpenAI Images adapter (gpt-image-1 / DALL·E-style HTTP API).

Talks to the OpenAI Images API over HTTP with ``httpx.AsyncClient``.

Content policy: OpenAI's usage policies and content filters must be respected;
the provider may itself refuse a prompt. That is *in addition to* — never a
substitute for — this system's own compliance gate, which runs upstream in
``generation_service`` before any adapter here is ever constructed or called.
Nothing in this module weakens or bypasses that gate.

Testability: the HTTP client, base URL, and the download seam are all injectable
so the adapter can be exercised fully offline (see ``tests/test_ai_engines.py``).
No real network call is made unless a live ``httpx.AsyncClient`` reaches a real
endpoint.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.ai_engines.base import (
    AIEngineAdapter,
    AIEngineError,
    GeneratedImage,
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-image-1"


class OpenAIAdapter(AIEngineAdapter):
    """Adapter for the OpenAI Images API.

    Args:
        client: optional pre-built ``httpx.AsyncClient``. When supplied, the
            adapter uses it and never closes it (caller owns its lifecycle). When
            omitted, a client is created per request and closed afterwards. Inject
            a client backed by ``httpx.MockTransport`` for offline tests.
        base_url: override the API root (defaults to the public OpenAI endpoint).
        api_key: override the key; otherwise read from the environment.
        model: image model identifier.
    """

    training_capable = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._client = client
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        # Do NOT import app.core.config — read the key straight from the env.
        self._api_key = (
            api_key
            or os.environ.get("AI_ENGINE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self._model = model

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _size(params: dict[str, Any]) -> tuple[int, int, str]:
        w = int(params.get("width", 1024))
        h = int(params.get("height", 1024))
        return w, h, f"{w}x{h}"

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIEngineError(
                "OpenAI API key missing: set AI_ENGINE_API_KEY or OPENAI_API_KEY"
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _download(self, entry: dict[str, Any], index: int) -> str:
        """Resolve a single API result entry to a stored image location.

        Seam intentionally kept trivial and side-effect-free so it can be
        overridden to persist bytes via the storage service (owned elsewhere).
        The OpenAI response returns either a ``url`` (DALL·E) or ``b64_json``
        (gpt-image-1); we return a location string in both cases.
        """
        url = entry.get("url")
        if url:
            return str(url)
        if entry.get("b64_json"):
            # Base64 payload — hand back an addressable location. A production
            # override persists the decoded bytes through storage_service.
            return f"openai://b64/{index}.png"
        raise AIEngineError("OpenAI response entry had neither 'url' nor 'b64_json'")

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            resp = await self._client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers()
            )
            return self._parse(resp)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers()
            )
            return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:  # noqa: BLE001 - body may not be JSON
                pass
            raise AIEngineError(f"OpenAI API error {resp.status_code}: {detail}")
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AIEngineError(f"OpenAI API returned non-JSON body: {exc}") from exc

    # -------------------------------------------------------------- public API
    async def generate_image(
        self, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        w, h, size = self._size(params)
        n = int(params.get("output_count", 1))
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        data = await self._post("/images/generations", payload)
        entries = data.get("data") or []
        images: list[GeneratedImage] = []
        for i, entry in enumerate(entries):
            location = await self._download(entry, i)
            images.append(GeneratedImage(file_path=location, width=w, height=h, seed=None))
        if not images:
            raise AIEngineError("OpenAI API returned no images")
        return images

    async def revise_image(
        self, image_path: str, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        w, h, size = self._size(params)
        n = int(params.get("output_count", 1))
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "image": image_path,
        }
        data = await self._post("/images/edits", payload)
        entries = data.get("data") or []
        images: list[GeneratedImage] = []
        for i, entry in enumerate(entries):
            location = await self._download(entry, i)
            images.append(GeneratedImage(file_path=location, width=w, height=h, seed=None))
        if not images:
            raise AIEngineError("OpenAI API returned no images")
        return images
