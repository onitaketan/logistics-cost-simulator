"""AI engine registry — resolve an adapter by key (config-driven, swappable).

CLAUDE.md constraint #7: external AI APIs are swapped behind adapters keyed here.
The registry only resolves adapters; it never runs a generation and is never a
compliance gate — that gate runs upstream before any adapter is invoked.

OFFLINE_MODE (default ON): with settings.offline_mode true, the EXTERNAL engines
(openai / replicate) are refused here — prompts and generated likeness data must
not leave the machine unless the operator explicitly opts out with
OFFLINE_MODE=false. mock and self_hosted stay available (both are local-only).
This is the single choke point every generation path resolves through (the
worker included), and startup validation in core/config enforces the same rule
earlier; both layers exist on purpose (defense in depth).
"""

from app.services.ai_engines.base import AIEngineAdapter, AIEngineError
from app.services.ai_engines.mock_adapter import MockAdapter
from app.services.ai_engines.openai_adapter import OpenAIAdapter
from app.services.ai_engines.replicate_adapter import ReplicateAdapter
from app.services.ai_engines.self_hosted_adapter import SelfHostedAdapter

_REGISTRY: dict[str, type[AIEngineAdapter]] = {
    "mock": MockAdapter,
    "openai": OpenAIAdapter,
    "replicate": ReplicateAdapter,
    "self_hosted": SelfHostedAdapter,
}

# Engines that send prompts / receive images over the internet.
EXTERNAL_ENGINES = {"openai", "replicate"}


def get_adapter(adapter_key: str) -> AIEngineAdapter:
    if adapter_key in EXTERNAL_ENGINES:
        from app.core.config import get_settings  # local import: no cycle at module load

        if get_settings().offline_mode:
            raise AIEngineError(
                f"OFFLINE_MODE 有効のため外部AIエンジン '{adapter_key}' は使用できません。"
                "PC内で完結する 'self_hosted'（または mock）を使うか、流出リスクを理解の上で "
                "OFFLINE_MODE=false を明示してください。"
            )
    try:
        return _REGISTRY[adapter_key]()
    except KeyError:
        raise ValueError(f"unknown AI engine adapter: {adapter_key!r}")
