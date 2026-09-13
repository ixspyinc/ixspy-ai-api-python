"""包版本号的唯一来源。

版本号按以下优先级解析：

1. 环境变量 ``IXSPY_AI_API_VERSION``（显式覆盖，本地构建或特殊流水线使用）。
2. 环境变量 ``GITHUB_REF_NAME`` / ``GITHUB_REF``（GitHub Actions 在 tag 构建时
   设置），支持 ``1.2.3``、``v1.2.3``、``refs/tags/v1.2.3`` 等形式。
   **必须优先于已安装发行版的元数据** —— 否则构建机上恰好装了旧版本时，
   会把旧版本号打进新的发行包。
3. 源码发行包的 ``PKG-INFO``（从 sdist 重建时保留原版本）。
4. 已安装发行版的元数据（``pip install`` 后的运行时场景）。
5. 兜底 ``0.0.0``（源码目录直接运行、未安装且无环境变量时）。

构建后端会导入本模块，所需的 packaging 同时声明为构建依赖与运行时依赖。
"""

import os
from email.parser import Parser
from pathlib import Path
from typing import Optional

from packaging.version import InvalidVersion, Version

#: 发行版名称，用于查询已安装版本元数据。
DISTRIBUTION_NAME = "ixspy-ai-api"

#: 无法确定版本时使用的占位值。
FALLBACK_VERSION = "0.0.0"


def normalize_version(raw: str) -> str:
    """解析版本或 refs/tags/ 标签，保留 PEP 440 预发布、开发及本地版本。

    非法版本抛 ValueError，防止将意外标签发布成正式版本。
    """
    candidate = raw.strip()
    if candidate.startswith("refs/tags/"):
        candidate = candidate[len("refs/tags/"):]
    try:
        return str(Version(candidate))
    except InvalidVersion as exc:
        raise ValueError(f"无效的发行版本: {raw!r}") from exc


def _version_from_metadata() -> str:
    # 构建后端导入模块时不保证源码根目录位于 sys.path；importlib.metadata
    # 可能读到构建机上的旧安装包。sdist 自带的 PKG-INFO 才是重建版本依据。
    pkg_info = Path(__file__).resolve().parent.parent / "PKG-INFO"
    if pkg_info.is_file():
        metadata = Parser().parsestr(pkg_info.read_text(encoding="utf-8"), headersonly=True)
        if metadata.get("Name", "").lower().replace("_", "-") == DISTRIBUTION_NAME:
            return normalize_version(metadata.get("Version", ""))
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8 不会进入此分支
        return FALLBACK_VERSION
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return FALLBACK_VERSION
    except Exception:  # pragma: no cover - 元数据损坏时不应阻断导入
        return FALLBACK_VERSION


def _candidate_from_ci_env() -> Optional[str]:
    """读取 CI（GitHub Actions）提供的版本线索，无法得到有效版本时返回 ``None``。"""
    ref = os.environ.get("GITHUB_REF", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    if ref.startswith("refs/tags/"):
        return normalize_version(ref)
    if ref_type == "tag":
        return normalize_version(os.environ.get("GITHUB_REF_NAME", ""))
    if ref or ref_type:
        return None  # 分支和 PR（含数字名称）不能作为发行版本。
    raw = os.environ.get("GITHUB_REF_NAME", "")
    if not raw:
        return None
    try:
        return normalize_version(raw)
    except ValueError:
        return None


def get_version() -> str:
    """返回当前生效的版本号字符串。"""
    explicit = os.environ.get("IXSPY_AI_API_VERSION")
    if explicit:
        return normalize_version(explicit)

    # CI 标记优先于元数据，避免构建机上安装的旧版本号被写进新发行包。
    from_ci = _candidate_from_ci_env()
    if from_ci is not None:
        return from_ci

    return _version_from_metadata()


__version__ = get_version()

#: 兼容旧代码：``VERSION = (1, 2, 3)`` 形式的整数元组。
VERSION = Version(__version__).release
