from typing import Any

from pydantic import BaseModel, Field


class RetainRequest(BaseModel):
    content: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)


class ReflectRequest(BaseModel):
    query: str = Field(min_length=1)
    bank_id: str | None = None
    client_id: str = Field(default="unknown", min_length=1)
    speaker: str = Field(default="unknown", min_length=1)


class GatewayResponse(BaseModel):
    ok: bool = True
    bank_id: str
    engine: str = "hindsight"
    data: Any
    timing_ms: dict[str, float] = Field(default_factory=dict)
