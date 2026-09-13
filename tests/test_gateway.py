from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from ai4math_gateway.app import create_app, estimate_input_tokens


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config_path = root / "gateway.yaml"
        self.config_path.write_text(
            f"""
server:
  host: 127.0.0.1
  port: 4001
  auth_token: test-local
  database: {root / 'budget.sqlite3'}
  max_concurrent_requests: 2
  min_start_interval_seconds: 0.01
  retry_attempts: 3
  retry_base_seconds: 0.01
  sse_keepalive_seconds: 0.01
budget:
  id: test
  total_tokens: 5000
  total_cny: "1.00"
  total_requests: 10
models:
  fast:
    provider_model: openai/test-model
    api_base: https://example.invalid/v1
    api_key_env: TEST_API_KEY
    max_context_tokens: 4096
    max_output_tokens: 512
    default_output_tokens: 128
    input_cny_per_million: "3"
    output_cny_per_million: "15"
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    async def test_non_streaming_request_and_metadata_only_ledger(self) -> None:
        async def fake_completion(**kwargs):
            self.assertEqual(kwargs["model"], "openai/test-model")
            self.assertEqual(kwargs["max_tokens"], 64)
            return {
                "id": "answer-1",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "4"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
            }

        app = create_app(
            self.config_path,
            completion_fn=fake_completion,
            credentials={"fast": "test-secret"},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-local"},
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": "2+2 等于多少？"}],
                    "max_tokens": 64,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["model"], "fast")
            status = await client.get(
                "/budget/status", headers={"Authorization": "Bearer test-local"}
            )
            self.assertEqual(status.json()["budget"]["used_tokens"], 10)
            serialized = json.dumps(status.json(), ensure_ascii=False)
            self.assertNotIn("2+2 等于多少", serialized)

    async def test_streaming_request_is_settled(self) -> None:
        async def fake_completion(**kwargs):
            async def chunks():
                yield {
                    "id": "answer-2",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "好"}}],
                }
                yield {
                    "id": "answer-2",
                    "object": "chat.completion.chunk",
                    "choices": [],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
                }

            return chunks()

        app = create_app(
            self.config_path,
            completion_fn=fake_completion,
            credentials={"fast": "test-secret"},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-local"},
                json={
                    "model": "ai4math-gateway/fast",
                    "messages": [{"role": "user", "content": "问候"}],
                    "stream": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("data: [DONE]", response.text)
            status = await client.get(
                "/budget/status", headers={"Authorization": "Bearer test-local"}
            )
            self.assertEqual(status.json()["budget"]["used_tokens"], 10)
            self.assertEqual(status.json()["budget"]["reserved_tokens"], 0)

    async def test_streaming_retries_burst_error_before_first_chunk(self) -> None:
        calls = 0

        async def fake_completion(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("System protection triggered by request burst")

            async def chunks():
                yield {
                    "id": "answer-retry",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "恢复"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                }

            return chunks()

        app = create_app(
            self.config_path,
            completion_fn=fake_completion,
            credentials={"fast": "test-secret"},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-local"},
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": "并行测试"}],
                    "stream": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(calls, 2)
            self.assertIn("恢复", response.text)
            self.assertIn("ai4math-retry-keepalive", response.text)
            self.assertIn("data: [DONE]", response.text)

    async def test_streaming_sends_keepalive_while_model_thinks(self) -> None:
        async def fake_completion(**kwargs):
            await asyncio.sleep(0.03)

            async def chunks():
                yield {
                    "id": "answer-slow",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "完成"}}],
                    "usage": {"prompt_tokens": 6, "completion_tokens": 2},
                }

            return chunks()

        app = create_app(
            self.config_path,
            completion_fn=fake_completion,
            credentials={"fast": "test-secret"},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-local"},
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": "慢速测试"}],
                    "stream": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("ai4math-upstream-keepalive", response.text)
            self.assertIn("完成", response.text)

    async def test_auth_and_output_limits_are_enforced_before_upstream(self) -> None:
        calls = 0

        async def fake_completion(**kwargs):
            nonlocal calls
            calls += 1
            return {}

        app = create_app(
            self.config_path,
            completion_fn=fake_completion,
            credentials={"fast": "test-secret"},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            unauthorized = await client.get("/v1/models")
            self.assertEqual(unauthorized.status_code, 401)
            too_large = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-local"},
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 513,
                },
            )
            self.assertEqual(too_large.status_code, 400)
            self.assertEqual(calls, 0)

    def test_input_estimate_is_conservative_and_content_sensitive(self) -> None:
        short = estimate_input_tokens({"messages": [{"role": "user", "content": "a"}]})
        long = estimate_input_tokens({"messages": [{"role": "user", "content": "a" * 1000}]})
        self.assertGreaterEqual(short, 512)
        self.assertGreater(long, short)

    def test_input_estimate_does_not_count_each_utf8_byte_as_a_token(self) -> None:
        body = {"messages": [{"role": "user", "content": "数学证明与工具调用" * 2000}]}
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        estimate = estimate_input_tokens(body)
        self.assertLess(estimate, len(encoded))
        self.assertGreater(estimate, len(encoded) // 3)


if __name__ == "__main__":
    unittest.main()
