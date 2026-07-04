"""AI engine adapter interface.

CLAUDE.md constraint #7: external AI APIs must be swappable behind an adapter.
No adapter may be called for a generation that has not passed compliance —
that gate lives in generation_service, not here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class GeneratedImage:
    file_path: str        # path/URI to the stored image
    width: int
    height: int
    seed: int | None = None


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
