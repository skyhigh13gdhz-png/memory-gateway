import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from gateway.main import app


AUTH = {"Authorization": "Bearer test-token"}


class DocumentApiTests(unittest.TestCase):
    @patch("gateway.main.hindsight")
    def test_retain_ignores_update_mode_without_document_id(self, hindsight: AsyncMock) -> None:
        hindsight.retain = AsyncMock(return_value={"success": True})
        response = self.client.post(
            "/v1/memories/retain",
            headers=AUTH,
            json={"content": "new record", "speaker": "liangzai", "update_mode": "append"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(hindsight.retain.await_args.kwargs["document_id"])
        self.assertIsNone(hindsight.retain.await_args.kwargs["update_mode"])

    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("gateway.main.hindsight")
    def test_document_list_is_scoped_to_speaker(self, hindsight: AsyncMock) -> None:
        hindsight.list_documents = AsyncMock(return_value={"items": [], "total": 0, "limit": 10, "offset": 0})
        response = self.client.get(
            "/v1/documents?speaker=liangzai&bank_id=test-bank&limit=10",
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 200)
        hindsight.list_documents.assert_awaited_once_with(
            "test-bank", "liangzai", query=None, limit=10, offset=0
        )

    @patch("gateway.main.hindsight")
    def test_patch_replaces_exactly_one_fragment(self, hindsight: AsyncMock) -> None:
        before = {
            "id": "doc-1",
            "original_text": "CRV 亏损 42 美元。",
            "tags": ["speaker:liangzai", "source:chatgpt"],
            "document_metadata": {"speaker": "liangzai"},
            "retain_params": {"event_date": "2026-09-19T19:00:00+08:00"},
        }
        after = {**before, "original_text": "CRV 亏损 52 美元。"}
        hindsight.get_document = AsyncMock(side_effect=[before, after])
        hindsight.retain = AsyncMock(return_value={"success": True})
        response = self.client.post(
            "/v1/documents/doc-1/patch",
            headers=AUTH,
            json={
                "expected_text": "42",
                "replacement_text": "52",
                "bank_id": "test-bank",
                "client_id": "test-client",
                "speaker": "liangzai",
                "reason": "user_correction",
            },
        )
        self.assertEqual(response.status_code, 200)
        call = hindsight.retain.await_args
        self.assertEqual(call.args[:2], ("test-bank", "CRV 亏损 52 美元。"))
        self.assertEqual(call.kwargs["document_id"], "doc-1")
        self.assertEqual(call.kwargs["update_mode"], "replace")
        self.assertEqual(call.kwargs["timestamp"], "2026-09-19T19:00:00+08:00")

    @patch("gateway.main.hindsight")
    def test_patch_conflict_does_not_write(self, hindsight: AsyncMock) -> None:
        hindsight.get_document = AsyncMock(
            return_value={"id": "doc-1", "original_text": "CRV 亏损 52 美元。", "tags": ["speaker:liangzai"]}
        )
        hindsight.retain = AsyncMock()
        response = self.client.post(
            "/v1/documents/doc-1/patch",
            headers=AUTH,
            json={"expected_text": "42", "replacement_text": "52", "speaker": "liangzai"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "PATCH_CONFLICT")
        hindsight.retain.assert_not_awaited()

    @patch("gateway.main.hindsight")
    def test_wrong_speaker_is_hidden_as_not_found(self, hindsight: AsyncMock) -> None:
        hindsight.get_document = AsyncMock(
            return_value={"id": "doc-1", "original_text": "secret", "tags": ["speaker:other"]}
        )
        response = self.client.get(
            "/v1/documents/doc-1?speaker=liangzai&bank_id=test-bank",
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
