"""IXSPY AI 对话生成客户端。

与图片/视频不同，对话生成是**同步返回**接口：``generate()`` 直接返回生成结果，
不存在 ``task_id`` 与轮询流程。

- 创建对话生成：``POST /v1/chat/generations``
- 查询对话记录：``GET /v1/chat/tasks-list``
"""

from typing import Any, Dict, Optional

from .ai_client import AIClient, ImageInputs
from .types import ChatGenerationResult, TaskListPage
from .validation import SUPPORTED_MODELS, validate_model, validate_model_tier, validate_pagination, validate_prompt


class ChatClient(AIClient):
    """IXSPY AI 对话生成 API 客户端。"""

    #: 支持的模型取值，与图片客户端保持一致。
    SUPPORTED_MODELS = SUPPORTED_MODELS

    def generate(self,
                 prompt: str,
                 original_image: Optional[ImageInputs] = None,
                 model: Optional[str] = None,
                 model_tier: Optional[str] = None) -> ChatGenerationResult:
        """创建对话生成任务（同步返回结果）。

        参数:
            prompt: 对话提示词，必填且不能为空。
            original_image: 可选图片输入（单张或列表），元素可为本地路径、URL 或
                Base64 字符串。
            model: 模型，可选 ``auto``、``gemini``、``chatgpt``。
                ``None``（默认）表示不下发该字段，由服务端选择默认模型。图片与
                对话客户端在这一点上行为一致。
            model_tier: 模型规格，可选 ``Flash``、``Pro``，仅在 ``model='gemini'``
                时生效；``None``（默认）表示使用服务端默认值。

        返回:
            生成结果数据。常见字段见 :class:`~ixspy_ai_api.types.ChatGenerationResult`。

        抛出:
            ValueError: 提示词为空，或 model/model_tier 取值非法。
            APIError: API 调用失败。
        """
        prompt = validate_prompt(prompt)
        model = validate_model(model)
        model_tier = validate_model_tier(model_tier)

        payload: Dict[str, Any] = {"prompt": prompt}
        if model is not None:
            payload["model"] = model
        if model_tier is not None:
            if model != "gemini":
                # 显式提示而非静默丢弃，避免用户以为参数已生效。
                raise ValueError(
                    "model_tier 仅在 model='gemini' 时生效，"
                    f"当前 model={model!r}。请显式传入 model='gemini' 或移除 model_tier。"
                )
            payload["model_tier"] = model_tier

        if original_image is not None:
            payload["original_image"] = self._prepare_images(original_image)

        return self._request_as(ChatGenerationResult, "POST", "/v1/chat/generations", json=payload)

    def list_chat_tasks(self,
                        page: int = 1,
                        page_size: int = 20,
                        status: Optional[str] = None) -> TaskListPage:
        """查询对话记录列表。

        参数:
            page: 页码，从 1 开始。
            page_size: 每页数量，最大 100。
            status: 状态过滤；``None`` 或 ``"all"`` 表示不按状态过滤
                （与图片/视频列表接口保持一致的行为）。

        返回:
            含 ``total`` 与记录列表的分页数据。
        """
        validate_pagination(page, page_size)
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        return self._request_as(TaskListPage, "GET", "/v1/chat/tasks-list", params=params)


__all__ = ["ChatClient"]
