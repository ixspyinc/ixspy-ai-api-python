"""自由构图无参考图示例（纯文生图）。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/create_custom_composition_text_only.py
"""

from _common import require_api_key

from ixspy_ai_api import APIError, ImageClient, TaskFailedError, TaskTimeoutError


def main() -> None:
    client = ImageClient(api_key=require_api_key())

    task_id = client.create_custom_composition(
        prompt="生成一张白色背景的现代桌面音箱产品图，电商主图风格",
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


if __name__ == "__main__":
    main()
