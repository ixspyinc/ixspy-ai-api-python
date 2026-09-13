"""分步骤多图自由构图示例。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/create_custom_composition_multi.py
"""

from _common import image_path, require_api_key

from ixspy_ai_api import APIError, ImageClient, TaskFailedError, TaskTimeoutError


def main() -> None:
    client = ImageClient(api_key=require_api_key())

    original_images = [
        image_path("speaker.jpg"),
        image_path("demo_custom_composition_multi.jpeg"),
    ]

    task_id = client.create_custom_composition_multi(
        original_images=original_images,
        prompt="请用上传的图1中的 JBL 音箱替换图2的小音箱",
    )
    print(f"任务 ID: {task_id}")

    try:
        result = client.wait_for_completion(task_id, poll_interval=3, timeout=180)
    except TaskTimeoutError as exc:
        print(f"等待超时: {exc}")
        return
    except TaskFailedError as exc:
        print(f"任务失败: {exc}")
        return
    except APIError as exc:
        print(f"接口调用失败: {exc}")
        return

    print("标清图 URL:", result.get("sd_image_url"))

    try:
        hd_url = client.wait_for_hd_image(task_id, poll_interval=5, timeout=180)
    except (TaskTimeoutError, TaskFailedError, APIError) as exc:
        print(f"高清图获取失败（标清图已可用）: {exc}")
        return
    print("高清图 URL:", hd_url)

    # 示例结果可与 examples/images/demo_result_create_custom_composition_multi.jpg 对比。


if __name__ == "__main__":
    main()
