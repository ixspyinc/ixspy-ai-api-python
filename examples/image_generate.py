"""一步式图片生成示例：创建任务并等待完成。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/image_generate.py
"""

from _common import image_path, require_api_key

from ixspy_ai_api import APIError, ImageClient, TaskFailedError, TaskTimeoutError


def main() -> None:
    client = ImageClient(api_key=require_api_key())

    print("正在创建自由构图任务，通常需要等待 10-60 秒...")
    try:
        # generate() 是通用便捷接口；wait=True 时 timeout 默认 180 秒，
        # 传 None 才是无限等待。
        result = client.generate(
            task_type=client.TYPE_CUSTOM_COMPOSITION,
            original_image=image_path("speaker.jpg"),
            prompt="请给这个便携音箱配置一个典型使用场景",
            wait=True,
            timeout=180,
        )
    except TaskTimeoutError as exc:
        print(f"等待超时: {exc}")
        return
    except TaskFailedError as exc:
        print(f"任务失败: {exc}")
        return
    except APIError as exc:
        print(f"接口调用失败: {exc}")
        return

    print("任务 ID:", result["task_id"])
    print("标清图 URL:", result.get("sd_image_url"))

    # 示例结果可与 examples/images/demo_result_generate.png 对比。


if __name__ == "__main__":
    main()
