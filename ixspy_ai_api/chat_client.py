"""
IXSPY AI 对话生成客户端。

- 创建对话生成任务：POST /ai-tool/api/v1/chat/generations
- 查询对话任务列表：GET /ai-tool/api/v1/chat/tasks-list
"""

from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient


class ChatClient(AIClient):
    """IXSPY AI 对话生成 API 客户端。"""

    def generate(
        self,
        prompt: str,
        original_image: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
    ) -> Dict[str, Any]:
        """
        创建对话生成任务。

        参数:
            prompt: 对话提示词。
            original_image: 可选原图列表，元素可以是本地路径、URL 或 Base64 字符串。

        返回:
            响应数据，通常包含任务或生成内容相关字段。
        """
        endpoint = "/v1/chat/generations"
        payload: Dict[str, Any] = {"prompt": prompt}

        if original_image is not None:
            payload["original_image"] = self._prepare_images(original_image)

        return self._request("POST", endpoint, json=payload)

    def list_chat_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> Dict[str, Any]:
        """
        查询对话任务列表。

        参数:
            page: 页码，默认 1。
            page_size: 每页数量，默认 20。
            status: 状态过滤，支持 "all"、"queued"、"processing"、
                "completed" 和 "error"。

        返回:
            包含任务总数和任务列表的响应数据。
        """
        endpoint = "/v1/chat/tasks-list"
        params = {
            "page": page,
            "page_size": page_size,
            "status": status,
        }
        return self._request("GET", endpoint, params=params)
