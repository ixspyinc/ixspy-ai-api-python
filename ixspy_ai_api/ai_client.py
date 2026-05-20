"""
IXSPY AI API 基础客户端。

- AIClient：封装通用 HTTP 请求、认证和图片上传能力。
- APIError：统一的 API 异常类型。
"""

import base64
import binascii
import os
import time as time_module
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

import requests


class APIError(Exception):
    """当 API 响应中的错误码不为 0 时抛出的异常。"""

    def __init__(self, code: int, message: str, time: Optional[int] = None):
        self.code = code
        self.message = message
        self.time = int(time if time is not None else time_module.time())
        super().__init__(f"API Error {code}: {message}")


class AIClient:
    """IXSPY AI 服务基础客户端。"""

    BASE_URL = "https://ixspy.com/ai-tool/api"

    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: Optional[Union[int, float]] = 90):
        """
        初始化基础客户端。

        参数:
            api_key: IXSPY 控制台获取的 API 密钥。
            base_url: 可选的自定义 API 基础地址。
            timeout: HTTP 请求超时时间，单位为秒，默认 90 秒。传入 None 表示不设置超时。
        """
        self.api_key = api_key
        self.base_url = (base_url or self.BASE_URL).rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}"
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        发送 HTTP 请求，并解析统一的 API 响应格式。

        返回:
            响应中的 `data` 字段。

        抛出:
            APIError: 当 `error.code` 不为 0 或响应不是合法 JSON 时抛出。
        """
        url = f"{self.base_url}{endpoint}"
        # 文件上传时由 requests 自动设置 multipart 边界。
        if 'files' in kwargs:
            pass
        elif 'json' in kwargs:
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        elif 'data' in kwargs and not kwargs.get('files'):
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/x-www-form-urlencoded'

        if self.timeout is not None:
            kwargs.setdefault('timeout', self.timeout)

        response = self.session.request(method, url, **kwargs)
        try:
            resp_json = response.json()
        except ValueError:
            raise APIError(-1, f"响应不是合法 JSON: {response.text[:200]}", 0)

        error = resp_json.get('error', {})
        code = error.get('code', -1)
        if code != 0:
            raise APIError(
                code=code,
                message=error.get('message', '未知错误'),
                time=error.get('time', 0)
            )
        return resp_json.get('data', {})

    def upload_image_file(self, file_path: Union[str, Path]) -> str:
        """
        上传本地图片文件。

        参数:
            file_path: 本地图片路径。

        返回:
            CDN 图片 URL。
        """
        file_path = str(file_path)
        with open(file_path, 'rb') as f:
            files = {'image': (os.path.basename(file_path), f)}
            data = self._request('POST', '/v1/images/upload', files=files)
        return data['url']

    def upload_image_base64(self, base64_str: str) -> str:
        """
        上传 Base64 编码图片。

        参数:
            base64_str: Base64 字符串，可包含 `data:image/...` 前缀。

        返回:
            CDN 图片 URL。
        """
        payload = {"image_base64": base64_str}
        data = self._request('POST', '/v1/images/upload', json=payload)
        return data['url']

    @staticmethod
    def _is_base64_image_input(input_str: str) -> bool:
        value = input_str.strip()
        is_data_image = value.lower().startswith('data:image')
        if is_data_image:
            if ',' not in value:
                return False
            header, value = value.split(',', 1)
            if ';base64' not in header.lower():
                return False
        value = ''.join(value.split())
        if not value:
            return False
        if not is_data_image and len(value) <= 100:
            return False
        if len(value) % 4 == 1:
            return False

        try:
            padded_value = value + ('=' * (-len(value) % 4))
            base64.b64decode(padded_value, validate=True)
        except (binascii.Error, ValueError):
            return False
        return True

    def _prepare_single_image(self, image_input: Union[str, Path]) -> str:
        """
        将单个图片输入标准化为 CDN URL。

        本地文件和 Base64 字符串会自动上传；已有 URL 会原样返回。
        """
        input_str = str(image_input)
        if input_str.startswith(('http://', 'https://')):
            return input_str

        if os.path.exists(input_str):
            return self.upload_image_file(input_str)
        if self._is_base64_image_input(input_str):
            return self.upload_image_base64(input_str)
        # 未知格式交给服务端校验。
        return input_str

    def _prepare_images(self, images: Union[str, Path, List[Union[str, Path]]]) -> Union[str, List[str]]:
        """
        标准化单张图片或图片列表。

        返回:
            CDN URL 字符串，或 CDN URL 字符串列表。
        """
        if isinstance(images, (str, Path)):
            return self._prepare_single_image(images)
        if isinstance(images, list):
            return [self._prepare_single_image(img) for img in images]
        raise ValueError("images 必须是字符串、Path 对象或列表")
