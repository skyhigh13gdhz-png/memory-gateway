import hashlib
import logging
import secrets
import time

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

from .config import settings
from .hindsight import hindsight
from .models import GatewayResponse, RecallRequest, ReflectRequest, RetainRequest

app = FastAPI(title="Memory Gateway", version="0.1.0")
logger = logging.getLogger("uvicorn.error")

def content_fingerprint(content: str) -> dict:
    raw = content.encode("utf-8")
    return {
        "chars": len(content),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "tail_sha256": hashlib.sha256(raw[-256:]).hexdigest(),
    }


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.gateway_api_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


def bank(requested: str | None) -> str:
    return requested or settings.default_bank_id


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


@app.get("/health")
async def health() -> dict:
    engine_ok = await hindsight.health()
    return {"ok": engine_ok, "gateway": "ok", "engine": "hindsight", "hindsight": "ok" if engine_ok else "unreachable"}


@app.post("/v1/memories/retain", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def retain(req: RetainRequest) -> GatewayResponse:
    started = time.perf_counter()
    bank_id = bank(req.bank_id)
    metadata = {**req.metadata, "gateway_client_id": req.client_id, "speaker": req.speaker}
    fp = content_fingerprint(req.content)
    logger.info(
        "event=retain_integrity stage=gateway_received speaker=%s chars=%s bytes=%s sha256=%s tail_sha256=%s",
        req.speaker, fp["chars"], fp["bytes"], fp["sha256"], fp["tail_sha256"],
    )
    engine_started = time.perf_counter()
    try:
        data = await hindsight.retain(bank_id, req.content, metadata)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"memory engine error: {type(exc).__name__}") from exc
    engine_ms = elapsed_ms(engine_started)
    return GatewayResponse(bank_id=bank_id, data=data, timing_ms={"hindsight": engine_ms, "gateway_total": elapsed_ms(started)})


@app.post("/v1/memories/recall", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def recall(req: RecallRequest) -> GatewayResponse:
    started = time.perf_counter()
    bank_id = bank(req.bank_id)
    engine_started = time.perf_counter()
    try:
        data = await hindsight.recall(bank_id, req.query, req.max_results, req.speaker)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"memory engine error: {type(exc).__name__}") from exc
    engine_ms = elapsed_ms(engine_started)
    return GatewayResponse(bank_id=bank_id, data=data, timing_ms={"hindsight": engine_ms, "gateway_total": elapsed_ms(started)})


@app.post("/v1/memories/reflect", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def reflect(req: ReflectRequest) -> GatewayResponse:
    started = time.perf_counter()
    bank_id = bank(req.bank_id)
    engine_started = time.perf_counter()
    try:
        data = await hindsight.reflect(bank_id, req.query, req.speaker)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"memory engine error: {type(exc).__name__}") from exc
    engine_ms = elapsed_ms(engine_started)
    return GatewayResponse(bank_id=bank_id, data=data, timing_ms={"hindsight": engine_ms, "gateway_total": elapsed_ms(started)})
