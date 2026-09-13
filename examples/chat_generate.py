"""对话生成示例：文字对话与图文识别。

注意：对话接口是**同步返回**结果，没有 task_id，也不需要轮询。

运行方式：

    export IXSPY_API_KEY="你的密钥"
    python examples/chat_generate.py
"""

import json

from _common import image_path, require_api_key

from ixspy_ai_api import APIError, ChatClient

# 基础文字对话（去掉注释即可启用）：
# result = client.generate(prompt="Hello world!", model="gemini", model_tier="Pro")


def main() -> None:
    client = ChatClient(api_key=require_api_key())

    try:
        result = client.generate(
            prompt="描述图片内容",
            original_image=image_path("demo_result_generate.png"),
            model="chatgpt",
        )
    except APIError as exc:
        print(f"接口调用失败: {exc}")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
