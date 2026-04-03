import os
import sys
import time
sys.path.insert(0, sys.path[0]+"/../")
from ixspy_ai_api import VideoClient

# 图片生成视频演示

API_KEY = 'YOUR_KEY'
FOLDER_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep
original_image_path = FOLDER_PATH + 'images/demo_result_generate.png'

client = VideoClient(api_key=API_KEY)

#发起视频任务
video_task_id = client.create_video(
    original_images=original_image_path,
    prompt="基于图片场景制作展示视频"
)

print("视频任务ID:", video_task_id)
print("视频任务通常需要等待2-3分钟，请耐心等候...")

# 等待视频完成
video_result = client.wait_for_video_completion(video_task_id)

# 可和预生成的图片 examples/images/demo_result_video_generate.mp4 对比
print("视频URL:", video_result['video_url'])

# 获取视频任务列表
video_tasks = client.list_video_tasks(status="completed")
print("视频任务总数:", video_tasks['total'])
