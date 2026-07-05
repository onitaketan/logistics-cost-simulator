"""AI engine adapter interface.

CLAUDE.md constraint #7: external AI APIs must be swappable behind an adapter.
No adapter may be called for a generation that has not passed compliance —
that gate lives in generation_service, not here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class AIEngineError(RuntimeError):
    """Raised when an external AI engine call fails (transport, auth, or API error).

    Upstream (generation_service) turns this into a failed generation. This never
    means compliance was bypassed — that gate runs before any adapter is invoked.
    """


@dataclass
class GeneratedImage:
    # A produced image the worker will persist. Adapters populate EITHER:
    #  * `data`  — raw image bytes (e.g. gpt-image-1 b64), OR
    #  * `source_url` — an https URL the worker downloads, OR
    #  * neither, for the mock engine (file_path is a placeholder).
    file_path: str        # location/URI or placeholder for the produced image
    width: int
    height: int
    seed: int | None = None
    data: bytes | None = None        # raw bytes when the provider returns them inline
    source_url: str | None = None    # https URL to fetch when bytes are not inline


class AIEngineAdapter(ABC):
    #: whether this engine can be used for training/fine-tuning workflows
    training_capable: bool = False

    @abstractmethod
    async def generate_image(self, prompt: str, params: dict[str, Any]) -> list[GeneratedImage]:
        """Return generated images. `params` includes negative_prompt, size, count."""
        raise NotImplementedError

    @abstractmethod
    async def revise_image(
        self, image_path: str, prompt: str, params: dict[str, Any]
    ) -> list[GeneratedImage]:
        raise NotImplementedError
