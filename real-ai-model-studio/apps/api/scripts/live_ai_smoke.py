"""Live AI-engine smoke test — validates a REAL provider key + plumbing.

This makes an ACTUAL, billable call to the configured AI provider. It needs no
database. Use it to confirm credentials and connectivity before running a full
generation through the app.

Usage:
    export AI_ENGINE=openai            # or replicate
    export AI_ENGINE_API_KEY=sk-...    # openai;  REPLICATE_API_TOKEN=... for replicate
    python scripts/live_ai_smoke.py "a premium product on a clean studio background"

Prints the number of images returned and where each is (bytes inline vs URL).
Never commit real keys. Compliance gating is NOT exercised here — this is a raw
adapter/credentials check only.
"""

import asyncio
import os
import sys

from app.services.ai_engines import get_adapter


async def _run(prompt: str) -> int:
    engine = os.environ.get("AI_ENGINE", "mock")
    adapter = get_adapter(engine)
    print(f"engine={engine} adapter={adapter.__class__.__name__}")
    images = await adapter.generate_image(
        prompt, {"output_count": 1, "width": 1024, "height": 1024}
    )
    print(f"returned {len(images)} image(s):")
    for i, img in enumerate(images):
        kind = "inline-bytes" if img.data else ("url" if img.source_url else "placeholder")
        size = len(img.data) if img.data else "-"
        print(f"  [{i}] {img.width}x{img.height} via {kind} ({size} bytes) loc={img.file_path}")
    return len(images)


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "a premium beverage on a clean studio background"
    try:
        n = asyncio.run(_run(prompt))
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE FAILED: {exc}")
        raise SystemExit(1)
    print("SMOKE OK" if n > 0 else "SMOKE: no images returned")


if __name__ == "__main__":
    main()
