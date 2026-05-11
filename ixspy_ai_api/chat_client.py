"""
AI 对话生成 Python SDK - 对话客户端
- 发起对话生成任务：POST /ai-tool/api/v1/chat/generations
- 获取对话任务列表：GET /ai-tool/api/v1/chat/tasks-list
"""
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient


class ChatClient(AIClient):
    """AI 对话生成客户端"""

    # ---------- 发起对话生成任务 ----------
    def generate(
        self,
        prompt: str,
        original_image: Optional[List[Union[str, Path]]] = None,
    ) -> Dict[str, Any]:
        """
        发起对话生成任务

        :param prompt: 对话提示内容（必填）
        :param original_image: 原图列表，最多5张，支持文件路径、URL或Base64（可选）
        :return: 响应数据字典，包含 status 和 data（含 task_id、html 等）
        """
        endpoint = "/v1/chat/generations"
        payload: Dict[str, Any] = {"prompt": prompt}

        if original_image is not None:
            payload["original_image"] = self._prepare_images(original_image)

        return self._request("POST", endpoint, json=payload)

    # ---------- 获取对话任务列表 ----------
    def list_chat_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> Dict[str, Any]:
        """
        获取对话任务列表

        :param page: 页码，默认 1
        :param page_size: 每页数量，默认 20
        :param status: 状态过滤，可选值：all, queued, processing, completed, error
        :return: 响应数据字典，包含 total 和 list
        """
        endpoint = "/v1/chat/tasks-list"
        params = {
            "page": page,
            "page_size": page_size,
            "status": status,
        }
        return self._request("GET", endpoint, params=params)