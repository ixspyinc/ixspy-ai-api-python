"""
IXSPY AI 视频生成客户端。

VideoClient 提供视频任务创建、任务轮询和任务列表查询能力。
"""

import os
import sys
import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient, APIError


class VideoClient(AIClient):
    """IXSPY AI 视频生成 API 客户端。"""

    def create_video(self,
                     prompt: str,
                     reference_image: Optional[Union[List[Union[str, Path]], str, Path]] = None,
                     first_frame: Optional[Union[str, Path]] = None,
                     last_frame: Optional[Union[str, Path]] = None,
                     ratios: Optional[str] = None) -> int:
        """
        创建视频生成任务。

        参数:
            prompt: 视频画面描述。需详细描述图片中角色、物品的互动、风格、材质及场景背景。
            reference_image: 参考图数组，最多支持 3 张图。支持本地路径、URL 或 Base64 字符串。建议优先使用通过「图片上传」接口获取的 URL。
            first_frame: 首帧图，仅支持 1 张。支持本地路径、URL 或 Base64 字符串。
            last_frame: 尾帧图，仅支持 1 张。如传入该字段，则必须同时传入 first_frame。
            ratios: 视频比例。可选值：'16:9'、'9:16'。

        返回:
            任务 ID。
        """
        total_images = 0
        ref_images_list = []
        
        if reference_image:
            if isinstance(reference_image, (list, tuple)):
                ref_images_list = list(reference_image)
            else:
                ref_images_list = [reference_image]
            total_images += len(ref_images_list)
            
        if first_frame:
            total_images += 1
            
        if last_frame:
            if not first_frame:
                raise ValueError("如果传入 last_frame (尾帧图)，则必须同时传入 first_frame (首帧图)。")
            total_images += 1
            
        if total_images > 3:
            raise ValueError(f"图片总数(reference_image, first_frame, last_frame)不能超过 3 张，当前传入 {total_images} 张。")
            
        if ratios and ratios not in ('16:9', '9:16'):
            raise ValueError("ratios 参数仅支持 '16:9' 或 '9:16'。")

        payload = {
            "prompt": prompt
        }
        
        if ref_images_list:
            payload["reference_image"] = self._prepare_images(ref_images_list)
        if first_frame:
            prepared_first = self._prepare_images(first_frame)
            payload["first_frame"] = prepared_first[0] if isinstance(prepared_first, list) else prepared_first
        if last_frame:
            prepared_last = self._prepare_images(last_frame)
            payload["last_frame"] = prepared_last[0] if isinstance(prepared_last, list) else prepared_last
        if ratios:
            payload["ratios"] = ratios

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
