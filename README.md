# IXSPY AI API Python SDK

IXSPY AI API V1.0 官方 Python SDK，覆盖**图片生成**、**视频生成**与**对话生成**。

- 同步客户端，基于 `requests`，无额外运行时依赖（仅需 `requests>=2.20`）。
- 统一的异常层级：只捕获 `APIError` 即可覆盖网络、鉴权、限流、服务端与任务失败。
- 图片输入自动归一化：本地路径、HTTP(S) URL、Base64（含 `data:image/...;base64,`）三种形式可混用。
- 完整的类型标注（含 `py.typed`），IDE 可直接补全返回值字段。

## 安装

从 PyPI 安装：

```bash
pip install ixspy-ai-api
```

从源码安装（开发模式）：

```bash
git clone https://github.com/ixspyinc/ixspy-ai-api-python.git
cd ixspy-ai-api-python
pip install -e .
```

> `python setup.py install` 已被 setuptools 弃用，请使用上面的 `pip install`。

## 快速开始

```python
import os

from ixspy_ai_api import ImageClient

client = ImageClient(api_key=os.environ["IXSPY_API_KEY"])

task_id = client.create_custom_composition(
    original_image="images/speaker.jpg",   # 本地路径 / URL / Base64 均可
    prompt="移除产品背景，只保留白色背景产品图",
)
print(f"任务 ID: {task_id}")

result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)
print("标清图 URL:", result["sd_image_url"])

hd_url = client.wait_for_hd_image(task_id, poll_interval=5, timeout=180)
print("高清图 URL:", hd_url)
```

客户端支持上下文管理器，退出时自动关闭连接池：

```python
with ImageClient(api_key=os.environ["IXSPY_API_KEY"]) as client:
    result = client.generate(
        client.TYPE_CUSTOM_COMPOSITION,
        original_image="images/speaker.jpg",
        prompt="请给这个便携音箱配置一个典型使用场景",
    )
    print(result["sd_image_url"])
```

## 配置参数

`AIClient` 构造函数参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `api_key` | 必填 | IXSPY 控制台获取的 API 密钥。 |
| `base_url` | `https://ixspy.com/ai-tool/api` | 自定义 API 基础地址。 |
| `timeout` | `90` | **单次 HTTP 请求**超时（秒）。`None` 表示不限制。 |
| `upload_timeout` | `300` | 图片上传的超时（秒），上传比普通请求慢，默认单独放宽。 |
| `max_upload_bytes` | 30 MiB | 单张图片体积上限；超限在本地拦截，`0` 表示不限制。 |
| `retries` | `3` | **幂等请求**（GET 与上传）的退避重试次数。创建任务的 POST 永不自动重试，避免重复生成与重复计费。 |

> `timeout` 与轮询方法的 `timeout` 是**两个不同的概念**：前者是单次请求上限，
> 后者是整个轮询过程的总等待上限。

## 任务生命周期

图片和视频接口都是异步任务模式：

1. 创建任务，例如调用 `create_custom_composition()` 或 `create_video()`。
2. API 返回 `task_id`。
3. 使用 `get_task_status()` 或 `get_video_status()` 查询任务状态。
4. 等待任务状态变为 `completed`。
5. 读取结果字段，例如 `sd_image_url`、`hd_image_url` 或 `video_url`。

任务状态：

| 状态 | 含义 |
| --- | --- |
| `queued` | 任务已提交，正在等待执行。 |
| `processing` | 任务正在生成中。 |
| `completed` | 任务已成功完成，结果 URL 可用。 |
| `error` | 任务执行失败。 |

便捷轮询方法：

- `ImageClient.wait_for_completion(task_id, poll_interval=3, timeout=180)`
- `ImageClient.wait_for_hd_image(task_id, poll_interval=5, timeout=180)`
- `VideoClient.wait_for_video_completion(task_id, poll_interval=15, timeout=600)`

两个方法的 `timeout` 都是**总等待上限**，传 `0` 或 `None` 表示不限制。

## 错误处理

所有 SDK 异常都继承自 `APIError`：

```
APIError                       基类；捕获它即可覆盖所有 SDK 侧错误
├── APIResponseError           响应不是合法 JSON / 信封结构异常 / data 缺失
├── APIConnectionError         网络不可达、连接失败、超时
├── AuthError                  401 / 403，通常是 api_key 无效
├── RateLimitError             429，含 retry_after 属性
├── ServerError                5xx
├── TaskFailedError            任务确实执行失败（服务端状态为 error）
└── TaskTimeoutError           本地轮询超过等待上限（任务可能仍在服务端运行）
```

```python
from ixspy_ai_api import APIError, RateLimitError, TaskFailedError, TaskTimeoutError

try:
    task_id = client.create_custom_composition(original_image="a.jpg", prompt="移除背景")
    result = client.wait_for_completion(task_id, timeout=180)
except TaskTimeoutError as exc:
    # 本地放弃等待，任务可能仍在服务端运行：task_id 可用于稍后继续查询。
    print(f"超时，稍后可凭 task_id={exc.task_id} 继续查询")
except TaskFailedError as exc:
    print(f"任务失败: {exc.message}")
except RateLimitError as exc:
    print(f"被限流，建议 {exc.retry_after}s 后重试")
except APIError as exc:
    # exc.code / exc.message / exc.http_status / exc.task_id / exc.original
    print(f"调用失败: {exc}")
```

本地参数错误（缺少必填参数、model 取值非法、图片路径不存在等）抛 `ValueError`、
`TypeError` 或 `FileNotFoundError`，不需要网络请求即可发现。

## 图片输入

以下三种形式在同一个参数里可以混用：

```python
client.create_custom_composition(original_image="images/a.jpg")                  # 本地文件（自动上传）
client.create_custom_composition(original_image="https://cdn.example.com/a.png") # 已有 URL，原样使用
client.create_custom_composition(original_image="data:image/png;base64,iVBOR...")  # Base64（自动剥离前缀）
```

注意：

- 相对路径以**当前工作目录**为基准，建议使用绝对路径（`pathlib.Path(__file__).parent / "a.jpg"`）。
- 路径不存在时会立即抛 `FileNotFoundError`，不会把无效路径发给服务端。
- 单张图片体积超过 `max_upload_bytes` 时会在本地拦截。

## 支持的模型

`model` 参数可选 `auto`、`gemini`、`chatgpt`；不传（`None`）表示由服务端选择默认模型。

除 `ai_upscale_2k` 外，所有图片任务都支持 `model`；`ai_upscale_2k` 传入 `model` 会抛 `ValueError`。

`ChatClient.generate()` 的 `model_tier`（`Flash` / `Pro`）仅在 `model="gemini"` 时生效，
其他取值组合会显式报错，而不是静默忽略该参数。

## 示例

示例统一从环境变量读取密钥：

```bash
export IXSPY_API_KEY="你的密钥"        # PowerShell: $env:IXSPY_API_KEY = "你的密钥"
python examples/create_custom_composition.py
```

| 示例 | 说明 |
| --- | --- |
| `create_custom_composition.py` | 分步骤创建单图自由构图任务、轮询结果并获取高清图。 |
| `create_custom_composition_multi.py` | 多图自由构图，使用多张输入图组合生成。 |
| `create_custom_composition_text_only.py` | 无参考图自由构图（纯文生图）。 |
| `image_generate.py` | 使用 `ImageClient.generate()` 一步式创建并等待完成。 |
| `video_generate.py` | 参考图生成视频，并查询已完成视频任务列表。 |
| `video_generate_text_only.py` | 纯文字生成视频，无需输入图片。 |
| `chat_generate.py` | 对话生成（同步返回），演示文字对话与图文识别。 |

## 开发

```bash
pip install -e ".[dev]"
python -m pytest          # 单元测试（纯本地，不访问网络）
python -m ruff check .
python -m mypy ixspy_ai_api
python -m build           # 打包校验
```

版本号以 `ixspy_ai_api/version.py` 为唯一来源，`pyproject.toml` 通过
`[tool.setuptools.dynamic]` 读取它，因此不会出现两处版本不一致的问题。

普通 CI 使用 `0.0.0.dev<运行编号>` 构建；发布版本从 Git 标签读取，并校验
wheel 版本与标签一致。`v1.2.3rc1` 会保留为 `1.2.3rc1`，非法发布标签会报错。
本地需要指定构建版本时，可设置环境变量 `IXSPY_AI_API_VERSION`。

轮询会在每次查询前后检查期限，并将剩余时间用于连接、读取超时以及重试等待。
同步网络调用无法强制中断所有底层操作（例如 DNS 解析或持续缓慢返回的响应体），
因此实际返回时间仍可能晚于期限；SDK 不会在期限耗尽后主动开始下一次查询。

## API 文档

https://img.ixspy.com/api-doc.html
