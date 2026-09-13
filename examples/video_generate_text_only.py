"""纯文字生成视频示例（无需参考图）。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/video_generate_text_only.py
"""

from _common import require_api_key

from ixspy_ai_api import APIError, TaskFailedError, TaskTimeoutError, VideoClient


def main() -> None:
    client = VideoClient(api_key=require_api_key())

    print("正在提交纯文字视频生成任务...")
    video_task_id = client.create_video(
        prompt="一个赛博朋克风格的未来城市，霓虹灯闪烁，飞行汽车穿梭在摩天大楼之间，电影级质感，4k，高清晰度",
        ratios="16:9",
    )
    print("视频任务 ID:", video_task_id)
    print("视频任务通常需要等待 1-3 分钟，请耐心等候...")

    try:
        video_result = client.wait_for_video_completion(video_task_id, poll_interval=15, timeout=600)
    except TaskTimeoutError as exc:
        # 只捕获预期异常，不吞掉编程错误（例如 KeyError）。
        print(f"等待超时，任务可能仍在生成中: {exc}")
    except TaskFailedError as exc:
        print(f"视频任务失败: {exc}")
    except APIError as exc:
        print(f"接口调用失败: {exc}")
    else:
        print("视频生成成功！")
        print("视频 URL:", video_result.get("video_url"))

    try:
        video_tasks = client.list_video_tasks(status="completed", page_size=20)
        print("已完成视频任务总数:", video_tasks.get("total"))
    except APIError as exc:
        print(f"查询任务列表失败: {exc}")


if __name__ == "__main__":
    main()
