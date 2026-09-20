from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

from .config import settings
from .hindsight import hindsight
from .models import DocumentPatchRequest, GatewayResponse, RecallRequest, ReflectRequest, RetainRequest

app = FastAPI(title="Memory Gateway", version="0.1.0")
logger = logging.getLogger("uvicorn.error")
document_locks: dict[tuple[str, str], asyncio.Lock] = {}

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


def require_speaker(document: dict, speaker: str) -> None:
    if f"speaker:{speaker}" not in (document.get("tags") or []):
        raise HTTPException(status_code=404, detail="document not found")


def engine_error(exc: httpx.HTTPError) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return HTTPException(status_code=404, detail="document not found")
    return HTTPException(status_code=502, detail=f"memory engine error: {type(exc).__name__}")


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
    effective_update_mode = req.update_mode if req.document_id is not None else None
    if req.update_mode is not None and req.document_id is None:
        logger.info(
            "event=retain_normalized speaker=%s requested_update_mode=%s reason=missing_document_id",
            req.speaker,
            req.update_mode,
        )
    try:
        data = await hindsight.retain(
            bank_id,
            req.content,
            metadata,
            document_id=req.document_id,
            timestamp=req.timestamp,
            update_mode=effective_update_mode,
        )
    except httpx.HTTPError as exc:
        upstream_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning(
            "event=retain_failed speaker=%s document_id_present=%s timestamp_present=%s "
            "requested_update_mode=%s effective_update_mode=%s upstream_status=%s error_type=%s",
            req.speaker,
            req.document_id is not None,
            req.timestamp is not None,
            req.update_mode,
            effective_update_mode,
            upstream_status,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail=f"memory engine error: {type(exc).__name__}") from exc
    engine_ms = elapsed_ms(engine_started)
    return GatewayResponse(bank_id=bank_id, data=data, timing_ms={"hindsight": engine_ms, "gateway_total": elapsed_ms(started)})


@app.get("/v1/documents", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def list_documents(
    speaker: str,
    bank_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> GatewayResponse:
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1..1000 and offset must be >= 0")
    started = time.perf_counter()
    selected_bank = bank(bank_id)
    try:
        data = await hindsight.list_documents(
            selected_bank, speaker, query=q, limit=limit, offset=offset
        )
    except httpx.HTTPError as exc:
        raise engine_error(exc) from exc
    return GatewayResponse(bank_id=selected_bank, data=data, timing_ms={"gateway_total": elapsed_ms(started)})


@app.get("/v1/documents/{document_id}", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def get_document(document_id: str, speaker: str, bank_id: str | None = None) -> GatewayResponse:
    started = time.perf_counter()
    selected_bank = bank(bank_id)
    try:
        data = await hindsight.get_document(selected_bank, document_id)
    except httpx.HTTPError as exc:
        raise engine_error(exc) from exc
    require_speaker(data, speaker)
    return GatewayResponse(bank_id=selected_bank, data=data, timing_ms={"gateway_total": elapsed_ms(started)})


@app.post("/v1/documents/{document_id}/patch", response_model=GatewayResponse, dependencies=[Depends(require_token)])
async def patch_document(document_id: str, req: DocumentPatchRequest) -> GatewayResponse:
    started = time.perf_counter()
    selected_bank = bank(req.bank_id)
    lock = document_locks.setdefault((selected_bank, document_id), asyncio.Lock())
    async with lock:
        try:
            current = await hindsight.get_document(selected_bank, document_id)
        except httpx.HTTPError as exc:
            raise engine_error(exc) from exc
        require_speaker(current, req.speaker)
        content = current.get("original_text")
        if not isinstance(content, str):
            raise HTTPException(status_code=409, detail="document original_text is unavailable")
        occurrences = content.count(req.expected_text)
        if occurrences == 0:
            raise HTTPException(status_code=409, detail="PATCH_CONFLICT")
        if occurrences > 1:
            raise HTTPException(status_code=409, detail="PATCH_AMBIGUOUS")
        updated = content.replace(req.expected_text, req.replacement_text, 1)
        metadata = dict(current.get("document_metadata") or {})
        metadata["speaker"] = req.speaker
        metadata["last_patch_client_id"] = req.client_id
        if req.reason:
            metadata["last_patch_reason"] = req.reason
        timestamp = (current.get("retain_params") or {}).get("event_date")
        before_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        after_hash = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        try:
            retain_result = await hindsight.retain(
                selected_bank,
                updated,
                metadata,
                document_id=document_id,
                timestamp=timestamp,
                update_mode="replace",
                tags=list(current.get("tags") or []),
            )
            document = await hindsight.get_document(selected_bank, document_id)
        except httpx.HTTPError as exc:
            raise engine_error(exc) from exc
        logger.info(
            "event=document_patch document_id=%s speaker=%s before_sha256=%s after_sha256=%s",
            document_id,
            req.speaker,
            before_hash,
            after_hash,
        )
    data = {
        "document": document,
        "patch": {"before_sha256": before_hash, "after_sha256": after_hash},
        "retain": retain_result,
    }
    return GatewayResponse(bank_id=selected_bank, data=data, timing_ms={"gateway_total": elapsed_ms(started)})


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
