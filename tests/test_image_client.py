"""ImageClient 载荷构造与轮询测试。

对应 review 发现：
- ``generate()`` 默认 ``timeout=None`` 导致无限阻塞；
- ``prompt`` 校验只判断 ``is None``，空字符串可以提交；
- ``model`` 相关分支存在死代码与客户端硬编码支持矩阵；
- 轮询错误码不可区分、超时后仍会多等一个 interval。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ixspy_ai_api import (  # noqa: E402
    DEFAULT_WAIT_TIMEOUT,
    APIError,
    APIResponseError,
    ImageClient,
    TaskFailedError,
    TaskTimeoutError,
)
from ixspy_ai_api.image_client import MODEL_SELECTABLE_TYPES, TASK_SPECS  # noqa: E402
from tests.fakes import FakeSession  # noqa: E402


class ImageClientTestCase(unittest.TestCase):
    def setUp(self):
        self.client = ImageClient(api_key="k")
        self.session = FakeSession()
        self.client.session = self.session

    def created_payload(self) -> dict:
        """返回最近一次请求的 JSON 载荷。"""
        return self.session.json_bodies()[-1]


class TestTaskSpecRegistry(unittest.TestCase):
    def test_all_types_declared(self):
        expected = {
            "custom_composition_multi",
            "custom_composition",
            "scene_replacement",
            "product_replacement",
            "product_recoloring",
            "partial_redraw",
            "smart_expand",
            "translation",
            "ai_upscale_2k",
        }
        self.assertEqual(set(TASK_SPECS), expected)

    def test_type_constants_match_registry(self):
        for name in dir(ImageClient):
            if not name.startswith("TYPE_"):
                continue
            with self.subTest(constant=name):
                self.assertIn(getattr(ImageClient, name), TASK_SPECS)

    def test_only_model_selectable_types_accept_model(self):
        for task_type, spec in TASK_SPECS.items():
            with self.subTest(task_type=task_type):
                if task_type == "ai_upscale_2k":
                    self.assertNotIn("model", spec.optional)
                    self.assertNotIn(task_type, MODEL_SELECTABLE_TYPES)
                else:
                    self.assertIn("model", spec.optional)

    def test_required_fields_are_subset_of_known_fields(self):
        for task_type, spec in TASK_SPECS.items():
            with self.subTest(task_type=task_type):
                self.assertTrue(spec.required <= spec.known_fields, f"{task_type} 必填字段未声明")

    def test_image_fields_are_declared(self):
        for task_type, spec in TASK_SPECS.items():
            with self.subTest(task_type=task_type):
                self.assertTrue(spec.image_fields <= spec.known_fields, f"{task_type} 图片字段未声明")


class TestCreateTaskValidation(ImageClientTestCase):
    def test_unknown_task_type_lists_options(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_task("no_such_type", prompt="x")
        self.assertIn("no_such_type", str(ctx.exception))
        self.assertIn("custom_composition", str(ctx.exception))

    def test_unknown_parameter_rejected_instead_of_silently_sent(self):
        """旧实现把任意 kwargs 直接交给服务端。"""
        with self.assertRaises(ValueError) as ctx:
            self.client.create_task("custom_composition", prompt="x", typo_param="oops")
        self.assertIn("typo_param", str(ctx.exception))

    def test_missing_required_parameters_are_all_reported(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_task("product_replacement")
        message = str(ctx.exception)
        self.assertIn("original_image", message)
        self.assertIn("reference_image", message)

    def test_missing_task_id_field(self):
        self.session.enqueue_envelope({"unexpected": 1})
        with self.assertRaises(APIResponseError) as ctx:
            self.client.create_task("custom_composition", prompt="x")
        self.assertIn("task_id", ctx.exception.message)

    def test_non_integer_task_id_rejected(self):
        self.session.enqueue_envelope({"task_id": "not-a-number"})
        with self.assertRaises(APIResponseError):
            self.client.create_task("custom_composition", prompt="x")

    def test_string_task_id_coerced_to_int(self):
        self.session.enqueue_envelope({"task_id": "42"})
        self.assertEqual(self.client.create_task("custom_composition", prompt="x"), 42)

    def test_endpoint_uses_task_type(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_task("custom_composition", prompt="x")
        self.assertIn("/v1/images/generations/custom_composition", self.session.last_call["url"])
        self.assertEqual(self.session.last_call["method"], "POST")


class TestPromptValidation(ImageClientTestCase):
    def test_empty_prompt_rejected(self):
        """核心回归：旧实现 `if prompt is None` 放行了空字符串。"""
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.create_custom_composition(prompt=value)
        self.assertEqual(self.session.call_count, 0)

    def test_none_prompt_rejected(self):
        with self.assertRaises(ValueError):
            self.client.create_custom_composition(prompt=None)

    def test_non_string_prompt_rejected(self):
        with self.assertRaises(TypeError):
            self.client.create_custom_composition(prompt=123)  # type: ignore[arg-type]

    def test_valid_prompt_reaches_payload(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="  移除背景  ")
        self.assertEqual(self.created_payload()["prompt"], "  移除背景  ")


class TestModelHandling(ImageClientTestCase):
    def test_unsupported_model_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_custom_composition(prompt="x", model="gpt-5")
        self.assertIn("auto", str(ctx.exception))

    def test_model_none_is_not_sent(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="x", model=None)
        self.assertNotIn("model", self.created_payload())

    def test_model_auto_is_sent(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="x", model="auto")
        self.assertEqual(self.created_payload()["model"], "auto")

    def test_model_rejected_for_ai_upscale(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_task("ai_upscale_2k", original_image="a.png", model="gemini")
        self.assertIn("不支持", str(ctx.exception))

    def test_positional_wrapper_for_upscale_has_no_model_parameter(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_ai_upscale_2k("acme-asset-1")
        self.assertNotIn("model", self.created_payload())


class TestPayloadConstruction(ImageClientTestCase):
    def test_custom_composition_defaults(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="x")
        self.assertEqual(self.created_payload(), {"prompt": "x", "ratios": "auto"})

    def test_custom_composition_omits_none_image(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="x")
        self.assertNotIn("original_image", self.created_payload())

    def test_custom_composition_passes_url_through(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition(prompt="x", original_image="https://cdn.example.com/a.png")
        self.assertEqual(self.created_payload()["original_image"], "https://cdn.example.com/a.png")

    def test_multi_composition_sends_list(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition_multi(
            original_images=["https://cdn.example.com/a.png", "https://cdn.example.com/b.png"],
            prompt="merge",
        )
        self.assertEqual(
            self.created_payload()["original_image"],
            ["https://cdn.example.com/a.png", "https://cdn.example.com/b.png"],
        )

    def test_multi_composition_without_images_omits_field(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_custom_composition_multi(prompt="text only")
        self.assertNotIn("original_image", self.created_payload())

    def test_product_recoloring(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_product_recoloring("https://cdn.example.com/a.png", "#ff4500ff")
        self.assertEqual(
            self.created_payload(),
            {"original_image": "https://cdn.example.com/a.png", "color": "#ff4500ff"},
        )

    def test_smart_expand(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_smart_expand("https://cdn.example.com/a.png", "top_left", "1:1")
        self.assertEqual(
            self.created_payload(),
            {"original_image": "https://cdn.example.com/a.png", "direction": "top_left", "ratios": "1:1"},
        )

    def test_translation(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_translation("https://cdn.example.com/a.png", "auto", "English")
        self.assertEqual(
            self.created_payload(),
            {
                "original_image": "https://cdn.example.com/a.png",
                "source_language": "auto",
                "target_language": "English",
            },
        )

    def test_scene_replacement_requires_prompt_or_reference(self):
        with self.assertRaises(ValueError) as ctx:
            self.client.create_scene_replacement("https://cdn.example.com/a.png")
        self.assertIn("prompt", str(ctx.exception))

    def test_scene_replacement_accepts_reference_only(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_scene_replacement(
            "https://cdn.example.com/a.png",
            reference_image="https://cdn.example.com/ref.png",
        )
        payload = self.created_payload()
        self.assertIn("reference_image", payload)
        self.assertNotIn("prompt", payload)

    def test_scene_replacement_omits_empty_prompt(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_scene_replacement(
            "https://cdn.example.com/a.png",
            prompt="",
            reference_image="https://cdn.example.com/ref.png",
        )
        self.assertNotIn("prompt", self.created_payload())

    def test_partial_redraw(self):
        self.session.enqueue_envelope({"task_id": 1})
        self.client.create_partial_redraw("https://cdn.example.com/a.png", "换成红色")
        self.assertEqual(
            self.created_payload(),
            {"original_image": "https://cdn.example.com/a.png", "prompt": "换成红色"},
        )


class TestTaskStatus(ImageClientTestCase):
    def test_get_task_status(self):
        self.session.enqueue_envelope({"status": "processing", "task_id": 9})
        self.assertEqual(self.client.get_task_status(9)["status"], "processing")
        self.assertIn("/v1/images/generations/tasks/9", self.session.last_call["url"])


class TestWaitForCompletion(ImageClientTestCase):
    def test_returns_when_completed(self):
        self.session.enqueue_envelope({"status": "queued"})
        self.session.enqueue_envelope({"status": "processing"})
        self.session.enqueue_envelope({"status": "completed", "sd_image_url": "https://cdn.example.com/sd.png"})
        result = self.client.wait_for_completion(1, poll_interval=0, timeout=10)
        self.assertEqual(result["sd_image_url"], "https://cdn.example.com/sd.png")
        self.assertEqual(self.session.call_count, 3)

    def test_task_failure_raises_task_failed_error(self):
        self.session.enqueue_envelope({"status": "error", "error": "模型超时"})
        with self.assertRaises(TaskFailedError) as ctx:
            self.client.wait_for_completion(7, poll_interval=0, timeout=10)
        self.assertEqual(ctx.exception.task_id, 7)
        self.assertIn("模型超时", ctx.exception.message)

    def test_task_failure_error_is_also_api_error(self):
        self.session.enqueue_envelope({"status": "error"})
        with self.assertRaises(APIError):
            self.client.wait_for_completion(7, poll_interval=0, timeout=10)

    def test_timeout_preserves_task_id_and_hints_resume(self):
        """核心回归：旧实现抛 code=1001，且超时后还会多等一个 interval。"""
        for _ in range(6):
            self.session.enqueue_envelope({"status": "processing"})
        with self.assertRaises(TaskTimeoutError) as ctx:
            self.client.wait_for_completion(7, poll_interval=0.01, timeout=0.03)
        self.assertEqual(ctx.exception.task_id, 7)
        self.assertEqual(ctx.exception.code, 1001)
        self.assertIn("task_id", ctx.exception.message)

    def test_timeout_bounds_number_of_polls(self):
        """超时必须真实生效，而不是无限轮询。"""
        for _ in range(50):
            self.session.enqueue_envelope({"status": "queued"})
        with self.assertRaises(TaskTimeoutError):
            self.client.wait_for_completion(7, poll_interval=0.005, timeout=0.05)
        self.assertLess(self.session.call_count, 50, "超时后不应继续请求")

    def test_zero_timeout_means_unlimited(self):
        self.session.enqueue_envelope({"status": "completed"})
        result = self.client.wait_for_completion(1, poll_interval=0, timeout=0)
        self.assertEqual(result["status"], "completed")

    def test_none_timeout_means_unlimited(self):
        self.session.enqueue_envelope({"status": "completed"})
        result = self.client.wait_for_completion(1, poll_interval=0, timeout=None)
        self.assertEqual(result["status"], "completed")

    def test_unknown_status_raises_api_error(self):
        self.session.enqueue_envelope({"status": "banana"})
        with self.assertRaises(APIError) as ctx:
            self.client.wait_for_completion(1, poll_interval=0, timeout=10)
        self.assertIn("banana", ctx.exception.message)

    def test_missing_status_is_reported(self):
        self.session.enqueue_envelope({"task_id": 1})
        with self.assertRaises(APIError) as ctx:
            self.client.wait_for_completion(1, poll_interval=0, timeout=10)
        self.assertIn("None", ctx.exception.message)

    def test_negative_timeout_rejected(self):
        with self.assertRaises(ValueError):
            self.client.wait_for_completion(1, timeout=-5)

    def test_negative_poll_interval_rejected(self):
        with self.assertRaises(ValueError):
            self.client.wait_for_completion(1, poll_interval=-1)

    def test_task_failed_and_timeout_are_distinguishable(self):
        """调用方必须能区分“任务真的失败”与“本地放弃等待”。"""
        self.assertFalse(issubclass(TaskTimeoutError, TaskFailedError))
        self.assertFalse(issubclass(TaskFailedError, TaskTimeoutError))


class TestGenerate(ImageClientTestCase):
    def test_default_timeout_matches_wait_for_completion(self):
        """核心回归：旧实现 generate() 的 timeout 默认 None = 无限等待。"""
        import inspect

        generate_default = inspect.signature(ImageClient.generate).parameters["timeout"].default
        wait_default = inspect.signature(ImageClient.wait_for_completion).parameters["timeout"].default
        self.assertEqual(generate_default, wait_default)
        self.assertEqual(generate_default, DEFAULT_WAIT_TIMEOUT)
        self.assertIsNotNone(generate_default)

    def test_wait_false_returns_task_id(self):
        self.session.enqueue_envelope({"task_id": 5})
        result = self.client.generate("custom_composition", wait=False, prompt="x")
        self.assertEqual(result, 5)
        self.assertEqual(self.session.call_count, 1)

    def test_wait_true_returns_result_with_task_id(self):
        self.session.enqueue_envelope({"task_id": 5})
        self.session.enqueue_envelope({"status": "completed", "sd_image_url": "https://cdn.example.com/sd.png"})
        result = self.client.generate("custom_composition", prompt="x", poll_interval=0, timeout=10)
        self.assertEqual(result["task_id"], 5)
        self.assertEqual(result["sd_image_url"], "https://cdn.example.com/sd.png")

    def test_generate_honours_timeout(self):
        self.session.enqueue_envelope({"task_id": 5})
        for _ in range(30):
            self.session.enqueue_envelope({"status": "queued"})
        with self.assertRaises(TaskTimeoutError):
            self.client.generate("custom_composition", prompt="x", poll_interval=0.005, timeout=0.03)

    def test_generate_validates_params(self):
        with self.assertRaises(ValueError):
            self.client.generate("custom_composition", prompt="")
        self.assertEqual(self.session.call_count, 0)


class TestHdImage(ImageClientTestCase):
    def test_returns_url_when_ready(self):
        self.session.enqueue_envelope({"hd_image_url": "https://cdn.example.com/hd.png"})
        self.assertEqual(self.client.get_hd_image(1), "https://cdn.example.com/hd.png")

    def test_returns_none_when_not_ready(self):
        """旧实现抛裸 KeyError。"""
        self.session.enqueue_envelope({"status": "processing"})
        self.assertIsNone(self.client.get_hd_image(1))

    def test_alternate_field_names_accepted(self):
        self.session.enqueue_envelope({"hd_url": "https://cdn.example.com/hd2.png"})
        self.assertEqual(self.client.get_hd_image(1), "https://cdn.example.com/hd2.png")

    def test_wait_for_hd_image_polls_until_ready(self):
        self.session.enqueue_envelope({"status": "processing"})   # upscale 未就绪
        self.session.enqueue_envelope({"status": "completed"})     # 任务状态正常
        self.session.enqueue_envelope({"hd_image_url": "https://cdn.example.com/hd.png"})
        result = self.client.wait_for_hd_image(1, poll_interval=0, timeout=5)
        self.assertEqual(result, "https://cdn.example.com/hd.png")

    def test_wait_for_hd_image_raises_when_task_failed(self):
        self.session.enqueue_envelope({"status": "processing"})
        self.session.enqueue_envelope({"status": "error", "error": "生成失败"})
        with self.assertRaises(TaskFailedError) as ctx:
            self.client.wait_for_hd_image(3, poll_interval=0, timeout=5)
        self.assertEqual(ctx.exception.task_id, 3)

    def test_wait_for_hd_image_times_out(self):
        for _ in range(10):
            self.session.enqueue_envelope({"status": "processing"})
            self.session.enqueue_envelope({"status": "completed"})
        with self.assertRaises(TaskTimeoutError):
            self.client.wait_for_hd_image(3, poll_interval=0.005, timeout=0.03)


class TestListTasks(ImageClientTestCase):
    def test_default_params(self):
        self.session.enqueue_envelope({"total": 0, "list": []})
        self.client.list_tasks()
        self.assertEqual(self.session.last_call["params"], {"page": 1, "page_size": 20})

    def test_status_all_is_omitted(self):
        self.session.enqueue_envelope({"total": 0})
        self.client.list_tasks(status="all")
        self.assertNotIn("status", self.session.last_call["params"])

    def test_status_filter_is_sent(self):
        self.session.enqueue_envelope({"total": 0})
        self.client.list_tasks(status="completed")
        self.assertEqual(self.session.last_call["params"]["status"], "completed")

    def test_task_type_filter_is_sent(self):
        self.session.enqueue_envelope({"total": 0})
        self.client.list_tasks(task_type="translation")
        self.assertEqual(self.session.last_call["params"]["type"], "translation")

    def test_unknown_task_type_filter_rejected(self):
        with self.assertRaises(ValueError):
            self.client.list_tasks(task_type="nope")

    def test_pagination_validated(self):
        for page, page_size in ((0, 20), (-1, 20), (1, 0), (1, 5000)):
            with self.subTest(page=page, page_size=page_size), self.assertRaises(ValueError):
                self.client.list_tasks(page=page, page_size=page_size)
        self.assertEqual(self.session.call_count, 0)


if __name__ == "__main__":
    unittest.main()
