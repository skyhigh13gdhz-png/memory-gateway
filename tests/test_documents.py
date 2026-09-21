import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from gateway.main import app, normalize_metadata, operation_speakers, public_operation


AUTH = {"Authorization": "Bearer test-token"}


class DocumentApiTests(unittest.TestCase):
    def test_operation_helpers_scope_and_strip_private_payload(self) -> None:
        operation = {
            "operation_id": "op-1",
            "status": "completed",
            "error_message": "earlier retry failed",
            "retry_count": 2,
            "task_payload": {
                "contents": [{
                    "content": "private diary text",
                    "tags": ["speaker:liangzai"],
                    "metadata": {"speaker": "liangzai"},
                }],
            },
        }
        self.assertEqual(operation_speakers(operation), {"liangzai"})
        public = public_operation(operation)
        self.assertTrue(public["terminal"])
        self.assertEqual(public["last_error"], "earlier retry failed")
        self.assertNotIn("task_payload", public)
        self.assertNotIn("private diary text", str(public))

    def test_metadata_is_normalized_to_hindsight_strings(self) -> None:
        self.assertEqual(
            normalize_metadata({"text": "ok", "flag": True, "count": 3, "none": None, "data": {"b": 2, "a": 1}}),
            {"text": "ok", "flag": "true", "count": "3", "none": "null", "data": '{"a":1,"b":2}'},
        )

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

    @patch("gateway.main.hindsight")
    def test_retain_can_request_fast_async_processing(self, hindsight: AsyncMock) -> None:
        hindsight.retain = AsyncMock(return_value={"success": True, "async": True, "operation_id": "op-1"})
        response = self.client.post(
            "/v1/memories/retain",
            headers=AUTH,
            json={"content": "new record", "speaker": "liangzai", "async_processing": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(hindsight.retain.await_args.kwargs["async_processing"])
        self.assertEqual(response.json()["data"]["operation_id"], "op-1")

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
    def test_document_list_filters_event_date_and_includes_original_text(self, hindsight: AsyncMock) -> None:
        summaries = [
            {"id": "doc-16", "retain_params": {"event_date": "2026-09-16T00:00:00+08:00"}},
            {"id": "doc-17", "retain_params": {"event_date": "2026-09-17T00:00:00+08:00"}},
            {"id": "doc-18", "retain_params": {"event_date": "2026-09-18T12:00:00+08:00"}},
        ]
        hindsight.list_documents = AsyncMock(
            return_value={"items": summaries, "total": 3, "limit": 1000, "offset": 0}
        )
        hindsight.get_document = AsyncMock(return_value={
            "id": "doc-17",
            "original_text": "中午吃炒面，晚上吃花卷和烤鸭。",
            "tags": ["speaker:liangzai"],
            "retain_params": {"event_date": "2026-09-17T00:00:00+08:00"},
        })
        response = self.client.get(
            "/v1/documents?speaker=liangzai&date_from=2026-09-17&date_to=2026-09-17&include_text=true",
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["id"], "doc-17")
        self.assertIn("炒面", payload["items"][0]["original_text"])
        hindsight.get_document.assert_awaited_once_with("default", "doc-17")

    def test_document_list_rejects_reversed_date_range(self) -> None:
        response = self.client.get(
            "/v1/documents?speaker=liangzai&date_from=2026-09-18&date_to=2026-09-17",
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 422)

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

    @patch("gateway.main.hindsight")
    def test_operation_get_is_scoped_and_sanitized(self, hindsight: AsyncMock) -> None:
        hindsight.get_operation = AsyncMock(return_value={
            "operation_id": "op-1",
            "status": "completed",
            "operation_type": "retain",
            "created_at": "2026-09-21T12:00:00Z",
            "updated_at": "2026-09-21T12:01:00Z",
            "completed_at": "2026-09-21T12:01:00Z",
            "error_message": "timeout before retry",
            "retry_count": 1,
            "task_payload": {"contents": [{
                "content": "private text",
                "metadata": {"speaker": "liangzai"},
                "tags": ["speaker:liangzai"],
            }]},
        })
        response = self.client.get(
            "/v1/operations/op-1?speaker=liangzai&bank_id=test-bank", headers=AUTH
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "completed")
        self.assertTrue(data["terminal"])
        self.assertEqual(data["last_error"], "timeout before retry")
        self.assertNotIn("task_payload", data)
        self.assertNotIn("private text", response.text)
        hindsight.get_operation.assert_awaited_once_with(
            "test-bank", "op-1", include_payload=True
        )

    @patch("gateway.main.hindsight")
    def test_operation_get_hides_other_speaker(self, hindsight: AsyncMock) -> None:
        hindsight.get_operation = AsyncMock(return_value={
            "operation_id": "op-1",
            "status": "processing",
            "task_payload": {"contents": [{"metadata": {"speaker": "monica"}}]},
        })
        response = self.client.get(
            "/v1/operations/op-1?speaker=liangzai", headers=AUTH
        )
        self.assertEqual(response.status_code, 404)

    @patch("gateway.main.hindsight")
    def test_operation_get_hides_not_found(self, hindsight: AsyncMock) -> None:
        hindsight.get_operation = AsyncMock(return_value={
            "operation_id": "missing", "status": "not_found", "task_payload": None
        })
        response = self.client.get(
            "/v1/operations/missing?speaker=liangzai", headers=AUTH
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
