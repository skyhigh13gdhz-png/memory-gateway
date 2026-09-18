from typing import Any

import httpx

from .config import settings


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

    async def retain(self, bank_id: str, content: str, metadata: dict[str, Any]) -> Any:
        speaker = str(metadata.get("speaker", "unknown"))
        item: dict[str, Any] = {
            "content": content,
            "context": f"The speaker of this memory is {speaker}.",
            "tags": [f"speaker:{speaker}"],
        }
        if metadata:
            item["metadata"] = metadata
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/memories",
            json={"items": [item]},
        )

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
