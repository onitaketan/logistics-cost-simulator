"""Replicate adapter (predictions API: create -> poll -> collect output URLs).

Talks to Replicate over HTTP with ``httpx.AsyncClient``.

Content policy: the underlying hosted model on Replicate has its own acceptable
use terms that must be respected. That is *in addition to* — never a substitute
for — this system's compliance gate, which runs upstream in
``generation_service`` before any adapter here is constructed or called. Nothing
here weakens or bypasses that gate.

Testability: the HTTP client, base URL, model version, and poll interval are all
injectable so the create/poll loop can be exercised fully offline (see
``tests/test_ai_engines.py``).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from app.services.ai_engines.base import (
    AIEngineAdapter,
    AIEngineError,
    GeneratedImage,
)

DEFAULT_BASE_URL = "https://api.replicate.com/v1"
# Default SDXL-family version; override per deployment.
DEFAULT_VERSION = "stability-ai/sdxl"
_TERMINAL = {"succeeded", "failed", "canceled"}


class ReplicateAdapter(AIEngineAdapter):
    """Adapter for Replicate's predictions API.

    Args:
        client: optional pre-built ``httpx.AsyncClient`` (caller owns lifecycle,
            not closed by the adapter). Omit to create one per request. Inject a
            client backed by ``httpx.MockTransport`` for offline tests.
        base_url: override the API root.
        api_token: override the token; otherwise read from the environment.
        version: Replicate model version to run.
        poll_interval: seconds between status polls (0 in tests for speed).
        max_polls: safety cap on the number of poll iterations.
    """

    training_capable = False

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        api_token: str | None = None,
        version: str = DEFAULT_VERSION,
        poll_interval: float = 1.5,
        max_polls: int = 120,
    ) -> None:
        self._client = client
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        # Do NOT import app.core.config — read the token straight from the env.
        self._api_token = api_token or os.environ.get("REPLICATE_API_TOKEN")
        self._version = version
        self._poll_interval = poll_interval
        self._max_polls = max_polls

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _size(params: dict[str, Any]) -> tuple[int, int]:
        return int(params.get("width", 1024)), int(params.get("height", 1024))

    def _headers(self) -> dict[str, str]:
        if not self._api_token:
            raise AIEngineError("Replicate token missing: set REPLICATE_API_TOKEN")
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise AIEngineError(f"Replicate API error {resp.status_code}: {detail}")
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AIEngineError(f"Replicate API returned non-JSON body: {exc}") from exc

    async def _download(self, url: str, index: int) -> str:
        """Resolve an output URL to a stored image location.

        Side-effect-free seam; override to persist bytes via storage_service
        (owned elsewhere). Returns the URL unchanged by default.
        """
        return str(url)

    async def _create(self, client: httpx.AsyncClient, model_input: dict[str, Any]) -> dict[str, Any]:
        resp = await client.post(
            f"{self._base_url}/predictions",
            json={"version": self._version, "input": model_input},
            headers=self._headers(),
        )
        return self._parse(resp)

    async def _poll(self, client: httpx.AsyncClient, prediction: dict[str, Any]) -> dict[str, Any]:
        status = prediction.get("status")
        get_url = (prediction.get("urls") or {}).get("get")
        polls = 0
        while status not in _TERMINAL:
            if not get_url:
                raise AIEngineError("Replicate prediction missing poll URL")
            if polls >= self._max_polls:
                raise AIEngineError("Replicate prediction timed out while polling")
            if self._poll_interval:
                await asyncio.sleep(self._poll_interval)
            resp = await client.get(get_url, headers=self._headers())
            prediction = self._parse(resp)
            status = prediction.get("status")
            polls += 1
        return prediction

    @staticmethod
    def _outputs(prediction: dict[str, Any]) -> list[str]:
        output = prediction.get("output")
        if output is None:
            return []
        if isinstance(output, str):
            return [output]
        if isinstance(output, list):
            return [str(u) for u in output]
        return []

    async def _run(self, prompt: str, params: dict[str, Any], extra_input: dict[str, Any] | None = None) -> list[GeneratedImage]:
        w, h = self._size(params)
        model_input: dict[str, Any] = {
            "prompt": prompt,
            "width": w,
            "height": h,
            "num_outputs": int(params.get("output_count", 1)),
        }
        if params.get("negative_prompt"):
            model_input["negative_prompt"] = params["negative_prompt"]
        if extra_input:
            model_input.update(extra_input)

        async def _go(client: httpx.AsyncClient) -> list[GeneratedImage]:
            prediction = await self._create(client, model_input)
            prediction = await self._poll(client, prediction)
            if prediction.get("status") != "succeeded":
                err = prediction.get("error") or prediction.get("status")
                raise AIEngineError(f"Replicate prediction did not succeed: {err}")
            urls = self._outputs(prediction)
            if not urls:
                raise AIEngineError("Replicate prediction produced no output")
            images: list[GeneratedImage] = []
            for i, url in enumerate(urls):
                location = await self._download(url, i)
                images.append(GeneratedImage(file_path=location, width=w, height=h, seed=None))
            return images

        if self._client is not None:
            return await _go(self._client)
        async with httpx.AsyncClient(timeout=60.0) as client:
            return await _go(client)

    # -------------------------------------------------------------- public API
    async def generate_image(
        self, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        return await self._run(prompt, params)

    async def revise_image(
        self, image_path: str, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        return await self._run(prompt, params, extra_input={"image": image_path})
