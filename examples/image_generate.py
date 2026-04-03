import os
import sys
import time
sys.path.insert(0, sys.path[0]+"/../")
from ixspy_ai_api import ImageClient

# 封装好一次性调用, 需要自己传入对应的参数

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/speaker.jpg'

client = ImageClient(api_key=API_KEY)

print("正在請求'自由構圖'， 需要等待30-60秒完成...")
result = client.generate(
    task_type=client.TYPE_CUSTOM_COMPOSITION,
    original_image=original_image_path,
    prompt="请给这个便携音箱配置随机配置一个典型使用场景",
    wait=True
)
print("任务ID:", result['task_id'])  # generate 已把 task_id 加入结果

# 可和预生成的图片 examples/images/demo_result_generate.png 对比
print("标清图:", result['sd_image_url'])


