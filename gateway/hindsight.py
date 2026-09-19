from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import quote

import httpx

from .config import settings

logger = logging.getLogger("uvicorn.error")


class HindsightAdapter:
    """只在这一层理解 Hindsight 私有 API，Gateway 对外 contract 不泄漏这些细节。"""

    def __init__(self) -> None:
        self.base_url = settings.hindsight_base_url.rstrip("/")
        self.timeout = settings.hindsight_timeout_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()

    async def health(self) -> bool:
        # 当前已验收的 Hindsight 部署以 /docs 作为基础可达性检查。
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/docs")
                return response.status_code < 400
        except httpx.HTTPError:
            return False

    async def retain(
        self,
        bank_id: str,
        content: str,
        metadata: dict[str, Any],
        *,
        document_id: str | None = None,
        timestamp: str | None = None,
        update_mode: str | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        speaker = str(metadata.get("speaker", "unknown"))
        item: dict[str, Any] = {
            "content": content,
            "context": f"The speaker of this memory is {speaker}.",
            "tags": tags if tags is not None else [f"speaker:{speaker}"],
        }
        if metadata:
            item["metadata"] = metadata
        if document_id is not None:
            item["document_id"] = document_id
        if timestamp is not None:
            item["timestamp"] = timestamp
        if update_mode is not None:
            item["update_mode"] = update_mode
        raw = content.encode("utf-8")
        logger.info(
            "event=retain_integrity stage=hindsight_outbound speaker=%s chars=%s bytes=%s sha256=%s tail_sha256=%s",
            speaker, len(content), len(raw), hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw[-256:]).hexdigest(),
        )
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/memories",
            json={"items": [item]},
        )

    async def list_documents(
        self,
        bank_id: str,
        speaker: str,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> Any:
        params: dict[str, Any] = {
            "tags": [f"speaker:{speaker}"],
            "tags_match": "all_strict",
            "limit": limit,
            "offset": offset,
        }
        if query:
            params["q"] = query
        return await self._request("GET", f"/v1/default/banks/{bank_id}/documents", params=params)

    async def get_document(self, bank_id: str, document_id: str) -> Any:
        return await self._request("GET", f"/v1/default/banks/{bank_id}/documents/{quote(document_id, safe='')}")

    async def recall(self, bank_id: str, query: str, max_results: int, speaker: str) -> Any:
        # max_results 属于 Gateway contract；Hindsight 当前已验收 payload 只保证 query。
        # 在确认 Hindsight 对结果数量参数的正式字段前，不把猜测字段透传到底层。
        data = await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/memories/recall",
            json={
                "query": query,
                "tags": [f"speaker:{speaker}"],
                "tags_match": "all_strict",
                "include_chunks": True,
                "max_chunk_tokens": 4096,
            },
        )
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            data = {**data, "results": data["results"][:max_results]}
        return data

    async def reflect(self, bank_id: str, query: str, speaker: str) -> Any:
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/reflect",
            json={
                "query": query,
                "context": f"Current speaker: {speaker}",
                "tags": [f"speaker:{speaker}"],
                "tags_match": "all_strict",
            },
        )


hindsight = HindsightAdapter()
