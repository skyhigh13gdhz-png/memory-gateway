#!/usr/bin/env python3
"""End-to-end smoke test for the Gateway V2.1 Document contract."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


def call(method: str, url: str, body: dict[str, Any] | None = None, expected: tuple[int, ...] = (200,)) -> Any:
    token = os.environ["GATEWAY_API_TOKEN"]
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    payload = json.loads(raw.decode("utf-8")) if raw else None
    if status not in expected:
        raise RuntimeError(f"{method} {url} returned {status}: {payload}")
    return status, payload


def main() -> int:
    base = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
    bank = f"audit-gateway-v21-{run_id}"
    document_id = f"gateway-document-{run_id}"
    speaker = "audit-gateway"
    original = f"{run_id}：CRV 止损亏损 42 美元。"

    call(
        "POST",
        f"{base}/v1/memories/retain",
        {
            "content": original,
            "bank_id": bank,
            "client_id": "gateway-v21-smoke",
            "speaker": speaker,
            "document_id": document_id,
            "timestamp": "2026-09-19T19:00:00+08:00",
            "update_mode": "replace",
            "metadata": {"audit_id": "gateway-v21-smoke"},
        },
    )
    query = urllib.parse.urlencode({"speaker": speaker, "bank_id": bank, "limit": 10})
    _, listing = call("GET", f"{base}/v1/documents?{query}")
    ids = [item["id"] for item in listing["data"]["items"]]
    if document_id not in ids:
        raise RuntimeError("new document is absent from scoped listing")

    range_query = urllib.parse.urlencode({
        "speaker": speaker,
        "bank_id": bank,
        "date_from": "2026-09-19",
        "date_to": "2026-09-19",
        "include_text": "true",
        "limit": 10,
    })
    _, ranged = call("GET", f"{base}/v1/documents?{range_query}")
    ranged_items = ranged["data"]["items"]
    if len(ranged_items) != 1 or ranged_items[0].get("original_text") != original:
        raise RuntimeError("date range listing did not return the complete original document")

    doc_query = urllib.parse.urlencode({"speaker": speaker, "bank_id": bank})
    _, document = call("GET", f"{base}/v1/documents/{document_id}?{doc_query}")
    if document["data"]["original_text"] != original:
        raise RuntimeError("Document GET did not preserve the original text")

    _, patched = call(
        "POST",
        f"{base}/v1/documents/{document_id}/patch",
        {
            "bank_id": bank,
            "client_id": "gateway-v21-smoke",
            "speaker": speaker,
            "expected_text": "42",
            "replacement_text": "52",
            "reason": "smoke_test",
        },
    )
    if "52" not in patched["data"]["document"]["original_text"] or "42" in patched["data"]["document"]["original_text"]:
        raise RuntimeError("Patch did not replace 42 with 52 exactly")

    conflict_status, conflict = call(
        "POST",
        f"{base}/v1/documents/{document_id}/patch",
        {
            "bank_id": bank,
            "client_id": "gateway-v21-smoke",
            "speaker": speaker,
            "expected_text": "42",
            "replacement_text": "52",
        },
        expected=(409,),
    )
    wrong_speaker_query = urllib.parse.urlencode({"speaker": "other", "bank_id": bank})
    hidden_status, _ = call(
        "GET",
        f"{base}/v1/documents/{document_id}?{wrong_speaker_query}",
        expected=(404,),
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "bank_id": bank,
                "document_id": document_id,
                "list_get": "PASS",
                "date_range_with_text": "PASS",
                "patch_42_to_52": "PASS",
                "repeat_patch_status": conflict_status,
                "repeat_patch_detail": conflict.get("detail"),
                "wrong_speaker_status": hidden_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
