"""IXSPY AI API 基础客户端。

本模块提供：

- :class:`AIClient`：封装鉴权、HTTP 请求、错误分类、重试、图片上传与输入归一化。
- 异常层级：:class:`APIError` 及其子类，见下方“异常模型”。
- :func:`wait_for_task`：与具体业务无关的任务轮询实现。

异常模型
--------

::

    APIError                       基类；捕获它即可覆盖所有 SDK 侧错误
    ├── APIResponseError           响应不是合法 JSON / 信封结构异常 / data 缺失
    ├── APIConnectionError         网络不可达、连接失败、超时
    ├── AuthError                  401 / 403
    ├── RateLimitError             429（含 Retry-After）
    ├── ServerError                5xx
    ├── TaskFailedError            任务本身执行失败（服务端状态为 error）
    └── TaskTimeoutError           本地轮询超过等待上限（任务可能仍在服务端运行）

区分 ``TaskFailedError`` 与 ``TaskTimeoutError`` 是刻意的：前者说明任务确实失败，
后者说明**本地放弃等待**，用户仍可拿 ``task_id`` 继续查询。
"""

import base64
import binascii
import json
import logging
import os
import time
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol, Tuple, Type, TypeVar, Union, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Timeout
from urllib3.util.retry import Retry

from .types import PENDING_TASK_STATUSES, TASK_STATUS_COMPLETED, TASK_STATUS_ERROR
from .version import __version__

logger = logging.getLogger(__name__)

#: 响应结构类型变量（绑定到具体 TypedDict，例如 ``ImageTaskResult``）。
ResultT = TypeVar("ResultT")


class MappingLike(Protocol):
    """只读映射的最小接口。

    既接受普通 ``dict``，也接受 :class:`~typing.TypedDict`（例如
    ``VideoTaskResult``），避免为了通过类型检查而在调用处撒 ``cast``。
    刻意只声明 ``__contains__`` 与 ``__getitem__`` —— TypedDict 在类型检查器
    眼中与 ``Mapping[str, Any]`` 并不兼容，但与这个最小协议兼容。
    """

    def __contains__(self, key: object) -> bool:
        ...

    def __getitem__(self, key: str) -> Any:
        ...

    def keys(self) -> Any:
        ...

#: 图片输入类型：本地路径 / HTTP(S) URL / Base64 字符串。
ImageInput = Union[str, Path]

#: 图片输入类型：单张或列表。
ImageInputs = Union[ImageInput, List[ImageInput]]

#: HTTP 请求超时（秒）。默认覆盖单次请求，不是轮询总耗时。
DEFAULT_REQUEST_TIMEOUT: Union[int, float] = 90

#: 图片上传的超时（秒）。上传比普通 JSON 请求慢得多，因此单独放宽。
DEFAULT_UPLOAD_TIMEOUT: Union[int, float] = 300

#: 轮询默认的“总等待上限”（秒）。``None`` 或 ``0`` 表示不限制。
DEFAULT_WAIT_TIMEOUT: Optional[Union[int, float]] = 180

#: 单张图片上传前允许的最大体积（字节）。0 表示不限制。
DEFAULT_MAX_UPLOAD_BYTES = 30 * 1024 * 1024

#: 重试策略：仅对幂等请求（GET / 图片上传）生效，避免重复创建付费任务。
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
RETRY_ALLOWED_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_DATA_URI_PREFIX = "data:"
_IMAGE_MIME_PREFIX = "image/"


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #

class APIError(Exception):
    """所有 SDK 错误的基类。

    属性:
        code: 服务端业务错误码；本地错误使用负值（见 :data:`LOCAL_ERROR_CODES`）。
        message: 人类可读的错误描述。
        time: 服务端时间戳（秒）；本地错误为 ``None``。
        http_status: HTTP 状态码（若错误来自 HTTP 响应）。
        task_id: 关联的任务 ID（若已知）。
        original: 触发该错误的底层异常（例如 ``requests.Timeout``）。
    """

    #: 基类默认错误码。
    default_code = -1

    def __init__(self,
                 code: Optional[int] = None,
                 message: str = "",
                 time: Optional[Union[int, float]] = None,
                 *,
                 http_status: Optional[int] = None,
                 task_id: Optional[int] = None,
                 original: Optional[BaseException] = None):
        self.code = int(self.default_code if code is None else code)
        self.message = message
        self.time = None if time is None else float(time)
        self.http_status = http_status
        self.task_id = task_id
        self.original = original
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [f"API Error {self.code}"]
        if self.http_status is not None:
            parts.append(f"HTTP {self.http_status}")
        if self.task_id is not None:
            parts.append(f"task {self.task_id}")
        return f"{' | '.join(parts)}: {self.message}"


class APIResponseError(APIError):
    """响应不是合法 JSON、信封结构异常，或缺少必需的 ``data``。"""

    default_code = -2


class APIConnectionError(APIError):
    """网络层面失败：DNS、连接被拒、读超时等。"""

    default_code = -3


class AuthError(APIError):
    """鉴权或权限失败（HTTP 401/403）。"""

    default_code = -4


class RateLimitError(APIError):
    """请求被限流（HTTP 429）。"""

    default_code = -5

    def __init__(self, *args: Any, retry_after: Optional[float] = None, **kwargs: Any):
        self.retry_after = retry_after
        super().__init__(*args, **kwargs)


class ServerError(APIError):
    """服务端错误（HTTP 5xx）。"""

    default_code = -6


class TaskFailedError(APIError):
    """任务执行失败：服务端返回的状态为 ``error``。"""

    default_code = 1000


class TaskTimeoutError(APIError):
    """本地轮询达到等待上限。

    任务**可能仍在服务端运行**，可凭 ``task_id`` 继续查询。
    """

    default_code = 1001


#: 本地错误码（非服务端返回）语义表。
LOCAL_ERROR_CODES = {
    -1: "未分类错误",
    -2: "响应格式错误",
    -3: "网络连接错误",
    -4: "鉴权失败",
    -5: "请求被限流",
    -6: "服务端错误",
    1000: "任务执行失败",
    1001: "轮询超时",
}


# 每个线程/上下文独立保存轮询期限，避免共享客户端时互相覆盖。
_poll_deadline: ContextVar[Optional[Tuple[float, int, str]]] = ContextVar("poll_deadline", default=None)


def _remaining_poll_time() -> Optional[float]:
    deadline = _poll_deadline.get()
    if deadline is None:
        return None
    remaining = deadline[0] - time.monotonic()
    if remaining <= 0:
        raise TaskTimeoutError(
            message=f"{deadline[2]} {deadline[1]} 等待超时。任务可能仍在服务端运行，可凭 task_id 继续查询。",
            task_id=deadline[1],
        )
    return remaining


@contextmanager
def _polling_budget(timeout: Optional[Union[int, float]], task_id: int, label: str) -> Iterator[None]:
    previous = _poll_deadline.get()
    deadline = (time.monotonic() + timeout, task_id, label) if timeout else previous
    if previous is not None and deadline is not None and previous[0] < deadline[0]:
        deadline = previous
    token = _poll_deadline.set(deadline)
    try:
        yield
    finally:
        _poll_deadline.reset(token)


class _DeadlineTimeout(Timeout):
    """urllib3 每次尝试都会 clone 超时对象，在此重新计算剩余预算。"""

    def __init__(self, total: float, connect: float, read: float):
        super().__init__(total=total, connect=connect, read=read)
        self._budget_total = total
        self._budget_connect = connect
        self._budget_read = read

    def clone(self) -> Timeout:
        remaining = _remaining_poll_time()
        budget = self._budget_total if remaining is None else min(self._budget_total, remaining)
        return _DeadlineTimeout(budget, min(self._budget_connect, budget), min(self._budget_read, budget))


class _DeadlineRetry(Retry):
    """让 HTTP 重试的退避和 Retry-After 服从当前轮询期限。"""

    def sleep(self, response=None) -> None:
        remaining = _remaining_poll_time()
        if remaining is None:
            return super().sleep(response)
        delay = self.get_retry_after(response) if self.respect_retry_after_header and response else None
        delay = delay or self.get_backoff_time()
        if delay:
            time.sleep(min(delay, remaining))
        _remaining_poll_time()


# --------------------------------------------------------------------------- #
# 输入识别辅助
# --------------------------------------------------------------------------- #

def _is_http_url(value: str) -> bool:
    """判断字符串是否为 HTTP(S) URL。"""
    return value.startswith(("http://", "https://"))


def _strip_data_uri(value: str) -> Tuple[str, Optional[str]]:
    """拆分 ``data:`` URI。

    返回 ``(payload, mime_type)``；若不是 data URI，则返回 ``(原值, None)``。
    Base64 载荷会去掉 ``data:image/png;base64,`` 前缀 —— 服务端只需要纯载荷，
    保留前缀既浪费带宽又依赖服务端的宽容度。
    """
    if not value.lower().startswith(_DATA_URI_PREFIX):
        return value, None

    header, separator, payload = value.partition(',')
    if not separator:
        raise ValueError("data URI 缺少 ',' 分隔符，无法解析 Base64 载荷")

    mime_type = header[len(_DATA_URI_PREFIX):].split(';', 1)[0].strip().lower() or None
    is_base64 = any(part.strip().lower() == "base64" for part in header.split(';')[1:])
    if not is_base64:
        raise ValueError(
            "data URI 不是 Base64 编码。请使用 data:image/png;base64,<数据> 形式，"
            "或先把图片写入本地文件再传入路径。"
        )
    return payload.strip(), mime_type


def _looks_like_base64_image(value: str) -> bool:
    """判断字符串是否像 Base64 编码的图片数据。

    仅返回 ``True`` 的情况：带 ``data:image`` 前缀且声明 base64，或长度达到
    图片量级的裸 Base64 串。判定刻意保守——误判会把无效内容发往服务端，而漏判
    只会让服务端返回更明确的错误。
    """
    stripped = value.strip()
    if not stripped:
        return False

    has_data_prefix = stripped.lower().startswith(_DATA_URI_PREFIX)
    if has_data_prefix:
        try:
            payload, mime_type = _strip_data_uri(stripped)
        except ValueError:
            return False
        if mime_type is not None and not mime_type.startswith(_IMAGE_MIME_PREFIX):
            return False
        if not payload:
            return False
        return _decodes_as_base64(payload)

    # 裸 Base64：图片数据必然远长于一般字符串，用长度先过滤噪声。
    if len(stripped) < 256:
        return False
    return _decodes_as_base64(stripped)


def _decodes_as_base64(value: str) -> bool:
    """在移除空白后尝试严格 Base64 解码。"""
    compact = ''.join(value.split())
    if not compact or len(compact) % 4 == 1:
        return False
    # 自动兼容 URL-safe 字母表（部分编码器会用 - 和 _ 代替 + 和 /）。
    uses_urlsafe = ('-' in compact or '_' in compact)
    try:
        base64.b64decode(compact, altchars=b"-_" if uses_urlsafe else None, validate=True)
    except (binascii.Error, ValueError):
        # 缺少 padding 的合法 Base64 也应被接受。
        padded = compact + '=' * (-len(compact) % 4)
        try:
            base64.b64decode(padded, altchars=b"-_" if uses_urlsafe else None, validate=True)
        except (binascii.Error, ValueError):
            return False
    return True


def _looks_like_local_path(value: str) -> bool:
    """判断字符串是否更像本地文件路径而不是 URL/Base64。

    只做保守判断：出现路径分隔符、Windows 盘符或常见图片扩展名即视为路径。
    """
    if '\\' in value or '/' in value:
        return True
    if len(value) > 1 and value[1] == ':':  # 例如 C:foo.jpg
        return True
    return Path(value).suffix.lower() in {
        '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.heic', '.avif'
    }


# --------------------------------------------------------------------------- #
# 轮询
# --------------------------------------------------------------------------- #

class StatusPayload(Protocol):
    """轮询所需的最小响应接口。

    使用 :class:`~typing.Protocol` 而不是 ``Dict[str, Any]``，是为了让
    ``wait_for_task`` 既能接收普通的 ``dict``，也能接收结构更精确的
    :class:`~typing.TypedDict`（例如 ``ImageTaskResult``）—— TypedDict 与
    ``Dict[str, Any]`` 之间在类型检查器看来并不互相兼容。
    """

    def get(self, key: str, default: Any = ...) -> Any:
        ...


def wait_for_task(
    fetch_status: Callable[[], ResultT],
    task_id: int,
    *,
    poll_interval: float = 3,
    timeout: Optional[Union[int, float]] = DEFAULT_WAIT_TIMEOUT,
    task_label: str = "任务",
) -> ResultT:
    """通用任务轮询。

    参数:
        fetch_status: 无参回调，返回最新任务数据（内部通常调用状态查询接口）。
        task_id: 任务 ID，仅用于错误信息。
        poll_interval: 两次查询之间的间隔（秒），支持小数。
        timeout: **总等待上限**（秒）；``None`` 或 ``0`` 表示不限制。
            与请求级超时不同，这里统计的是从开始轮询到结束的总时间。
            同步回调不能被强制中断；SDK 请求会使用剩余预算限制超时和重试。
        task_label: 错误信息中的任务类别（如 ``"图片任务"``）。

    返回:
        状态为 ``completed`` 的任务数据。

    抛出:
        TaskFailedError: 服务端状态为 ``error``。
        TaskTimeoutError: 超过 ``timeout`` 秒仍未结束。
        APIError: 返回了未知状态。
    """
    if poll_interval is not None and poll_interval < 0:
        raise ValueError(f"poll_interval 不能为负数，当前: {poll_interval}")
    if timeout is not None and timeout < 0:
        raise ValueError(f"timeout 不能为负数，当前: {timeout}")

    with _polling_budget(timeout, task_id, task_label):
        while True:
            _remaining_poll_time()
            data: Any = fetch_status()
            remaining = _remaining_poll_time()
            status = data.get('status')
            if status == TASK_STATUS_COMPLETED:
                return cast(ResultT, data)
            if status == TASK_STATUS_ERROR:
                raise TaskFailedError(
                    message=f"{task_label} {task_id} 执行失败: {data.get('error') or '服务端未返回失败原因'}",
                    task_id=task_id,
                )
            if status not in PENDING_TASK_STATUSES:
                raise APIError(code=-7, message=f"{task_label} {task_id} 返回未知状态: {status!r}", task_id=task_id)
            sleep_for = poll_interval if remaining is None else min(poll_interval, remaining)
            if sleep_for:
                time.sleep(sleep_for)


# --------------------------------------------------------------------------- #
# 基础客户端
# --------------------------------------------------------------------------- #

class AIClient:
    """IXSPY AI 服务基础客户端。

    参数:
        api_key: IXSPY 控制台获取的 API 密钥。
        base_url: 可选的自定义 API 基础地址。
        timeout: **单次 HTTP 请求**超时（秒），默认 90。``None`` 表示不限制。
            这**不是**轮询总耗时，轮询上限见各客户端的 ``timeout`` 参数。
        upload_timeout: 图片上传的请求超时（秒），默认 300。
        max_upload_bytes: 单张图片上传体积上限（字节），默认 30 MiB，``0`` 表示不限制。
        retries: 幂等请求（GET / 上传）的额外重试次数，默认 3；``0`` 表示关闭。
    """

    BASE_URL = "https://ixspy.com/ai-tool/api"

    def __init__(self,
                 api_key: str,
                 base_url: Optional[str] = None,
                 timeout: Optional[Union[int, float]] = DEFAULT_REQUEST_TIMEOUT,
                 *,
                 upload_timeout: Optional[Union[int, float]] = DEFAULT_UPLOAD_TIMEOUT,
                 max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
                 retries: int = RETRY_TOTAL):
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key 不能为空")
        self.api_key = str(api_key).strip()
        self.base_url = (base_url or self.BASE_URL).rstrip('/')
        self.timeout = timeout
        self.upload_timeout = upload_timeout if upload_timeout is not None else timeout
        self.max_upload_bytes = max_upload_bytes
        self.user_agent = f"ixspy-ai-api-python/{__version__}"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        })
        self._upload_adapter: Optional[HTTPAdapter] = None
        self._default_adapter: Optional[HTTPAdapter] = None
        self._configure_retries(retries)

    # -- 内部：HTTP ---------------------------------------------------------- #

    def _configure_retries(self, retries: int) -> None:
        """为幂等方法挂载退避重试。

        只对 ``GET``/``HEAD``/``OPTIONS`` 与显式标记的上传请求生效 —— 创建任务
        的 ``POST`` 绝不自动重试，否则可能重复生成并重复计费。
        """
        if retries <= 0:
            return
        retry = _DeadlineRetry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=RETRY_ALLOWED_METHODS,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        # 上传走的也是 POST，因此为上传单独放行 POST+PUT。
        upload_retry = retry.new(total=retries, allowed_methods=frozenset({"POST", "PUT"}))
        default_adapter = HTTPAdapter(max_retries=retry)
        self._default_adapter = default_adapter
        self._upload_adapter = HTTPAdapter(max_retries=upload_retry)
        self.session.mount("https://", default_adapter)
        self.session.mount("http://", default_adapter)
        self.session.mount(f"{self.base_url}/v1/images/upload", self._upload_adapter)

    def _build_headers(self, kwargs: Dict[str, Any]) -> None:
        """按请求体类型设置 ``Content-Type``（multipart 交由 requests 处理）。"""
        headers = dict(kwargs.pop('headers', None) or {})
        if 'files' in kwargs:
            pass  # requests 会自动写入带 boundary 的 multipart Content-Type
        elif 'json' in kwargs:
            headers.setdefault('Content-Type', 'application/json')
        elif 'data' in kwargs:
            headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        if headers:
            kwargs['headers'] = headers

    def _send(self, method: str, url: str, kwargs: Dict[str, Any]):
        """发起一次实际请求，并把网络异常转换为 :class:`APIConnectionError`。"""
        request_kwargs = dict(kwargs)
        if self.timeout is not None:
            request_kwargs.setdefault('timeout', self.timeout)
        remaining = _remaining_poll_time()
        if remaining is not None:
            configured = request_kwargs.get('timeout')
            if isinstance(configured, tuple):
                connect, read = configured
            else:
                connect = read = configured
            request_kwargs['timeout'] = _DeadlineTimeout(
                total=remaining,
                connect=min(connect, remaining) if connect is not None else remaining,
                read=min(read, remaining) if read is not None else remaining,
            )
        try:
            response = self.session.request(method, url, **request_kwargs)
            _remaining_poll_time()
            return response
        except requests.exceptions.Timeout as exc:
            _remaining_poll_time()
            raise APIConnectionError(
                message=(
                    f"请求 {method} {url} 超时（单次请求上限 {request_kwargs.get('timeout')}s）。"
                    "若为轮询请求，可通过 timeout 参数调整；若为上传，请调大 upload_timeout。"
                ),
                original=exc,
            ) from exc
        except requests.exceptions.RequestException as exc:
            _remaining_poll_time()
            raise APIConnectionError(
                message=f"请求 {method} {url} 失败: {exc}",
                original=exc,
            ) from exc

    def _request(self, method: str, endpoint: str, *, _upload: bool = False, **kwargs: Any) -> Dict[str, Any]:
        """发送 HTTP 请求并解析统一响应信封。

        参数:
            method: HTTP 方法。
            endpoint: 以 ``/`` 开头的接口路径。
            _upload: 内部标记，表示这是一次图片上传（超时更长、允许重试 POST）。
            **kwargs: 透传给 ``requests`` 的参数。

        返回:
            响应中的 ``data`` 字段。

        抛出:
            APIError: 及其子类，覆盖网络、鉴权、限流、服务端与业务错误。
        """
        url = f"{self.base_url}{endpoint}"
        self._build_headers(kwargs)
        if _upload:
            kwargs.setdefault('timeout', self.upload_timeout)
        response = self._send(method, url, kwargs)

        return self._parse_response(response, method, url)

    def _parse_response(self, response, method: str, url: str) -> Dict[str, Any]:
        """校验 HTTP 状态与响应信封，返回 ``data`` 字段。"""
        status_code = response.status_code
        if status_code >= 400:
            self._raise_for_status(response, method, url)

        try:
            payload = response.json()
        except ValueError:
            snippet = (response.text or "")[:200]
            raise APIResponseError(
                message=f"响应不是合法 JSON（{method} {url}）: {snippet!r}",
                http_status=status_code,
            ) from None

        if not isinstance(payload, dict):
            raise APIResponseError(
                message=f"响应信封不是 JSON 对象（{method} {url}），实际类型: {type(payload).__name__}",
                http_status=status_code,
            )

        if 'error' not in payload:
            raise APIResponseError(
                message=(
                    f"响应缺少 'error' 字段（{method} {url}），"
                    f"无法判断调用结果。响应键: {sorted(payload)[:10]}"
                ),
                http_status=status_code,
            )

        error = payload.get('error') or {}
        if not isinstance(error, dict):
            raise APIResponseError(
                message=f"'error' 字段不是对象（{method} {url}），实际类型: {type(error).__name__}",
                http_status=status_code,
            )

        code = error.get('code', APIError.default_code)
        if code != 0:
            raise APIError(
                code=code,
                message=error.get('message') or LOCAL_ERROR_CODES.get(code, '未知错误'),
                time=error.get('time'),
                http_status=status_code,
            )

        data = payload.get('data')
        if data is None:
            raise APIResponseError(
                message=(
                    f"响应缺少 'data' 字段（{method} {url}）。"
                    "这通常意味着服务端返回了非预期结构，而不是空结果。"
                ),
                http_status=status_code,
            )
        if not isinstance(data, dict):
            raise APIResponseError(
                message=f"'data' 字段不是对象（{method} {url}），实际类型: {type(data).__name__}",
                http_status=status_code,
            )
        return data

    def _raise_for_status(self, response, method: str, url: str) -> None:
        """把 HTTP 错误状态映射为具体异常类型。"""
        status_code = response.status_code
        message = self._extract_error_message(response) or self._default_http_message(status_code)
        context = f"{method} {url}"

        if status_code in (401, 403):
            raise AuthError(
                message=f"{context} 鉴权失败（HTTP {status_code}）: {message}。请检查 api_key 是否有效。",
                http_status=status_code,
            )
        if status_code == 429:
            retry_after = self._parse_retry_after(response)
            raise RateLimitError(
                message=(
                    f"{context} 触发限流（HTTP 429）: {message}"
                    + (f"，建议 {retry_after:g}s 后重试" if retry_after else "")
                ),
                http_status=status_code,
                retry_after=retry_after,
            )
        if status_code >= 500:
            raise ServerError(
                message=f"{context} 服务端错误（HTTP {status_code}）: {message}",
                http_status=status_code,
            )
        raise APIError(
            message=f"{context} 请求失败（HTTP {status_code}）: {message}",
            http_status=status_code,
        )

    @staticmethod
    def _extract_error_message(response) -> Optional[str]:
        """尽力从错误响应里提取可读信息，兼容 JSON 与纯文本/HTML。"""
        try:
            payload = response.json()
        except ValueError:
            text = (response.text or "").strip()
            if not text:
                return None
            return text[:200]
        if isinstance(payload, dict):
            error = payload.get('error')
            if isinstance(error, dict) and error.get('message'):
                return str(error['message'])
            for key in ('message', 'msg', 'detail', 'error'):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
            return json.dumps(payload, ensure_ascii=False)[:200]
        return str(payload)[:200]

    @staticmethod
    def _default_http_message(status_code: int) -> str:
        if status_code == 429:
            return "请求过于频繁"
        if status_code >= 500:
            return "服务端暂时不可用，可稍后重试"
        return "服务端拒绝了该请求"

    @staticmethod
    def _parse_retry_after(response) -> Optional[float]:
        raw = response.headers.get('Retry-After') if getattr(response, 'headers', None) else None
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    # -- 内部：结果提取 ------------------------------------------------------ #

    def _request_as(self, result_type: Type[ResultT], method: str, endpoint: str,
                    **kwargs: Any) -> ResultT:
        """发起请求并把返回的 ``dict`` 收窄为具体的响应结构类型。

        服务端返回的是自由形态的 JSON 对象，:class:`~typing.TypedDict` 只用于
        描述已知字段，因此这里用显式的类型转换表达「结构由服务端约定」。
        """
        return cast(ResultT, cast(Any, self._request(method, endpoint, **kwargs)))
    @staticmethod
    def _require_field(data: "MappingLike", field: str, context: str) -> Any:
        """从响应数据中取必需字段，缺失时给出明确的 APIResponseError。"""
        if field not in data or data[field] is None:
            keys = sorted(data.keys())[:10] if hasattr(data, "keys") else []
            raise APIResponseError(
                message=f"{context} 的响应缺少字段 {field!r}。可用字段: {keys}"
            )
        return data[field]

    @classmethod
    def _require_int(cls, data: "MappingLike", field: str, context: str) -> int:
        value = cls._require_field(data, field, context)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise APIResponseError(
                message=f"{context} 的字段 {field!r} 不是整数: {value!r}",
            ) from None

    # -- 图片输入归一化 ------------------------------------------------------ #

    @classmethod
    def _is_base64_image_input(cls, input_str: str) -> bool:
        """判断字符串是否为 Base64 图片数据。

        保留该方法以兼容旧调用；实现委托给模块级 :func:`_looks_like_base64_image`。
        """
        return _looks_like_base64_image(input_str)

    def _prepare_single_image(self, image_input: ImageInput) -> str:
        """把单个图片输入归一化为 CDN URL。

        处理规则（按顺序）：

        1. ``http(s)://`` → 原样返回。
        2. 存在的本地路径 → 上传并返回 CDN URL。
        3. Base64（含 ``data:image/...;base64,`` 前缀）→ 去掉前缀后上传，返回 CDN URL。
        4. 其他字符串 → 原样交由服务端校验（用于服务端已托管的相对资源标识）。

        抛出:
            FileNotFoundError: 输入**看起来是本地路径**但文件不存在。此前这种输入
                会被静默发给服务端，导致难以理解的 400 错误。
            ValueError: ``data:`` URI 结构非法。
        """
        if isinstance(image_input, Path):
            return self._load_local_image(image_input)

        if not isinstance(image_input, str):
            raise TypeError(f"图片输入必须是 str、Path 或它们的列表，当前类型: {type(image_input).__name__}")

        value = image_input.strip()
        if not value:
            raise ValueError("图片输入不能为空字符串")

        if _is_http_url(value):
            return value

        if os.path.isfile(value):
            return self._load_local_image(value)

        if _looks_like_base64_image(value):
            payload, _mime = _strip_data_uri(value) if value.lower().startswith(_DATA_URI_PREFIX) else (value, None)
            return self.upload_image_base64(payload)

        if _looks_like_local_path(value):
            raise FileNotFoundError(
                f"图片文件不存在: {image_input!r}。"
                "请传入存在的本地路径、http(s) URL 或 Base64 数据"
                "（相对路径以当前工作目录为基准，建议使用绝对路径）。"
            )

        logger.debug("图片输入既不是 URL/路径也不是 Base64，交由服务端校验: %.80s", value)
        return value

    def _load_local_image(self, file_path: Union[str, Path]) -> str:
        """读取并上传本地图片，带体积预校验。"""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {str(path)!r}")
        if self.max_upload_bytes:
            size = path.stat().st_size
            if size > self.max_upload_bytes:
                raise ValueError(
                    f"图片体积 {size / 1024 / 1024:.1f} MiB 超过上限 "
                    f"{self.max_upload_bytes / 1024 / 1024:.1f} MiB: {str(path)!r}"
                )
        return self.upload_image_file(path)

    def _prepare_images(self, images: ImageInputs) -> Union[str, List[str]]:
        """归一化单张图片或图片列表，保持输入形状。

        返回:
            ``str``（输入为单张）或 ``List[str]``（输入为列表）。
        """
        if isinstance(images, (str, Path)):
            return self._prepare_single_image(images)
        if isinstance(images, (list, tuple)):
            return [self._prepare_single_image(item) for item in images]
        raise TypeError(
            f"images 必须是字符串、Path 对象或它们的列表，当前类型: {type(images).__name__}"
        )

    def _prepare_image_list(self, images: ImageInputs) -> List[str]:
        """归一化图片输入并**始终**返回列表。"""
        prepared = self._prepare_images(images)
        return list(prepared) if isinstance(prepared, list) else [prepared]

    # -- 上传 ---------------------------------------------------------------- #

    def upload_image_file(self, file_path: Union[str, Path]) -> str:
        """上传本地图片文件。

        参数:
            file_path: 本地图片路径。

        返回:
            CDN 图片 URL。
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {str(path)!r}")

        filename = path.name
        with path.open('rb') as handle:
            files = {'image': (filename, handle)}
            data = self._request('POST', '/v1/images/upload', _upload=True, files=files)
        return self._require_field(data, 'url', f'上传图片 {filename}')

    def upload_image_base64(self, base64_str: str) -> str:
        """上传 Base64 编码的图片。

        参数:
            base64_str: Base64 字符串，可包含 ``data:image/...;base64,`` 前缀
                （前缀会被自动剥离，只需传纯载荷也可以）。

        返回:
            CDN 图片 URL。
        """
        if not isinstance(base64_str, str) or not base64_str.strip():
            raise ValueError("base64_str 不能为空")
        payload_str = base64_str.strip()
        if payload_str.lower().startswith(_DATA_URI_PREFIX):
            payload_str, _mime = _strip_data_uri(payload_str)
        if not payload_str:
            raise ValueError("Base64 载荷为空")

        data = self._request('POST', '/v1/images/upload', _upload=True, json={"image_base64": payload_str})
        return self._require_field(data, 'url', '上传 Base64 图片')

    # -- 生命周期 ------------------------------------------------------------ #

    def close(self) -> None:
        """关闭底层连接池。"""
        self.session.close()

    def __enter__(self) -> "AIClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} base_url={self.base_url!r} version={__version__}>"


def warn_deprecated(old: str, new: str, stacklevel: int = 3) -> None:
    """发出统一的弃用提示。"""
    warnings.warn(f"{old} 已弃用，请改用 {new}", DeprecationWarning, stacklevel=stacklevel)


__all__ = [
    "AIClient",
    "APIError",
    "APIResponseError",
    "APIConnectionError",
    "AuthError",
    "RateLimitError",
    "ServerError",
    "TaskFailedError",
    "TaskTimeoutError",
    "LOCAL_ERROR_CODES",
    "DEFAULT_REQUEST_TIMEOUT",
    "DEFAULT_UPLOAD_TIMEOUT",
    "DEFAULT_WAIT_TIMEOUT",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "ImageInput",
    "ImageInputs",
    "wait_for_task",
    "warn_deprecated",
]
