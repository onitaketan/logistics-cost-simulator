"""AI engine registry — resolve an adapter by key (config-driven, swappable).

CLAUDE.md constraint #7: external AI APIs are swapped behind adapters keyed here.
The registry only resolves adapters; it never runs a generation and is never a
compliance gate — that gate runs upstream before any adapter is invoked.
"""

from app.services.ai_engines.base import AIEngineAdapter
from app.services.ai_engines.mock_adapter import MockAdapter
from app.services.ai_engines.openai_adapter import OpenAIAdapter
from app.services.ai_engines.replicate_adapter import ReplicateAdapter

_REGISTRY: dict[str, type[AIEngineAdapter]] = {
    "mock": MockAdapter,
    "openai": OpenAIAdapter,
    "replicate": ReplicateAdapter,
    # "self_hosted": SelfHostedAdapter,
}


def get_adapter(adapter_key: str) -> AIEngineAdapter:
    try:
        return _REGISTRY[adapter_key]()
    except KeyError:
        raise ValueError(f"unknown AI engine adapter: {adapter_key!r}")
