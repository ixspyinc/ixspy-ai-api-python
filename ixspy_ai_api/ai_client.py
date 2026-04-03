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

import requests


class APIError(Exception):
    """API 调用异常"""
    def __init__(self, code: int, message: str, time: int):
        self.code = code
        self.message = message
        self.time = time
        super().__init__(f"API Error {code}: {message}")


class AIClient:
    """AI 服务基础客户端，封装通用 HTTP 请求和图片上传"""

    BASE_URL = "https://ixspy.com/ai-tool/api"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """
        初始化基础客户端

        Args:
            api_key: API 密钥，从控制台获取
            base_url: 可选的自定义基础地址
        """
        self.api_key = api_key
        self.base_url = (base_url or self.BASE_URL).rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}"
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        发送 HTTP 请求并解析统一响应格式

        Returns:
            响应中的 data 字段

        Raises:
            APIError: 当 error.code != 0 时抛出
        """
        url = f"{self.base_url}{endpoint}"
        # 根据请求类型自动设置 Content-Type
        if 'files' in kwargs:
            # multipart/form-data，让 requests 自动处理
            pass
        elif 'json' in kwargs:
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        elif 'data' in kwargs and not kwargs.get('files'):
            # application/x-www-form-urlencoded
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/x-www-form-urlencoded'

        response = self.session.request(method, url, **kwargs)
        try:
            resp_json = response.json()
        except ValueError:
            raise APIError(-1, f"Invalid JSON response: {response.text[:200]}", 0)

        error = resp_json.get('error', {})
        code = error.get('code', -1)
        if code != 0:
            raise APIError(
                code=code,
                message=error.get('message', 'Unknown error'),
                time=error.get('time', 0)
            )
        return resp_json.get('data', {})

    # ---------- 图片上传（公用） ----------
    def upload_image_file(self, file_path: Union[str, Path]) -> str:
        """
        上传本地图片文件（文件模式）

        Args:
            file_path: 本地图片路径

        Returns:
            CDN 图片 URL
        """
        file_path = str(file_path)
        with open(file_path, 'rb') as f:
            files = {'image': (os.path.basename(file_path), f)}
            data = self._request('POST', '/v1/images/upload', files=files)
        return data['url']

    def upload_image_base64(self, base64_str: str) -> str:
        """
        上传 Base64 编码的图片（Base64 模式）

        Args:
            base64_str: Base64 字符串，可带 data:image/... 前缀

        Returns:
            CDN 图片 URL
        """
        payload = {"image_base64": base64_str}
        data = self._request('POST', '/v1/images/upload', json=payload)
        return data['url']

    def _prepare_single_image(self, image_input: Union[str, Path]) -> str:
        """
        将单个图片输入标准化为 CDN URL（自动上传本地文件或 Base64）

        Args:
            image_input: 本地路径、Base64 字符串或已有 URL

        Returns:
            CDN URL
        """
        input_str = str(image_input)
        # 已经是 URL
        if input_str.startswith(('http://', 'https://')):
            return input_str
        # 可能是 Base64
        if input_str.startswith('data:image') or (len(input_str) > 100 and '/' not in input_str[:50]):
            return self.upload_image_base64(input_str)
        # 本地文件路径
        if os.path.exists(input_str):
            return self.upload_image_file(input_str)
        # 未知格式，直接返回原值（让服务端判断）
        return input_str

    def _prepare_images(self, images: Union[str, Path, List[Union[str, Path]]]) -> Union[str, List[str]]:
        """
        批量标准化图片输入

        Args:
            images: 单个图片或图片列表

        Returns:
            单个 URL 字符串或 URL 列表
        """
        if isinstance(images, (str, Path)):
            return self._prepare_single_image(images)
        if isinstance(images, list):
            return [self._prepare_single_image(img) for img in images]
        raise ValueError("images 必须是字符串、Path对象或列表")
