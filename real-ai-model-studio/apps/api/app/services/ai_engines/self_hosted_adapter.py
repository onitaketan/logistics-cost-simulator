"""Self-hosted image engine adapter (P2-005) — fully offline generation.

Talks to a Stable Diffusion WebUI (AUTOMATIC1111)-compatible HTTP API running on
the SAME machine / LAN (``/sdapi/v1/txt2img``). Prompts and generated images
never leave the host: this is the engine to use under OFFLINE_MODE, where the
external (openai / replicate) adapters are refused at the registry.

Setup (operator-provided, once):
  1. Run Stable Diffusion WebUI locally with the API enabled:  ``--api``
     (default listen: http://127.0.0.1:7860)
  2. Point this adapter at it:  ``SELF_HOSTED_BASE_URL=http://host.docker.internal:7860``
     (Docker; the compose file maps host.docker.internal on Linux too) or
     ``http://127.0.0.1:7860`` for a venv-run API.

The compliance gate runs upstream in generation_service before any adapter is
constructed — nothing here weakens it. Testability mirrors the other adapters:
the httpx client is injectable (MockTransport in tests; no network needed).
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

from app.services.ai_engines.base import (
    AIEngineAdapter,
    AIEngineError,
    GeneratedImage,
)


class SelfHostedAdapter(AIEngineAdapter):
    """Adapter for an AUTOMATIC1111-compatible local inference server."""

    training_capable = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        self._client = client
        self._base_url = (base_url or os.environ.get("SELF_HOSTED_BASE_URL") or "").rstrip("/")

    def _require_base_url(self) -> str:
        if not self._base_url:
            raise AIEngineError(
                "self_hosted engine: SELF_HOSTED_BASE_URL が未設定です。"
                "ローカル生成サーバ（例: Stable Diffusion WebUI --api）のURLを指定してください。"
            )
        return self._base_url

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._require_base_url()}{path}"
        try:
            if self._client is not None:
                resp = await self._client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=300.0) as client:  # local GPU can be slow
                    resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise AIEngineError(
                f"self_hosted engine unreachable at {url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise AIEngineError(
                f"self_hosted engine error {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise AIEngineError("self_hosted engine returned non-JSON response") from exc

    @staticmethod
    def _seed_of(body: dict[str, Any]) -> int | None:
        # A1111 puts the actual seed inside the JSON-encoded "info" string.
        info = body.get("info")
        if isinstance(info, str):
            try:
                return json.loads(info).get("seed")
            except (ValueError, AttributeError):
                return None
        return None

    def _images_from(self, body: dict[str, Any], width: int, height: int) -> list[GeneratedImage]:
        images = body.get("images") or []
        if not images:
            raise AIEngineError("self_hosted engine returned no images")
        seed = self._seed_of(body)
        out: list[GeneratedImage] = []
        for i, b64 in enumerate(images):
            try:
                data = base64.b64decode(b64)
            except Exception as exc:  # malformed b64 from the server
                raise AIEngineError("self_hosted engine returned invalid image data") from exc
            out.append(GeneratedImage(
                file_path=f"self_hosted://b64/{i}.png",
                width=width, height=height, seed=seed, data=data,
            ))
        return out

    async def generate_image(self, prompt: str, params: dict[str, Any]) -> list[GeneratedImage]:
        width = int(params.get("width", 1024))
        height = int(params.get("height", 1024))
        payload = {
            "prompt": prompt,
            "negative_prompt": params.get("negative_prompt") or "",
            "width": width,
            "height": height,
            "batch_size": int(params.get("output_count", 1)),
            "seed": int(params.get("seed", -1)),
            "steps": int(params.get("steps", 28)),
        }
        body = await self._post("/sdapi/v1/txt2img", payload)
        return self._images_from(body, width, height)

    async def revise_image(
        self, image_path: str, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        # MVP revision = a fresh txt2img driven by the revision prompt (mirrors the
        # other adapters). img2img with the stored source image is a follow-up.
        return await self.generate_image(prompt, params)
