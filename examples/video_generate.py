import os
import sys

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import VideoClient

# 图片生成视频示例。

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/demo_result_generate.png'

client = VideoClient(api_key=API_KEY)

video_task_id = client.create_video(
    original_images=original_image_path,
    prompt="基于图片场景制作展示视频"
)

print("视频任务 ID:", video_task_id)
print("视频任务通常需要等待 1-3 分钟，请耐心等候...")

video_result = client.wait_for_video_completion(video_task_id)

# 可与 examples/images/demo_result_video_generate.mp4 对比。
print("视频 URL:", video_result['video_url'])

video_tasks = client.list_video_tasks(status="completed")
print("已完成视频任务总数:", video_tasks['total'])
