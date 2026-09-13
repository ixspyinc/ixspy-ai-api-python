"""基础客户端测试：响应信封、HTTP 错误映射、重试策略、网络异常。

对应 review 发现：
- 缺少 ``raise_for_status()`` 导致 429/401/5xx 被误报为“响应不是合法 JSON”；
- 业务错误码与轮询错误码混用 ``-1``，调用方无法区分失败原因；
- 缺少 ``data`` 字段时抛裸 ``KeyError`` 而不是 :class:`APIError`。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from ixspy_ai_api import (  # noqa: E402
    AIClient,
    APIConnectionError,
    APIError,
    APIResponseError,
    AuthError,
    RateLimitError,
    ServerError,
)
from ixspy_ai_api.ai_client import RETRY_ALLOWED_METHODS, RETRY_TOTAL  # noqa: E402
from tests.fakes import FakeSession  # noqa: E402


class RaisingSession(FakeSession):
    """请求时抛出指定异常，用于模拟网络层故障。"""

    def __init__(self, exception: BaseException):
        super().__init__()
        self.exception = exception

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        raise self.exception


class TestClientConstruction(unittest.TestCase):
    def test_empty_api_key_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(api_key=bad), self.assertRaises(ValueError):
                AIClient(api_key=bad)

    def test_base_url_trailing_slash_removed(self):
        client = AIClient(api_key="k", base_url="https://example.com/api/")
        self.assertEqual(client.base_url, "https://example.com/api")

    def test_default_headers(self):
        client = AIClient(api_key="secret")
        self.assertEqual(client.session.headers["Authorization"], "Bearer secret")
        self.assertIn("ixspy-ai-api-python/", client.session.headers["User-Agent"])

    def test_upload_timeout_defaults_to_request_timeout_when_none(self):
        client = AIClient(api_key="k", timeout=42, upload_timeout=None)
        self.assertEqual(client.upload_timeout, 42)

    def test_context_manager_closes_session(self):
        client = AIClient(api_key="k")
        session = FakeSession()
        client.session = session
        with client as entered:
            self.assertIs(entered, client)
        self.assertTrue(session.closed)


class TestRetryPolicy(unittest.TestCase):
    """创建任务的 POST 绝不能自动重试，否则会重复生成并重复计费。"""

    def test_default_adapter_forbids_post_retry(self):
        client = AIClient(api_key="k")
        adapter = client._default_adapter
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.max_retries.total, RETRY_TOTAL)
        self.assertNotIn("POST", adapter.max_retries.allowed_methods)
        self.assertEqual(adapter.max_retries.allowed_methods, RETRY_ALLOWED_METHODS)

    def test_upload_adapter_allows_post_retry(self):
        client = AIClient(api_key="k")
        self.assertIn("POST", client._upload_adapter.max_retries.allowed_methods)

    def test_retries_can_be_disabled(self):
        client = AIClient(api_key="k", retries=0)
        self.assertIsNone(client._default_adapter)
        self.assertIsNone(client._upload_adapter)

    def test_upload_keeps_task_retry_policy_unchanged(self):
        from unittest.mock import patch

        with AIClient(api_key="k") as client:
            task_url = client.base_url + "/v1/images/generations/custom_composition"
            upload_url = client.base_url + "/v1/images/upload"

            def send_upload(*args, **kwargs):
                task_adapter = client.session.get_adapter(task_url)
                self.assertFalse(task_adapter.max_retries.is_retry("POST", 503))
                self.assertTrue(client.session.get_adapter(upload_url).max_retries.is_retry("POST", 503))
                response = requests.Response()
                response.status_code = 200
                response._content = b'{"error": {"code": 0}, "data": {"url": "https://cdn.example/a"}}'
                return response

            with patch.object(client._upload_adapter, "send", side_effect=send_upload):
                client.upload_image_base64("aGVsbG8=")
            self.assertFalse(client.session.get_adapter(task_url).max_retries.is_retry("POST", 503))

    def test_context_manager_closes_upload_pool_even_after_failure(self):
        from unittest.mock import patch

        client = AIClient(api_key="k")
        with patch.object(client._upload_adapter, "close") as close_upload:
            with self.assertRaises(RuntimeError), client:
                raise RuntimeError("caller failed")
            close_upload.assert_called_once()


class TestResponseEnvelope(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def test_success_returns_data(self):
        self.session.enqueue_envelope({"task_id": 11})
        self.assertEqual(self.client._request("GET", "/x"), {"task_id": 11})

    def test_business_error_raises_api_error_with_server_code(self):
        self.session.enqueue_error(2001, "参数不合法")
        with self.assertRaises(APIError) as ctx:
            self.client._request("GET", "/x")
        self.assertEqual(ctx.exception.code, 2001)
        self.assertEqual(ctx.exception.message, "参数不合法")
        self.assertEqual(ctx.exception.time, 1700000000.0)

    def test_missing_error_field_is_reported_explicitly(self):
        """旧的实现会把缺少 'error' 的响应静默当成 code=-1 的业务错误。"""
        self.session.enqueue_json({"data": {"task_id": 1}})
        with self.assertRaises(APIResponseError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("'error'", ctx.exception.message)

    def test_missing_data_field_is_reported_explicitly(self):
        """旧实现返回 {} 后由调用方抛裸 KeyError。"""
        self.session.enqueue_json({"error": {"code": 0}})
        with self.assertRaises(APIResponseError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("'data'", ctx.exception.message)

    def test_null_data_field_is_reported(self):
        self.session.enqueue_json({"error": {"code": 0}, "data": None})
        with self.assertRaises(APIResponseError):
            self.client._request("GET", "/x")

    def test_non_object_data_is_reported(self):
        self.session.enqueue_json({"error": {"code": 0}, "data": [1, 2, 3]})
        with self.assertRaises(APIResponseError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("list", ctx.exception.message)

    def test_non_object_envelope_is_reported(self):
        self.session.enqueue_json([1, 2, 3])
        with self.assertRaises(APIResponseError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("JSON 对象", ctx.exception.message)

    def test_non_json_body_is_reported_with_snippet(self):
        self.session.enqueue_text("<html>502 Bad Gateway</html>", status_code=200)
        with self.assertRaises(APIResponseError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("合法 JSON", ctx.exception.message)
        self.assertIn("502 Bad Gateway", ctx.exception.message)

    def test_error_field_not_object(self):
        self.session.enqueue_json({"error": "oops", "data": {}})
        with self.assertRaises(APIResponseError):
            self.client._request("GET", "/x")


class TestHttpStatusMapping(unittest.TestCase):
    """旧实现完全不看 HTTP 状态码，429/401/5xx 都会退化成“响应不是合法 JSON”。"""

    def setUp(self):
        self.client = AIClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def test_401_maps_to_auth_error(self):
        self.session.enqueue_json({"message": "invalid token"}, status_code=401)
        with self.assertRaises(AuthError) as ctx:
            self.client._request("GET", "/x")
        self.assertEqual(ctx.exception.http_status, 401)
        self.assertIn("invalid token", ctx.exception.message)
        self.assertIn("api_key", ctx.exception.message)

    def test_403_maps_to_auth_error(self):
        self.session.enqueue_text("Forbidden", status_code=403)
        with self.assertRaises(AuthError):
            self.client._request("GET", "/x")

    def test_429_maps_to_rate_limit_error_with_retry_after(self):
        self.session.enqueue_text("too many requests", status_code=429,
                                  headers={"Retry-After": "12"})
        with self.assertRaises(RateLimitError) as ctx:
            self.client._request("GET", "/x")
        self.assertEqual(ctx.exception.retry_after, 12.0)
        self.assertIn("12", ctx.exception.message)

    def test_429_without_retry_after_header(self):
        self.session.enqueue_text("slow down", status_code=429)
        with self.assertRaises(RateLimitError) as ctx:
            self.client._request("GET", "/x")
        self.assertIsNone(ctx.exception.retry_after)

    def test_5xx_maps_to_server_error(self):
        self.session.enqueue_text("upstream exploded", status_code=503)
        with self.assertRaises(ServerError) as ctx:
            self.client._request("GET", "/x")
        self.assertEqual(ctx.exception.http_status, 503)

    def test_400_maps_to_base_api_error_keeping_status(self):
        self.session.enqueue_json({"error": {"code": 4001, "message": "bad request"}}, status_code=400)
        with self.assertRaises(APIError) as ctx:
            self.client._request("GET", "/x")
        self.assertEqual(ctx.exception.http_status, 400)
        self.assertIn("bad request", ctx.exception.message)

    def test_html_error_body_does_not_leak_as_json_error(self):
        self.session.enqueue_text("<html><body>Gateway Timeout</body></html>", status_code=504)
        with self.assertRaises(ServerError) as ctx:
            self.client._request("GET", "/x")
        self.assertIn("Gateway Timeout", ctx.exception.message)


class TestNetworkFailures(unittest.TestCase):
    def test_timeout_maps_to_connection_error(self):
        client = AIClient(api_key="k", timeout=5)
        client.session = RaisingSession(requests.exceptions.Timeout("read timed out"))
        with self.assertRaises(APIConnectionError) as ctx:
            client._request("GET", "/x")
        self.assertIn("超时", ctx.exception.message)
        self.assertIsInstance(ctx.exception.original, requests.exceptions.Timeout)

    def test_connection_error_is_wrapped(self):
        client = AIClient(api_key="k")
        client.session = RaisingSession(requests.exceptions.ConnectionError("dns boom"))
        with self.assertRaises(APIConnectionError) as ctx:
            client._request("GET", "/x")
        self.assertIn("dns boom", ctx.exception.message)

    def test_connection_error_is_catchable_as_api_error(self):
        """用户只需捕获 APIError 即可覆盖网络故障。"""
        client = AIClient(api_key="k")
        client.session = RaisingSession(requests.exceptions.ConnectionError("boom"))
        with self.assertRaises(APIError):
            client._request("GET", "/x")


class TestExceptionHierarchy(unittest.TestCase):
    def test_all_errors_share_base_class(self):
        for exc_type in (APIResponseError, APIConnectionError, AuthError, RateLimitError, ServerError):
            with self.subTest(exc_type=exc_type.__name__):
                self.assertTrue(issubclass(exc_type, APIError))

    def test_error_message_contains_code_status_and_task(self):
        error = APIError(code=5, message="boom", http_status=500, task_id=99)
        self.assertIn("5", str(error))
        self.assertIn("HTTP 500", str(error))
        self.assertIn("task 99", str(error))
        self.assertIn("boom", str(error))

    def test_local_error_time_is_none_not_zero(self):
        """旧实现用 time=0 占据时间戳字段，会污染日志分析。"""
        error = APIError(code=-1, message="boom")
        self.assertIsNone(error.time)


if __name__ == "__main__":
    unittest.main()
