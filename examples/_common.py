"""示例公共辅助。

运行示例前请先设置 API Key，避免把密钥硬编码进源码：

    export IXSPY_API_KEY="你的密钥"     # Windows: set IXSPY_API_KEY=...
"""

import os
import sys
from pathlib import Path

# 让示例在没有 pip install 的情况下也能直接运行。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: 示例图片目录。
IMAGES_DIR = Path(__file__).resolve().parent / "images"


def require_api_key() -> str:
    """从环境变量读取 API Key，未设置时给出明确提示并退出。"""
    api_key = os.environ.get("IXSPY_API_KEY", "").strip()
    if not api_key:
        print(
            "未找到 API Key。请先设置环境变量 IXSPY_API_KEY 再运行示例，例如：\n"
            '  PowerShell:  $env:IXSPY_API_KEY = "你的密钥"\n'
            '  bash:        export IXSPY_API_KEY="你的密钥"',
            file=sys.stderr,
        )
        raise SystemExit(2)
    return api_key


def image_path(name: str) -> Path:
    """返回示例图片的绝对路径（以本文件位置为基准，不依赖当前工作目录）。"""
    path = IMAGES_DIR / name
    if not path.is_file():
        print(f"示例图片不存在: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path
