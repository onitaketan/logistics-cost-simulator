"""AI engine registry — resolve an adapter by key (config-driven, swappable)."""

from app.services.ai_engines.base import AIEngineAdapter
from app.services.ai_engines.mock_adapter import MockAdapter

_REGISTRY: dict[str, type[AIEngineAdapter]] = {
    "mock": MockAdapter,
    # "openai": OpenAIAdapter,        # add in Phase 3
    # "replicate": ReplicateAdapter,
    # "self_hosted": SelfHostedAdapter,
}


def get_adapter(adapter_key: str) -> AIEngineAdapter:
    try:
        return _REGISTRY[adapter_key]()
    except KeyError:
        raise ValueError(f"unknown AI engine adapter: {adapter_key!r}")
