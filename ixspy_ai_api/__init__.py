"""IXSPY AI API 官方 Python SDK。

模块结构：

- :mod:`ixspy_ai_api.ai_client`：基础客户端、异常层级、通用轮询。
- :mod:`ixspy_ai_api.image_client`：图片生成任务。
- :mod:`ixspy_ai_api.video_client`：视频生成任务。
- :mod:`ixspy_ai_api.chat_client`：对话生成（同步返回）。
- :mod:`ixspy_ai_api.validation`：共享参数校验。
- :mod:`ixspy_ai_api.types`：任务状态常量与响应结构类型。

快速上手::

    from ixspy_ai_api import ImageClient

    with ImageClient(api_key="YOUR_KEY") as client:
        result = client.generate(
            client.TYPE_CUSTOM_COMPOSITION,
            original_image="images/speaker.jpg",
            prompt="移除产品背景，只保留白色背景产品图",
        )
        print(result["sd_image_url"])
"""

from .ai_client import (
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_UPLOAD_TIMEOUT,
    DEFAULT_WAIT_TIMEOUT,
    LOCAL_ERROR_CODES,
    AIClient,
    APIConnectionError,
    APIError,
    APIResponseError,
    AuthError,
    RateLimitError,
    ServerError,
    TaskFailedError,
    TaskTimeoutError,
    wait_for_task,
)
from .chat_client import ChatClient
from .image_client import MODEL_SELECTABLE_TYPES, TASK_SPECS, ImageClient, TaskSpec
from .types import (
    PENDING_TASK_STATUSES,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_ERROR,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_QUEUED,
    TERMINAL_TASK_STATUSES,
    ChatGenerationResult,
    ImageTaskResult,
    TaskListPage,
    TaskResult,
    VideoTaskResult,
)
from .validation import SUPPORTED_MODEL_TIERS, SUPPORTED_MODELS, SUPPORTED_VIDEO_RATIOS
from .version import __version__
from .video_client import VideoClient

__all__ = [
    # 客户端
    "AIClient",
    "ImageClient",
    "VideoClient",
    "ChatClient",
    # 异常
    "APIError",
    "APIResponseError",
    "APIConnectionError",
    "AuthError",
    "RateLimitError",
    "ServerError",
    "TaskFailedError",
    "TaskTimeoutError",
    "LOCAL_ERROR_CODES",
    # 常量
    "DEFAULT_REQUEST_TIMEOUT",
    "DEFAULT_UPLOAD_TIMEOUT",
    "DEFAULT_WAIT_TIMEOUT",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "SUPPORTED_MODELS",
    "SUPPORTED_MODEL_TIERS",
    "SUPPORTED_VIDEO_RATIOS",
    "TASK_STATUS_QUEUED",
    "TASK_STATUS_PROCESSING",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_ERROR",
    "PENDING_TASK_STATUSES",
    "TERMINAL_TASK_STATUSES",
    "TASK_SPECS",
    "MODEL_SELECTABLE_TYPES",
    "TaskSpec",
    # 类型
    "TaskResult",
    "ImageTaskResult",
    "VideoTaskResult",
    "TaskListPage",
    "ChatGenerationResult",
    # 工具
    "wait_for_task",
    "__version__",
]
