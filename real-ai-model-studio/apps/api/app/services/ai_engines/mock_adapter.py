"""Deterministic mock engine for local dev / tests. Produces no real imagery."""

from typing import Any

from app.services.ai_engines.base import AIEngineAdapter, GeneratedImage


class MockAdapter(AIEngineAdapter):
    training_capable = False

    async def generate_image(self, prompt: str, params: dict[str, Any]) -> list[GeneratedImage]:
        count = int(params.get("output_count", 1))
        w = int(params.get("width", 1024))
        h = int(params.get("height", 1024))
        return [
            GeneratedImage(file_path=f"mock://generated/{i}.png", width=w, height=h, seed=i)
            for i in range(count)
        ]

    async def revise_image(
        self, image_path: str, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        w = int(params.get("width", 1024))
        h = int(params.get("height", 1024))
        return [GeneratedImage(file_path=f"mock://revised/0.png", width=w, height=h, seed=0)]
