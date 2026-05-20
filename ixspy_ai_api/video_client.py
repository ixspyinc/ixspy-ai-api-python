"""
IXSPY AI 视频生成客户端。

VideoClient 提供视频任务创建、任务轮询和任务列表查询能力。
"""

import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient, APIError


class VideoClient(AIClient):
    """IXSPY AI 视频生成 API 客户端。"""

    def create_video(self,
                     original_images: List[Union[str, Path]],
                     prompt: str) -> int:
        """
        创建视频生成任务。

        参数:
            original_images: 原图列表，元素可以是本地路径、URL 或 Base64 字符串。
            prompt: 视频画面描述。

        返回:
            任务 ID。
        """
        prepared_images = self._prepare_images(original_images)
        payload = {
            "original_image": prepared_images,
            "prompt": prompt
        }
        data = self._request('POST', '/v1/video/generations', json=payload)
        return int(data['task_id'])

    def get_video_status(self, task_id: int) -> Dict[str, Any]:
        """查询单个视频任务的状态和结果数据。"""
        endpoint = f"/v1/video/generations/tasks/{task_id}"
        return self._request('GET', endpoint)

    def wait_for_video_completion(self, task_id: int, poll_interval: int = 15, timeout: Optional[int] = 600) -> Dict[str, Any]:
        """
        轮询视频任务，直到任务完成、失败或超时。

        参数:
            task_id: 视频任务 ID。
            poll_interval: 每次查询状态之间的间隔，单位为秒。默认 15 秒。
            timeout: 最大等待时间，单位为秒。传入 0 或 None 表示不限制。

        返回:
            已完成任务的数据。
        """
        start_time = time.time()
        while True:
            if timeout and (time.time() - start_time > timeout):
                raise APIError(-1, f"视频任务 {task_id} 轮询超时", 0)

            data = self.get_video_status(task_id)
            status = data.get('status')
            if status == 'completed':
                return data
            if status == 'error':
                raise APIError(-1, f"视频任务 {task_id} 执行失败", 0)
            if status in ('queued', 'processing'):
                time.sleep(poll_interval)
            else:
                raise APIError(-1, f"未知视频任务状态: {status}", 0)

    def list_video_tasks(self,
                         page: int = 1,
                         page_size: int = 20,
                         status: Optional[str] = None) -> Dict[str, Any]:
        """查询视频任务列表，支持分页和状态过滤。"""
        params = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        return self._request('GET', '/v1/video/tasks-list', params=params)
