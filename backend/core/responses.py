"""
Standard API response shape (enforced project-wide):
  { "success": bool, "data": any, "error": string | null }

Every route MUST return via ok() or err() — never raw dicts.
"""
from typing import Any, Optional
from pydantic import BaseModel


class APIResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def err(message: str, data: Any = None) -> dict:
    return {"success": False, "data": data, "error": message}
