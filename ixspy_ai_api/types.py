"""公共类型定义。

本模块提供两类内容：

- ``*Result`` 之类的 :class:`typing.TypedDict`：描述接口返回结构，使用户在
  保持 ``dict`` 使用方式（``result["sd_image_url"]``）的同时获得 IDE 补全与
  静态检查能力。
- 任务状态常量与状态集合：避免在多个客户端模块里硬编码字符串。
"""

from typing import Any, Dict, List, TypedDict

# --------------------------------------------------------------------------- #
# 任务状态
# --------------------------------------------------------------------------- #

#: 任务已提交，等待执行。
TASK_STATUS_QUEUED = "queued"

#: 任务执行中。
TASK_STATUS_PROCESSING = "processing"

#: 任务成功完成，结果 URL 可用。
TASK_STATUS_COMPLETED = "completed"

#: 任务执行失败。
TASK_STATUS_ERROR = "error"

#: 表示“尚未结束，需要继续轮询”的状态集合。
PENDING_TASK_STATUSES = frozenset({TASK_STATUS_QUEUED, TASK_STATUS_PROCESSING})

#: 表示“任务已结束”的状态集合。
TERMINAL_TASK_STATUSES = frozenset({TASK_STATUS_COMPLETED, TASK_STATUS_ERROR})

#: 任务状态在中文文档中的说明，供 README/错误信息复用。
TASK_STATUS_DESCRIPTIONS = {
    TASK_STATUS_QUEUED: "已提交，等待执行",
    TASK_STATUS_PROCESSING: "执行中",
    TASK_STATUS_COMPLETED: "已完成，结果可用",
    TASK_STATUS_ERROR: "执行失败",
}


# --------------------------------------------------------------------------- #
# 响应结构
# --------------------------------------------------------------------------- #

class TaskResult(TypedDict, total=False):
    """轮询接口返回的任务数据。

    字段随任务类型不同而变化，因此全部为可选；``status`` 是唯一在服务端
    必定返回的字段。
    """

    status: str
    task_id: int
    error: str
    create_time: int
    finish_time: int


class ImageTaskResult(TaskResult, total=False):
    """图片任务的轮询结果，在 :class:`TaskResult` 基础上补充图片 URL 字段。"""

    sd_image_url: str
    hd_image_url: str
    thumbnail_url: str


class VideoTaskResult(TaskResult, total=False):
    """视频任务的轮询结果。"""

    video_url: str
    cover_url: str
    duration: int


class TaskListPage(TypedDict, total=False):
    """任务列表分页结果。"""

    total: int
    page: int
    page_size: int
    list: List[Dict[str, Any]]


class ChatGenerationResult(TypedDict, total=False):
    """对话生成接口的返回数据。

    具体字段由服务端决定（可能直接返回回答内容，也可能返回任务 ID），
    因此不做过度约束。
    """

    task_id: int
    status: str
    content: str
    answer: str
    model: str


class ImageInput(TypedDict, total=False):
    """已归一化的图片输入占位类型（实际传输时是 URL 字符串）。"""

    url: str


#: 图片输入的宽松类型别名：本地路径、URL 或 Base64 字符串。
ImageRef = Any

#: 视频参考图字段：单张或最多三张。
ImageRefList = List[ImageRef]

__all__ = [
    "TASK_STATUS_QUEUED",
    "TASK_STATUS_PROCESSING",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_ERROR",
    "PENDING_TASK_STATUSES",
    "TERMINAL_TASK_STATUSES",
    "TASK_STATUS_DESCRIPTIONS",
    "TaskResult",
    "ImageTaskResult",
    "VideoTaskResult",
    "TaskListPage",
    "ChatGenerationResult",
    "ImageInput",
    "ImageRef",
    "ImageRefList",
]
