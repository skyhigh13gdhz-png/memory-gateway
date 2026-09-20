from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RetainRequest(BaseModel):
    content: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    document_id: str | None = Field(default=None, min_length=1)
    timestamp: str | None = None
    update_mode: Literal["replace", "append"] | None = None


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)
    max_results: int = Field(default=20, ge=1, le=100)


class ReflectRequest(BaseModel):
    query: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)


class DocumentPatchRequest(BaseModel):
    expected_text: str = Field(min_length=1)
    replacement_text: str
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(min_length=1)
    reason: str | None = None


class GatewayResponse(BaseModel):
    ok: bool = True
    bank_id: str
    engine: str = "hindsight"
    data: Any
    timing_ms: dict[str, float] = Field(default_factory=dict)
