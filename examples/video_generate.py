"""参考图生成视频示例，并查询已完成视频任务列表。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/video_generate.py

视频任务通常需要 1-3 分钟，等待期间 task_id 仍然有效。
"""

from _common import image_path, require_api_key

from ixspy_ai_api import APIError, TaskFailedError, TaskTimeoutError, VideoClient


def main() -> None:
    client = VideoClient(api_key=require_api_key())

    video_task_id = client.create_video(
        reference_image=image_path("demo_result_generate.png"),
        prompt="生成产品展示视频",
        ratios="16:9",
    )
    print("视频任务 ID:", video_task_id)
    print("视频任务通常需要等待 1-3 分钟，请耐心等候...")

    try:
        video_result = client.wait_for_video_completion(video_task_id, poll_interval=15, timeout=600)
    except TaskTimeoutError as exc:
        # 与“任务失败”不同：任务可能仍在服务端运行，可用 task_id 继续查询。
        print(f"等待超时，任务可能仍在生成中: {exc}")
    except TaskFailedError as exc:
        print(f"视频任务失败: {exc}")
    except APIError as exc:
        print(f"接口调用失败: {exc}")
    else:
        print("视频 URL:", video_result.get("video_url"))
        # 示例结果可与 examples/images/demo_result_video_generate.mp4 对比。

    try:
        video_tasks = client.list_video_tasks(status="completed", page_size=20)
        print("已完成视频任务总数:", video_tasks.get("total"))
    except APIError as exc:
        print(f"查询任务列表失败: {exc}")


if __name__ == "__main__":
    main()
