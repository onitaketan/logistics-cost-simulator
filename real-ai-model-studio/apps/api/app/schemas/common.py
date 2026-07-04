from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    """Consistent envelope for all endpoints (docs/03_api_spec.md §2)."""

    success: bool = True
    data: T | None = None
    error: ApiError | None = None


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def fail(code: str, message: str) -> dict:
    return {"success": False, "data": None, "error": {"code": code, "message": message}}
