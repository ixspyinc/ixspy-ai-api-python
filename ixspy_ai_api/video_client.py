"""IXSPY AI 视频生成客户端。

``VideoClient`` 提供视频任务创建、任务轮询和任务列表查询能力。

视频任务耗时长（通常 1-3 分钟）、成本高，因此本模块刻意做到：

- 提交前在本地完成全部参数校验（图片数量、首尾帧依赖、比例、提示词），
  避免提交后才发现参数错误；
- 轮询超时抛 :class:`~ixspy_ai_api.ai_client.TaskTimeoutError`，与「任务确实
  失败」的 :class:`~ixspy_ai_api.ai_client.TaskFailedError` 区分开，用户可按需
  凭 ``task_id`` 继续查询。
"""

from typing import Any, Dict, List, Optional, Union

from .ai_client import (
    AIClient,
    ImageInput,
    TaskFailedError,
    wait_for_task,
)
from .types import TASK_STATUS_ERROR, TaskListPage, VideoTaskResult
from .validation import (
    SUPPORTED_VIDEO_RATIOS,
    validate_pagination,
    validate_prompt,
    validate_ratio,
    validate_required_image,
)

#: 参考图 + 首尾帧的图片总数上限。
MAX_VIDEO_IMAGES = 3

#: 轮询视频任务的默认间隔（秒）。
DEFAULT_VIDEO_POLL_INTERVAL = 15

#: 轮询视频任务的默认总等待上限（秒）。
DEFAULT_VIDEO_WAIT_TIMEOUT: Optional[Union[int, float]] = 600


class VideoClient(AIClient):
    """IXSPY AI 视频生成 API 客户端。"""

    #: 支持的画面比例。
    SUPPORTED_RATIOS = SUPPORTED_VIDEO_RATIOS

    def _validate_images(self, reference_images: List[Any],
                         first_frame: Optional[ImageInput],
                         last_frame: Optional[ImageInput]) -> None:
        """校验图片组合，一次性给出全部错误。"""
        problems: List[str] = []

        if len(reference_images) > MAX_VIDEO_IMAGES:
            problems.append(
                f"reference_image 最多支持 {MAX_VIDEO_IMAGES} 张，当前 {len(reference_images)} 张"
            )

        if last_frame is not None and first_frame is None:
            problems.append("传入 last_frame（尾帧图）时必须同时传入 first_frame（首帧图）")

        total = len(reference_images) + (1 if first_frame is not None else 0) + (1 if last_frame is not None else 0)
        if total > MAX_VIDEO_IMAGES:
            problems.append(
                f"图片总数（reference_image + first_frame + last_frame）不能超过 "
                f"{MAX_VIDEO_IMAGES} 张，当前 {total} 张"
            )

        if problems:
            raise ValueError("；".join(problems))

    def create_video(self,
                     prompt: str,
                     reference_image: Optional[Union[List[ImageInput], ImageInput]] = None,
                     first_frame: Optional[ImageInput] = None,
                     last_frame: Optional[ImageInput] = None,
                     ratios: Optional[str] = None) -> int:
        """创建视频生成任务。

        参数:
            prompt: 视频画面描述，必填且不能为空。建议详细描述角色、物品的互动、
                风格、材质及场景背景。
            reference_image: 参考图，单张或列表，最多 3 张。支持本地路径、URL 或
                Base64 字符串；建议优先使用「图片上传」接口返回的 URL。
            first_frame: 首帧图，仅支持 1 张。
            last_frame: 尾帧图，仅支持 1 张；传入时必须同时传入 ``first_frame``。
            ratios: 视频比例，可选 ``'16:9'``、``'9:16'``；``None`` 使用服务端默认值。

        返回:
            任务 ID。

        抛出:
            ValueError: 参数非法（空提示词、图片数量超限、首尾帧依赖缺失、比例不支持）。
            FileNotFoundError: 传入的本地图片路径不存在。
            APIError: API 调用失败。
        """
        prompt = validate_prompt(prompt)
        validate_ratio(ratios)

        reference_images: List[ImageInput] = []
        if reference_image is not None:
            if isinstance(reference_image, (list, tuple)):
                reference_images = list(reference_image)
            else:
                reference_images = [reference_image]
            validate_required_image(reference_images, "reference_image")

        self._validate_images(reference_images, first_frame, last_frame)

        payload: Dict[str, Any] = {"prompt": prompt}
        if reference_images:
            payload["reference_image"] = self._prepare_image_list(reference_images)
        if first_frame is not None:
            payload["first_frame"] = self._prepare_single_image(first_frame)
        if last_frame is not None:
            payload["last_frame"] = self._prepare_single_image(last_frame)
        if ratios:
            payload["ratios"] = ratios

        data = self._request('POST', '/v1/video/generations', json=payload)
        return self._require_int(data, 'task_id', '创建视频任务')

    def get_video_status(self, task_id: int) -> VideoTaskResult:
        """查询单个视频任务的状态和结果数据。"""
        return self._request_as(VideoTaskResult, 'GET', f"/v1/video/generations/tasks/{task_id}")

    def wait_for_video_completion(self,
                                  task_id: int,
                                  poll_interval: float = DEFAULT_VIDEO_POLL_INTERVAL,
                                  timeout: Optional[Union[int, float]] = DEFAULT_VIDEO_WAIT_TIMEOUT
                                  ) -> VideoTaskResult:
        """轮询视频任务，直到完成、失败或超时。

        参数:
            task_id: 视频任务 ID。
            poll_interval: 两次查询之间的间隔（秒），默认 15。
            timeout: **总等待上限**（秒），默认 600。``None`` 或 ``0`` 表示不限制。
                注意这是轮询总耗时上限，与单次请求超时无关；单次请求超时由
                ``AIClient(timeout=...)`` 控制。

        返回:
            已完成任务的数据，通常包含 ``video_url``。

        抛出:
            TaskFailedError: 任务状态为 ``error``（任务确实失败）。
            TaskTimeoutError: 超过 ``timeout`` 仍未完成（任务可能仍在服务端运行，
                可凭 ``task_id`` 继续查询）。
            APIError: 返回了未知状态或请求失败。
        """
        return wait_for_task(
            lambda: self.get_video_status(task_id),
            task_id,
            poll_interval=poll_interval,
            timeout=timeout,
            task_label="视频任务",
        )

    def get_video_url(self, task_id: int) -> str:
        """获取已完成视频任务的视频 URL。

        抛出:
            APIResponseError: 响应中缺少 ``video_url``（任务可能尚未完成）。
            TaskFailedError: 任务状态为 ``error``。
        """
        data = self.get_video_status(task_id)
        if data.get('status') == TASK_STATUS_ERROR:
            raise TaskFailedError(
                message=f"视频任务 {task_id} 执行失败: {data.get('error') or '服务端未返回失败原因'}",
                task_id=task_id,
            )
        return self._require_field(data, 'video_url', f'视频任务 {task_id}')

    def list_video_tasks(self,
                         page: int = 1,
                         page_size: int = 20,
                         status: Optional[str] = None) -> TaskListPage:
        """查询视频任务列表。

        参数:
            page: 页码，从 1 开始。
            page_size: 每页数量，最大 100。
            status: 状态过滤；``None`` 或 ``"all"`` 表示不按状态过滤。

        返回:
            含 ``total`` 与任务列表的分页数据。
        """
        validate_pagination(page, page_size)
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        return self._request_as(TaskListPage, 'GET', '/v1/video/tasks-list', params=params)


__all__ = ["VideoClient", "MAX_VIDEO_IMAGES", "DEFAULT_VIDEO_POLL_INTERVAL", "DEFAULT_VIDEO_WAIT_TIMEOUT"]
