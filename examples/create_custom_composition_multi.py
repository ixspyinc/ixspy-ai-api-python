import os
import sys
import time

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import ImageClient

# 分步骤多图自由构图示例。

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path_1 = FOLDER_PATH + 'images/speaker.jpg'
original_image_path_2 = FOLDER_PATH + 'images/demo_custom_composition_multi.jpeg'
original_images = [original_image_path_1, original_image_path_2]

client = ImageClient(api_key=API_KEY)

task_id = client.create_custom_composition_multi(
    original_images=original_images,
    prompt="请用上传的图1中的 JBL 音箱替换图2的小音箱",
)
print(f"任务 ID: {task_id}")

result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)

# 可与 examples/images/demo_result_create_custom_composition_multi.jpg 对比。
print("标清图 URL:", result['sd_image_url'])

# 高清图可能需要在任务完成后继续等待一小段处理时间。
time.sleep(30)

hd_url = client.get_hd_image(task_id)
print("高清图 URL:", hd_url)
