"""VideoClient 与 ChatClient 测试。

对应 review 发现：
- ``VideoClient`` 不校验 prompt，空提示词可提交有成本的视频任务；
- ``VideoClient`` 用 ``-1`` 表示所有失败，超时与任务失败无法区分；
- ``ChatClient`` 的 ``model_tier`` 在 ``model != 'gemini'`` 时被静默丢弃；
- 三个客户端的 ``status='all'`` 处理不一致。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ixspy_ai_api import (  # noqa: E402
    APIError,
    ChatClient,
    TaskFailedError,
    TaskTimeoutError,
    VideoClient,
)
from ixspy_ai_api.video_client import MAX_VIDEO_IMAGES  # noqa: E402
from tests.fakes import FakeSession  # noqa: E402

A = "https://cdn.example.com/a.png"
B = "https://cdn.example.com/b.png"
C = "https://cdn.example.com/c.png"
D = "https://cdn.example.com/d.png"


class VideoClientTestCase(unittest.TestCase):
    def setUp(self):
        self.client = VideoClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def created_payload(self) -> dict:
        return self.session.json_bodies()[-1]


class TestCreateVideoValidation(VideoClientTestCase):
    def test_empty_prompt_rejected(self):
        """核心回归：旧实现完全不校验 prompt。"""
        for value in (None, "", "   "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.create_video(prompt=value)  # type: ignore[arg-type]
        self.assertEqual(self.session.call_count, 0)

    def test_non_string_prompt_rejected(self):
        with self.assertRaises(TypeError):
            self.client.create_video(prompt=["a"])  # type: ignore[arg-type]

    def test_text_only_video_allowed(self):
        self.session.enqueue_envelope({"task_id": 3})
        self.client.create_video(prompt="赛博朋克城市")
        self.assertEqual(self.created_payload(), {"prompt": "赛博朋克城市"})

    def test_ratio_validated(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_video(prompt="x", ratios="4:3")
        self.assertIn("16:9", str(ctx.exception))
        self.assertEqual(self.session.call_count, 0)

    def test_valid_ratios_accepted(self):
        for ratio in ("16:9", "9:16"):
            with self.subTest(ratio=ratio):
                self.session.enqueue_envelope({"task_id": 1})
                self.client.create_video(prompt="x", ratios=ratio)
                self.assertEqual(self.created_payload()["ratios"], ratio)

    def test_ratio_omitted_when_none(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_video(prompt="x")
        self.assertNotIn("ratios", self.created_payload())

    def test_last_frame_requires_first_frame(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_video(prompt="x", last_frame=A)
        self.assertIn("first_frame", str(ctx.exception))
        self.assertEqual(self.session.call_count, 0)

    def test_reference_image_count_limit(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_video(prompt="x", reference_image=[A, B, C, D])
        self.assertIn(str(MAX_VIDEO_IMAGES), str(ctx.exception))

    def test_total_image_limit_combines_reference_and_frames(self):
        with self.assertRaises(ValueError):
            self.client.create_video(prompt="x", reference_image=[A, B], first_frame=C, last_frame=D)

    def test_three_images_allowed(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_video(prompt="x", reference_image=[A, B], first_frame=C)
        payload = self.created_payload()
        self.assertEqual(payload["reference_image"], [A, B])
        self.assertEqual(payload["first_frame"], C)

    def test_empty_reference_list_rejected(self):
        with self.assertRaises(ValueError):
            self.client.create_video(prompt="x", reference_image=[])

    def test_single_reference_image_becomes_list(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_video(prompt="x", reference_image=A)
        self.assertEqual(self.created_payload()["reference_image"], [A])

    def test_tuple_reference_images_supported(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_video(prompt="x", reference_image=(A, B))  # type: ignore[arg-type]
        self.assertEqual(self.created_payload()["reference_image"], [A, B])

    def test_frames_are_not_wrapped_in_list(self):
        """首帧/尾帧必须是单张字符串，不能发成数组。"""
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_video(prompt="x", first_frame=A, last_frame=B)
        payload = self.created_payload()
        self.assertIsInstance(payload["first_frame"], str)
        self.assertIsInstance(payload["last_frame"], str)

    def test_validation_errors_are_aggregated(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_video(prompt="x", reference_image=[A, B, C, D], last_frame=D)
        message = str(ctx.exception)
        self.assertIn("最多支持", message)
        self.assertIn("必须同时传入", message)

    def test_missing_task_id_reported(self):
        from ixspy_ai_api import APIResponseError
        self.session.enqueue_envelope({})
        with self.assertRaises(APIResponseError):
            self.client.create_video(prompt="x")


class TestVideoPolling(VideoClientTestCase):
    def test_wait_returns_completed_payload(self):
        self.session.enqueue_envelope({"status": "queued"})
        self.session.enqueue_envelope({"status": "completed", "video_url": "https://cdn.example.com/v.mp4"})
        result = self.client.wait_for_video_completion(1, poll_interval=0, timeout=10)
        self.assertEqual(result["video_url"], "https://cdn.example.com/v.mp4")

    def test_task_failure_raises_task_failed_error_with_code_1000(self):
        """核心回归：旧实现所有失败都用 code=-1。"""
        self.session.enqueue_envelope({"status": "error", "error": "内容审核未通过"})
        with self.assertRaises(TaskFailedError) as ctx:
            self.client.wait_for_video_completion(5, poll_interval=0, timeout=10)
        self.assertEqual(ctx.exception.code, 1000)
        self.assertEqual(ctx.exception.task_id, 5)
        self.assertIn("内容审核未通过", ctx.exception.message)

    def test_timeout_raises_task_timeout_error_not_task_failed(self):
        """核心回归：视频超时说明任务可能仍在跑，不能报成“失败”。"""
        for _ in range(20):
            self.session.enqueue_envelope({"status": "processing"})
        with self.assertRaises(TaskTimeoutError) as ctx:
            self.client.wait_for_video_completion(5, poll_interval=0.005, timeout=0.03)
        self.assertEqual(ctx.exception.code, 1001)
        self.assertIsNone(ctx.exception.time, "本地错误不应伪造时间戳")
        self.assertNotIsInstance(ctx.exception, TaskFailedError)

    def test_error_message_names_video_task(self):
        self.session.enqueue_envelope({"status": "error"})
        with self.assertRaises(TaskFailedError) as ctx:
            self.client.wait_for_video_completion(5, poll_interval=0, timeout=10)
        self.assertIn("视频任务", ctx.exception.message)

    def test_default_poll_interval_and_timeout_are_sane(self):
        import inspect

        params = inspect.signature(VideoClient.wait_for_video_completion).parameters
        self.assertEqual(params["poll_interval"].default, 15)
        self.assertEqual(params["timeout"].default, 600)

    def test_get_video_url(self):
        self.session.enqueue_envelope({"status": "completed", "video_url": "https://cdn.example.com/v.mp4"})
        self.assertEqual(self.client.get_video_url(1), "https://cdn.example.com/v.mp4")

    def test_get_video_url_reports_failed_task(self):
        self.session.enqueue_envelope({"status": "error", "error": "failed"})
        with self.assertRaises(TaskFailedError):
            self.client.get_video_url(1)

    def test_get_video_url_missing_field_is_api_error(self):
        from ixspy_ai_api import APIResponseError
        self.session.enqueue_envelope({"status": "processing"})
        with self.assertRaises(APIResponseError) as ctx:
            self.client.get_video_url(1)
        self.assertIn("video_url", ctx.exception.message)

    def test_get_video_url_error_catchable_as_api_error(self):
        self.session.enqueue_envelope({"status": "processing"})
        with self.assertRaises(APIError):
            self.client.get_video_url(1)


class TestListVideoTasks(VideoClientTestCase):
    def test_default_params(self):
        self.session.enqueue_envelope({"total": 1})
        self.client.list_video_tasks()
        self.assertEqual(self.session.last_call["params"], {"page": 1, "page_size": 20})

    def test_status_all_omitted(self):
        self.session.enqueue_envelope({"total": 1})
        self.client.list_video_tasks(status="all")
        self.assertNotIn("status", self.session.last_call["params"])

    def test_status_filter_sent(self):
        self.session.enqueue_envelope({"total": 1})
        self.client.list_video_tasks(status="completed")
        self.assertEqual(self.session.last_call["params"]["status"], "completed")

    def test_pagination_validated(self):
        with self.assertRaises(ValueError):
            self.client.list_video_tasks(page=0)


class ChatClientTestCase(unittest.TestCase):
    def setUp(self):
        self.client = ChatClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def payload(self) -> dict:
        return self.session.json_bodies()[-1]


class TestChatGenerate(ChatClientTestCase):
    def test_empty_prompt_rejected(self):
        for value in (None, "", "  "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.generate(prompt=value)  # type: ignore[arg-type]
        self.assertEqual(self.session.call_count, 0)

    def test_model_default_is_omitted_not_forced_to_auto(self):
        """与 ImageClient 的 ``model=None`` 语义保持一致。"""
        self.session.enqueue_envelope({"content": "hi"})
        self.client.generate(prompt="hello")
        self.assertNotIn("model", self.payload())

    def test_explicit_model_is_sent(self):
        self.session.enqueue_envelope({"content": "hi"})
        self.client.generate(prompt="hello", model="chatgpt")
        self.assertEqual(self.payload()["model"], "chatgpt")

    def test_unsupported_model_rejected(self):
        with self.assertRaises(ValueError):
            self.client.generate(prompt="hello", model="claude")

    def test_model_tier_requires_gemini(self):
        """核心回归：旧实现静默丢弃 model_tier，用户以为参数已生效。"""
        with self.assertRaises(ValueError) as ctx:
            self.client.generate(prompt="hello", model="chatgpt", model_tier="Pro")
        self.assertIn("gemini", str(ctx.exception))
        self.assertEqual(self.session.call_count, 0)

    def test_model_tier_without_model_rejected(self):
        with self.assertRaises(ValueError):
            self.client.generate(prompt="hello", model_tier="Pro")

    def test_model_tier_sent_with_gemini(self):
        self.session.enqueue_envelope({"content": "hi"})
        self.client.generate(prompt="hello", model="gemini", model_tier="Pro")
        self.assertEqual(self.payload(), {"prompt": "hello", "model": "gemini", "model_tier": "Pro"})

    def test_invalid_model_tier_rejected(self):
        with self.assertRaises(ValueError):
            self.client.generate(prompt="hello", model="gemini", model_tier="Turbo")

    def test_image_input_normalised(self):
        self.session.enqueue_envelope({"content": "描述"})
        self.client.generate(prompt="描述图片", original_image=A, model="chatgpt")
        self.assertEqual(self.payload()["original_image"], A)

    def test_image_list_supported(self):
        self.session.enqueue_envelope({"content": "描述"})
        self.client.generate(prompt="描述", original_image=[A, B])
        self.assertEqual(self.payload()["original_image"], [A, B])

    def test_missing_image_file_rejected(self):
        with self.assertRaises(FileNotFoundError):
            self.client.generate(prompt="描述", original_image="images/missing.png")
        self.assertEqual(self.session.call_count, 0)


class TestListChatTasks(ChatClientTestCase):
    def test_status_all_omitted_like_other_clients(self):
        """核心回归：旧实现无条件发送 status='all'。"""
        self.session.enqueue_envelope({"total": 0})
        self.client.list_chat_tasks(status="all")
        self.assertNotIn("status", self.session.last_call["params"])

    def test_default_omits_status(self):
        self.session.enqueue_envelope({"total": 0})
        self.client.list_chat_tasks()
        self.assertNotIn("status", self.session.last_call["params"])

    def test_status_filter_sent(self):
        self.session.enqueue_envelope({"total": 0})
        self.client.list_chat_tasks(status="completed")
        self.assertEqual(self.session.last_call["params"]["status"], "completed")

    def test_pagination_validated(self):
        with self.assertRaises(ValueError):
            self.client.list_chat_tasks(page_size=0)


if __name__ == "__main__":
    unittest.main()
