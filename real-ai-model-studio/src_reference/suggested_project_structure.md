# Suggested Project Structure

## Monorepo Example

```text
real-ai-model-studio/
├── CLAUDE.md
├── README.md
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── app/
│   │   │   ├── components/
│   │   │   ├── features/
│   │   │   │   ├── auth/
│   │   │   │   ├── dashboard/
│   │   │   │   ├── models/
│   │   │   │   ├── projects/
│   │   │   │   ├── compliance/
│   │   │   │   ├── generation/
│   │   │   │   ├── review/
│   │   │   │   ├── delivery/
│   │   │   │   └── audit/
│   │   │   ├── lib/
│   │   │   └── types/
│   │   └── package.json
│   └── api/
│       ├── app/
│       │   ├── main.py
│       │   ├── core/
│       │   ├── db/
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── routers/
│       │   │   ├── auth.py
│       │   │   ├── users.py
│       │   │   ├── models.py
│       │   │   ├── contracts.py
│       │   │   ├── projects.py
│       │   │   ├── compliance.py
│       │   │   ├── generations.py
│       │   │   ├── reviews.py
│       │   │   ├── approvals.py
│       │   │   ├── deliveries.py
│       │   │   └── audit.py
│       │   ├── services/
│       │   │   ├── compliance_engine.py
│       │   │   ├── audit_service.py
│       │   │   ├── storage_service.py
│       │   │   ├── generation_service.py
│       │   │   └── ai_engines/
│       │   │       ├── base.py
│       │   │       ├── openai_adapter.py
│       │   │       ├── replicate_adapter.py
│       │   │       └── self_hosted_adapter.py
│       │   └── workers/
│       │       └── generation_worker.py
│       └── pyproject.toml
├── packages/
│   └── shared-types/
├── docs/
├── legal/
├── planning/
└── proposal/
```

## Backend Service Rules

- `compliance_engine.py` contains all generation permission logic.
- `generation_service.py` must call compliance check before creating generation jobs.
- `audit_service.py` must log all critical operations.
- `storage_service.py` must calculate file hash for uploads and outputs.
- AI engines must implement a common interface.

## AI Engine Interface Example

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class AIEngineAdapter(ABC):
    @abstractmethod
    async def generate_image(self, prompt: str, params: Dict[str, Any]) -> List[str]:
        """Return list of generated image file paths or temporary URLs."""
        raise NotImplementedError

    @abstractmethod
    async def revise_image(self, image_path: str, prompt: str, params: Dict[str, Any]) -> List[str]:
        raise NotImplementedError
```

## Compliance Engine Example

```python
def can_generate(project, model, permission, contract):
    if not model.adult_verified:
        return "prohibited", ["Adult verification is missing"]
    if contract.is_expired:
        return "ng", ["Contract expired"]
    if not contract.ai_generation_allowed:
        return "ng", ["AI generation not allowed"]
    # Continue checks...
    return "ok", []
```
