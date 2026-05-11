import os
import sys

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import ImageClient

# 一步式图片生成示例：创建任务并等待完成。

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/speaker.jpg'

client = ImageClient(api_key=API_KEY)

print("正在创建自由构图任务，通常需要等待 10-60 秒...")
result = client.generate(
    task_type=client.TYPE_CUSTOM_COMPOSITION,
    original_image=original_image_path,
    prompt="请给这个便携音箱配置一个典型使用场景",
    wait=True
)
print("任务 ID:", result['task_id'])

# 可与 examples/images/demo_result_generate.png 对比。
print("标清图 URL:", result['sd_image_url'])
