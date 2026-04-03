"""
AI 图像/视频生成 Python SDK
- 基类: AIClient (通用请求、认证、图片上传)
- 图片客户端: ImageClient (9种作图、状态轮询、高清图、任务列表)
- 视频客户端: VideoClient (视频生成、状态轮询、任务列表)
"""

import os
import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient, APIError

class VideoClient(AIClient):
    """AI 视频生成客户端"""

    # ---------- 发起视频任务 ----------
    def create_video(self,
                     original_images: List[Union[str, Path]],
                     prompt: str) -> int:
        """
        发起视频生成任务（最多5张图）

        Args:
            original_images: 原始图片列表（本地路径/URL/Base64）
            prompt: 视频画面描述

        Returns:
            task_id
        """
        prepared_images = self._prepare_images(original_images)
        payload = {
            "original_image": prepared_images,
            "prompt": prompt
        }
        data = self._request('POST', '/v1/video/generations', json=payload)
        return int(data['task_id'])

    # ---------- 查询视频结果 ----------
    def get_video_status(self, task_id: int) -> Dict[str, Any]:
        """查询单个视频任务状态"""
        endpoint = f"/v1/video/generations/tasks/{task_id}"
        return self._request('GET', endpoint)

    def wait_for_video_completion(self, task_id: int, poll_interval: int = 15, timeout: int = 600) -> Dict[str, Any]:
        """轮询等待视频任务完成（建议间隔15-20秒）"""
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise APIError(-1, f"视频任务 {task_id} 轮询超时", 0)

            data = self.get_video_status(task_id)
            status = data.get('status')
            if status == 'completed':
                return data
            if status == 'error':
                raise APIError(-1, f"视频任务 {task_id} 执行失败", 0)
            time.sleep(poll_interval)

    # ---------- 获取视频任务列表 ----------
    def list_video_tasks(self,
                         page: int = 1,
                         page_size: int = 20,
                         status: Optional[str] = None) -> Dict[str, Any]:
        """获取视频任务列表，支持分页和状态过滤"""
        params = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        return self._request('GET', '/v1/video/tasks-list', params=params)
