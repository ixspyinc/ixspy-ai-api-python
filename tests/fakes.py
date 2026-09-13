"""测试用假 HTTP 传输层。

SDK 的 :class:`~ixspy_ai_api.ai_client.AIClient` 只通过 ``self.session.request``
访问网络，因此测试只需替换 ``session``，无需引入 ``responses`` /
``requests_mock`` 等额外依赖，也就没有 mock 库与 ``requests`` 版本耦合的风险。

用法::

    session = FakeSession()
    session.enqueue_json({"error": {"code": 0}, "data": {"task_id": 7}})
    client = ImageClient(api_key="k")
    client.session = session
"""

import json
from typing import Any, Dict, List, Optional


class FakeResponse:
    """最小化的 ``requests.Response`` 替身。"""

    def __init__(self,
                 status_code: int = 200,
                 payload: Optional[Any] = None,
                 text: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._payload = payload
        self._invalid_json = payload is None and text is not None
        if text is not None:
            self.text = text
        elif payload is not None:
            self.text = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
        else:
            self.text = ""
        self.headers = headers or {}
        self.url = "https://example.invalid/"
        self.reason = "OK" if status_code < 400 else "Error"

    def json(self) -> Any:
        if self._invalid_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class FakeSession:
    """按顺序返回预置响应的假会话，并记录每次调用。

    同时实现 ``mount``/``close``，以便被替换进 ``AIClient`` 后仍能兼容
    ``HTTPAdapter`` 挂载与 ``close()`` 调用。
    """

    def __init__(self, responses: Optional[List[FakeResponse]] = None):
        self.responses: List[FakeResponse] = list(responses or [])
        self.calls: List[Dict[str, Any]] = []
        self.headers: Dict[str, str] = {}
        self.mounted: Dict[str, Any] = {}
        self.closed = False

    # -- 预置 ------------------------------------------------------------- #

    def enqueue(self, response: FakeResponse) -> "FakeSession":
        self.responses.append(response)
        return self

    def enqueue_json(self,
                     payload: Any,
                     status_code: int = 200,
                     headers: Optional[Dict[str, str]] = None) -> "FakeSession":
        """预置一个合法 JSON 响应。"""
        return self.enqueue(FakeResponse(status_code=status_code, payload=payload, headers=headers))

    def enqueue_envelope(self, data: Any, status_code: int = 200) -> "FakeSession":
        """预置标准成功信封 ``{"error": {"code": 0}, "data": ...}``。"""
        return self.enqueue_json({"error": {"code": 0}, "data": data}, status_code=status_code)

    def enqueue_error(self, code: int, message: str = "boom", status_code: int = 200) -> "FakeSession":
        """预置业务错误信封。"""
        return self.enqueue_json(
            {"error": {"code": code, "message": message, "time": 1700000000}},
            status_code=status_code,
        )

    def enqueue_text(self, text: str, status_code: int = 200,
                     headers: Optional[Dict[str, str]] = None) -> "FakeSession":
        """预置非 JSON 响应体。"""
        return self.enqueue(FakeResponse(status_code=status_code, text=text, headers=headers))

    # -- requests.Session 兼容接口 ---------------------------------------- #

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(
                f"FakeSession 没有更多预置响应，但收到了 {method} {url} 调用；"
                f"已发生的调用数: {len(self.calls)}"
            )
        return self.responses.pop(0)

    def mount(self, prefix: str, adapter: Any) -> None:
        self.mounted[prefix] = adapter

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # -- 断言辅助 --------------------------------------------------------- #

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_call(self) -> Dict[str, Any]:
        if not self.calls:
            raise AssertionError("FakeSession 尚未收到任何调用")
        return self.calls[-1]

    def json_bodies(self) -> List[Any]:
        """返回所有请求中 ``json=`` 传入的载荷。"""
        return [call["json"] for call in self.calls if "json" in call]
