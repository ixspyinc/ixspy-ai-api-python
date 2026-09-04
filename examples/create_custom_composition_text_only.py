import os
import sys
import time

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import ImageClient

# 自由构图无参考图示例。

API_KEY = 'YOUR_KEY'

client = ImageClient(api_key=API_KEY)

task_id = client.create_custom_composition(
    prompt="生成一张白色背景的现代桌面音箱产品图，电商主图风格",
)
print(f"任务 ID: {task_id}")

result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)

print("标清图 URL:", result['sd_image_url'])

# 高清图可能需要在任务完成后继续等待一小段处理时间。
time.sleep(30)

hd_url = client.get_hd_image(task_id)
print("高清图 URL:", hd_url)
