import os
import sys

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import ChatClient

# 带可选图片输入的对话生成示例。

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/demo_result_generate.png'

client = ChatClient(api_key=API_KEY)

# result = client.generate(prompt="用 Python 写一个快速排序")
# print(result)

result = client.generate(
    prompt="描述图片内容",
    original_image=original_image_path
)
print(result)
