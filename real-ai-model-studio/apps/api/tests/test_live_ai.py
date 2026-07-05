"""Live AI-engine integration test — SKIPPED by default (real key, real cost).

Enable with:
    RAMS_LIVE_AI=1 AI_ENGINE=openai AI_ENGINE_API_KEY=sk-... pytest tests/test_live_ai.py -q

Makes a real, billable provider call and asserts an image comes back with either
inline bytes or a fetchable source URL. Never runs in CI without the opt-in flag.
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RAMS_LIVE_AI") != "1",
    reason="live AI test disabled (set RAMS_LIVE_AI=1 with a real key to run)",
)


def test_live_generate_returns_image():
    from app.services.ai_engines import get_adapter

    engine = os.environ.get("AI_ENGINE", "openai")
    adapter = get_adapter(engine)
    images = asyncio.run(
        adapter.generate_image(
            "a premium beverage on a clean studio background, product photography",
            {"output_count": 1, "width": 1024, "height": 1024},
        )
    )
    assert images, "provider returned no images"
    img = images[0]
    assert img.data or img.source_url or img.file_path, "no retrievable image location"
