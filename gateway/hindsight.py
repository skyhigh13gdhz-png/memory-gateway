from typing import Any

import httpx

from .config import settings


class HindsightAdapter:
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
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def retain(self, bank_id: str, content: str, metadata: dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/memories",
            json={"items": [{"content": content, "metadata": metadata}]},
        )

    async def recall(self, bank_id: str, query: str, max_results: int) -> Any:
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/memories/recall",
            json={"query": query, "max_results": max_results},
        )

    async def reflect(self, bank_id: str, query: str) -> Any:
        return await self._request(
            "POST",
            f"/v1/default/banks/{bank_id}/reflect",
            json={"query": query},
        )


hindsight = HindsightAdapter()
