# IXSPY AI API Python SDK

IXSPY AI API V1.0 官方 Python SDK。

## 安装

从 PyPI 安装：

```bash
pip install ixspy-ai-api
```

从源码安装：

```bash
git clone https://github.com/ixspyinc/ixspy-ai-api-python.git
cd ixspy-ai-api-python
python setup.py install
```

## 基础用法

SDK 使用异步任务模式。大多数图片和视频接口会先创建任务并返回 `task_id`，然后通过轮询查询任务状态，直到任务完成。

```python
import os
import sys
import time
from ixspy_ai_api import ImageClient

API_KEY = "YOUR_KEY"
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + "images/speaker.jpg"

client = ImageClient(api_key=API_KEY)

task_id = client.create_custom_composition(
    original_image=original_image_path,
    prompt="移除产品背景，只保留白色背景产品图",
)
print(f"任务 ID: {task_id}")

result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)
print("标清图 URL:", result["sd_image_url"])

# 高清图可能需要在任务完成后继续等待一小段处理时间。
time.sleep(30)
hd_url = client.get_hd_image(task_id)
print("高清图 URL:", hd_url)
```

更多示例请参考 `examples` 目录。

## 任务生命周期

图片和视频生成接口都基于任务执行：

1. 创建任务，例如调用 `create_custom_composition()` 或 `create_video()`。
2. API 返回 `task_id`。
3. 使用 `get_task_status()` 或 `get_video_status()` 查询任务状态。
4. 等待任务状态变为 `completed`。
5. 读取结果字段，例如 `sd_image_url`、`hd_image_url` 或 `video_url`。

常见任务状态：

- `queued`：任务已提交，正在等待执行。
- `processing`：任务正在生成中。
- `completed`：任务已成功完成，结果 URL 可用。
- `error`：任务执行失败。

便捷轮询方法：

- `ImageClient.wait_for_completion(task_id, poll_interval=3, timeout=180)`
- `VideoClient.wait_for_video_completion(task_id, poll_interval=15, timeout=600)`

如果任务失败或轮询超时，SDK 会抛出 `APIError`。

## API 文档

https://img.ixspy.com/api-doc.html
