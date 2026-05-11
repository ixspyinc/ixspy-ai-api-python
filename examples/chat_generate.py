import os
import sys
import time
sys.path.insert(0, sys.path[0]+"/../")
from ixspy_ai_api import ChatClient

# 图片生成视频演示

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/demo_result_generate.png'

client = ChatClient(api_key=API_KEY)

# result = client.generate(prompt="用Python写一个快速排序")
# print(result)

result = client.generate(
    prompt="描述图片内容",
    original_image=original_image_path
)
print(result)



