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

构建后端调用 get_build_version，非法版本会硬失败；运行时 get_version 默认
对损坏的来源发出 RuntimeWarning 并继续回退，不让版本信息阻断 SDK 导入。
本模块依赖 packaging（并非零依赖），用其 PEP 440 解析器保留预发布后缀。
packaging>=20 同时声明为构建和运行时依赖，兼容本项目支持的 Python 3.8。
"""

import os
import warnings
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


def _version_problem(source: str, exc: Exception, strict: bool) -> None:
    message = f"无法使用{source}，将回退到其他版本来源: {exc}"
    if strict:
        raise ValueError(f"无法使用{source}: {exc}") from exc
    warnings.warn(message, RuntimeWarning, stacklevel=3)


def _normalize_candidate(raw: str, source: str, strict: bool) -> Optional[str]:
    try:
        return normalize_version(raw)
    except ValueError as exc:
        _version_problem(source, exc, strict)
        return None


def _version_from_metadata(*, strict: bool = False) -> str:
    # sdist 的 PKG-INFO 优先于构建机上可能残留的旧安装包。
    try:
        pkg_info = Path(__file__).resolve().parent.parent / "PKG-INFO"
        content = pkg_info.read_text(encoding="utf-8", errors="replace")
        metadata = Parser().parsestr(content, headersonly=True)
    except FileNotFoundError:
        metadata = None
    except (OSError, ValueError) as exc:
        _version_problem("源码包 PKG-INFO", exc, strict)
        metadata = None
    if metadata is not None and metadata.get("Name", "").lower().replace("_", "-") == DISTRIBUTION_NAME:
        raw = metadata.get("Version")
        # 缺失或空 Version 不作为版本候选，继续查询已安装元数据。
        if raw and raw.strip():
            candidate = _normalize_candidate(raw, "源码包 Version 字段", strict)
            if candidate is not None:
                return candidate
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8
        return FALLBACK_VERSION
    try:
        raw = version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return FALLBACK_VERSION
    except Exception as exc:
        _version_problem("已安装发行版元数据", exc, strict)
        return FALLBACK_VERSION
    if not raw:
        return FALLBACK_VERSION
    return _normalize_candidate(raw, "已安装发行版版本", strict) or FALLBACK_VERSION


def _candidate_from_ci_env(*, strict: bool = False) -> Optional[str]:
    """所有 CI 版本候选统一走同一容错策略；明确的分支/PR 不作为版本。"""
    ref = os.environ.get("GITHUB_REF", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    if ref.startswith("refs/tags/"):
        raw = ref
    elif ref_type == "tag":
        raw = os.environ.get("GITHUB_REF_NAME", "")
    elif ref or ref_type:
        return None
    else:
        raw = os.environ.get("GITHUB_REF_NAME", "")
        if not raw:
            return None
    return _normalize_candidate(raw, "GitHub 版本标签", strict)


def get_version(*, strict: bool = False) -> str:
    """解析版本；默认 warning 后回退，strict=True 用于构建期硬失败。"""
    explicit = os.environ.get("IXSPY_AI_API_VERSION")
    if explicit is not None:
        candidate = _normalize_candidate(explicit, "IXSPY_AI_API_VERSION", strict)
        if candidate is not None:
            return candidate
    from_ci = _candidate_from_ci_env(strict=strict)
    if from_ci is not None:
        return from_ci
    return _version_from_metadata(strict=strict)


def get_build_version() -> str:
    """setuptools 的动态版本入口，不允许非法候选被回退掩盖。"""
    return get_version(strict=True)


__version__ = get_version()

#: 兼容旧代码：``VERSION = (1, 2, 3)`` 形式的整数元组。
VERSION = Version(__version__).release
