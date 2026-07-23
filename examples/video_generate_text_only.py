import os
import sys

sys.path.insert(0, sys.path[0] + "/../")
from ixspy_ai_api import VideoClient

# 纯文字生成视频示例 (无需原图)。

API_KEY = 'YOUR_KEY'
client = VideoClient(api_key=API_KEY)

print("正在提交纯文字视频生成任务...")
video_task_id = client.create_video(
    prompt="一个赛博朋克风格的未来城市，霓虹灯闪烁，飞行汽车穿梭在摩天大楼之间，电影级质感，4k，高清晰度",
    ratios="16:9"
)

print("视频任务 ID:", video_task_id)
print("视频任务通常需要等待 1-3 分钟，请耐心等候...")

try:
    video_result = client.wait_for_video_completion(video_task_id)
    print("视频生成成功！")
    print("视频 URL:", video_result['video_url'])
except Exception as e:
    print(f"视频生成失败: {e}")

video_tasks = client.list_video_tasks(status="completed")
print("已完成视频任务总数:", video_tasks['total'])
