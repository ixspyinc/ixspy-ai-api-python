import os
import sys
import time

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import ImageClient

# 分步骤自由构图示例。

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/speaker.jpg'

client = ImageClient(api_key=API_KEY)

task_id = client.create_custom_composition(
    original_image=original_image_path,
    prompt="移除产品背景，只保留白色背景产品图",
)
print(f"任务 ID: {task_id}")

result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)

# 可与 examples/images/demo_result_create_custom_composition.png 对比。
print("标清图 URL:", result['sd_image_url'])

# 高清图可能需要在任务完成后继续等待一小段处理时间。
time.sleep(30)

hd_url = client.get_hd_image(task_id)
print("高清图 URL:", hd_url)
