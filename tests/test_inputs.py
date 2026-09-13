"""图片输入归一化测试。

对应 review 发现：
- 路径拼写错误时原样发给服务端，用户得到难以理解的 400；
- ``data:image/png;base64,`` 前缀未剥离，白白增加 33% 请求体；
- URL-safe/无 padding 的 Base64 被误判；
- 缺少体积预校验。

说明：本文件自身（``__file__``）被复用为“确实存在的本地文件”，以免测试依赖
创建临时目录 —— 部分受限执行环境不允许在程序新建的目录中写文件。
"""

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ixspy_ai_api import AIClient  # noqa: E402
from ixspy_ai_api.ai_client import (  # noqa: E402
    _looks_like_base64_image,
    _looks_like_local_path,
    _strip_data_uri,
)
from tests.fakes import FakeSession  # noqa: E402

#: 一段真实可解码的 PNG 头 + 填充数据，编码后长度足以通过裸 Base64 长度门槛。
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 2
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode()

#: 一个确实存在的本地文件（本测试文件自身）。
EXISTING_FILE = Path(__file__).resolve()


class TestDataUriStripping(unittest.TestCase):
    def test_prefix_is_removed(self):
        payload, mime = _strip_data_uri(f"data:image/png;base64,{PNG_BASE64}")
        self.assertEqual(payload, PNG_BASE64)
        self.assertEqual(mime, "image/png")

    def test_non_data_uri_passes_through(self):
        payload, mime = _strip_data_uri(PNG_BASE64)
        self.assertEqual(payload, PNG_BASE64)
        self.assertIsNone(mime)

    def test_missing_comma_is_rejected(self):
        with self.assertRaises(ValueError):
            _strip_data_uri("data:image/png;base64")

    def test_non_base64_data_uri_is_rejected_with_guidance(self):
        with self.assertRaises(ValueError) as ctx:
            _strip_data_uri("data:image/svg+xml,%3Csvg%3E")
        self.assertIn("Base64", str(ctx.exception))


class TestBase64Detection(unittest.TestCase):
    def test_padded_base64_detected(self):
        self.assertTrue(_looks_like_base64_image(PNG_BASE64))

    def test_unpadded_base64_detected(self):
        unpadded = PNG_BASE64.rstrip("=")
        self.assertTrue(_looks_like_base64_image(unpadded))

    def test_data_uri_detected(self):
        self.assertTrue(_looks_like_base64_image(f"data:image/jpeg;base64,{PNG_BASE64}"))

    def test_internal_whitespace_tolerated(self):
        wrapped = "\n".join(PNG_BASE64[i:i + 60] for i in range(0, len(PNG_BASE64), 60))
        self.assertTrue(_looks_like_base64_image(wrapped))

    def test_short_string_is_not_treated_as_base64(self):
        """短的普通字符串（例如 API key）不应被误判为图片数据。"""
        self.assertFalse(_looks_like_base64_image("sk-abcdef1234567890"))
        self.assertFalse(_looks_like_base64_image("hello"))

    def test_non_image_data_uri_is_not_detected(self):
        self.assertFalse(_looks_like_base64_image("data:text/plain;base64,aGVsbG8="))

    def test_garbage_data_uri_is_not_detected(self):
        self.assertFalse(_looks_like_base64_image("data:image/png;base64,!!!not base64!!!"))

    def test_empty_is_not_detected(self):
        self.assertFalse(_looks_like_base64_image("   "))

    def test_backwards_compatible_classmethod(self):
        self.assertTrue(AIClient._is_base64_image_input(PNG_BASE64))
        self.assertFalse(AIClient._is_base64_image_input("nope"))


class TestLocalPathHeuristic(unittest.TestCase):
    def test_paths_recognised(self):
        for value in (r"C:\images\a.jpg", "/tmp/a.png", "dir/a.png", "C:relative.jpg", "photo.WEBP"):
            with self.subTest(value=value):
                self.assertTrue(_looks_like_local_path(value))

    def test_non_paths_not_recognised(self):
        for value in ("speaker", "acme-asset-12345"):
            with self.subTest(value=value):
                self.assertFalse(_looks_like_local_path(value))


class TestPrepareSingleImage(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def test_http_url_returned_unchanged(self):
        url = "https://cdn.example.com/a.png"
        self.assertEqual(self.client._prepare_single_image(url), url)
        self.assertEqual(self.session.call_count, 0)

    def test_missing_local_path_raises_file_not_found(self):
        """核心回归：旧实现把拼错的路径静默发给服务端。"""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.client._prepare_single_image("images/definitely-missing.png")
        self.assertIn("definitely-missing.png", str(ctx.exception))
        self.assertEqual(self.session.call_count, 0, "不应发起任何网络请求")

    def test_missing_absolute_path_raises_file_not_found(self):
        missing = str(Path(__file__).resolve().parent / "no-such-dir" / "missing.png")
        with self.assertRaises(FileNotFoundError):
            self.client._prepare_single_image(missing)

    def test_existing_local_file_is_uploaded(self):
        self.session.enqueue_envelope({"url": "https://cdn.example.com/uploaded.png"})
        result = self.client._prepare_single_image(EXISTING_FILE)
        self.assertEqual(result, "https://cdn.example.com/uploaded.png")
        self.assertIn("/v1/images/upload", self.session.last_call["url"])
        self.assertEqual(self.session.last_call["method"], "POST")
        uploaded_name = self.session.last_call["files"]["image"][0]
        self.assertEqual(uploaded_name, EXISTING_FILE.name)

    def test_existing_local_file_as_string_is_uploaded(self):
        self.session.enqueue_envelope({"url": "https://cdn.example.com/uploaded.png"})
        self.assertEqual(
            self.client._prepare_single_image(str(EXISTING_FILE)),
            "https://cdn.example.com/uploaded.png",
        )

    def test_oversized_file_is_rejected_before_upload(self):
        client = AIClient(api_key="k", max_upload_bytes=16)
        client.session = self.session
        with self.assertRaises(ValueError) as ctx:
            client._prepare_single_image(EXISTING_FILE)
        self.assertIn("超过上限", str(ctx.exception))
        self.assertEqual(self.session.call_count, 0, "超限文件不应被上传")

    def test_size_limit_can_be_disabled(self):
        client = AIClient(api_key="k", max_upload_bytes=0)
        client.session = self.session
        self.session.enqueue_envelope({"url": "https://cdn.example.com/x.png"})
        self.assertEqual(client._prepare_single_image(EXISTING_FILE), "https://cdn.example.com/x.png")

    def test_empty_string_rejected(self):
        for value in ("", "   "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client._prepare_single_image(value)

    def test_non_string_input_rejected(self):
        with self.assertRaises(TypeError):
            self.client._prepare_single_image(123)  # type: ignore[arg-type]

    def test_raw_base64_is_uploaded_without_prefix(self):
        self.session.enqueue_envelope({"url": "https://cdn.example.com/b64.png"})
        self.client._prepare_single_image(PNG_BASE64)
        self.assertEqual(self.session.json_bodies()[0], {"image_base64": PNG_BASE64})

    def test_data_uri_prefix_is_stripped_before_upload(self):
        """核心回归：前缀不应被原样发给服务端。"""
        self.session.enqueue_envelope({"url": "https://cdn.example.com/uri.png"})
        self.client._prepare_single_image(f"data:image/png;base64,{PNG_BASE64}")
        body = self.session.json_bodies()[0]
        self.assertEqual(body, {"image_base64": PNG_BASE64})
        self.assertNotIn("data:image", body["image_base64"])

    def test_unknown_non_path_string_passes_through(self):
        """既非 URL、路径，也非 Base64 的标识符仍交由服务端校验。"""
        self.assertEqual(self.client._prepare_single_image("acme-asset-42"), "acme-asset-42")
        self.assertEqual(self.session.call_count, 0)


class TestUploadImageBase64(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def test_prefix_stripped(self):
        self.session.enqueue_envelope({"url": "https://cdn.example.com/x.png"})
        self.client.upload_image_base64(f"data:image/webp;base64,{PNG_BASE64}")
        self.assertEqual(self.session.json_bodies()[0]["image_base64"], PNG_BASE64)

    def test_empty_payload_rejected(self):
        for value in ("", "   ", "data:image/png;base64,", "data:image/png;base64,   "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.upload_image_base64(value)

    def test_missing_url_field_reports_response_error(self):
        from ixspy_ai_api import APIResponseError
        self.session.enqueue_envelope({"something": "else"})
        with self.assertRaises(APIResponseError) as ctx:
            self.client.upload_image_base64(PNG_BASE64)
        self.assertIn("url", ctx.exception.message)

    def test_multipart_upload_does_not_set_content_type(self):
        """multipart 的 Content-Type 必须留给 requests 生成 boundary。"""
        self.session.enqueue_envelope({"url": "https://cdn.example.com/a.png"})
        self.client.upload_image_file(EXISTING_FILE)
        files = self.session.last_call["files"]
        self.assertIn("image", files)
        self.assertNotIn("Content-Type", self.session.last_call.get("headers", {}))

    def test_upload_missing_file_raises_before_request(self):
        with self.assertRaises(FileNotFoundError):
            self.client.upload_image_file(Path(__file__).resolve().parent / "nope.png")
        self.assertEqual(self.session.call_count, 0)

    def test_json_request_sets_content_type(self):
        self.session.enqueue_envelope({"url": "https://cdn.example.com/a.png"})
        self.client.upload_image_base64(PNG_BASE64)
        self.assertEqual(self.session.last_call["headers"]["Content-Type"], "application/json")


class TestPrepareImagesShape(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(api_key="k")
        self.client.session = FakeSession()

    def test_scalar_returns_string(self):
        result = self.client._prepare_images("https://cdn.example.com/a.png")
        self.assertIsInstance(result, str)

    def test_list_returns_list(self):
        result = self.client._prepare_images([
            "https://cdn.example.com/a.png",
            "https://cdn.example.com/b.png",
        ])
        self.assertEqual(result, ["https://cdn.example.com/a.png", "https://cdn.example.com/b.png"])

    def test_list_helper_always_returns_list(self):
        self.assertEqual(
            self.client._prepare_image_list("https://cdn.example.com/a.png"),
            ["https://cdn.example.com/a.png"],
        )

    def test_unsupported_type_rejected(self):
        with self.assertRaises(TypeError):
            self.client._prepare_images({"not": "supported"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
