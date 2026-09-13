"""跨客户端共享的参数校验工具。

这些函数把原先散落在 ``ImageClient`` / ``VideoClient`` / ``ChatClient`` 中彼此
不一致的校验规则（例如 ``if prompt is None`` 与 ``if prompt:`` 的差别）收敛
到唯一实现，保证同一参数在所有接口上的行为一致。

所有校验失败都抛 :class:`ValueError` —— 它们是本地参数错误，不是 API 错误，
因此不应使用 :class:`~ixspy_ai_api.ai_client.APIError`。
"""

from typing import Any, Iterable, Optional

#: 图片生成支持的模型取值。
SUPPORTED_MODELS = frozenset({"auto", "gemini", "chatgpt"})

#: 对话生成支持的模型规格。
SUPPORTED_MODEL_TIERS = frozenset({"Flash", "Pro"})

#: 视频生成支持的画面比例。
SUPPORTED_VIDEO_RATIOS = frozenset({"16:9", "9:16"})


def validate_prompt(prompt: Any, param_name: str = "prompt") -> str:
    """校验提示词必须是非空字符串。

    同时拒绝 ``None``、非字符串和仅含空白字符的输入 —— 空提示词提交到服务端
    只会得到一个模糊的失败响应（视频任务还会产生费用），因此在本地拦截。
    """
    if prompt is None:
        raise ValueError(f"{param_name} 不能为空")
    if not isinstance(prompt, str):
        raise TypeError(f"{param_name} 必须是字符串，当前类型: {type(prompt).__name__}")
    if not prompt.strip():
        raise ValueError(f"{param_name} 不能为空字符串或仅含空白字符")
    return prompt


def validate_model(model: Optional[str], supported: Iterable[str] = SUPPORTED_MODELS) -> Optional[str]:
    """校验模型名是否受支持。``None`` 表示不指定，交由服务端选择默认模型。"""
    if model is None:
        return None
    allowed = sorted(supported)
    if model not in supported:
        raise ValueError(f"model 仅支持 {', '.join(repr(item) for item in allowed)}，当前: {model!r}")
    return model


def validate_model_tier(model_tier: Optional[str]) -> Optional[str]:
    """校验对话生成的模型规格。``None`` 表示不指定。"""
    if model_tier is None:
        return None
    if model_tier not in SUPPORTED_MODEL_TIERS:
        allowed = sorted(SUPPORTED_MODEL_TIERS)
        raise ValueError(f"model_tier 仅支持 {', '.join(repr(item) for item in allowed)}，当前: {model_tier!r}")
    return model_tier


def validate_ratio(ratios: Optional[str], supported: Iterable[str] = SUPPORTED_VIDEO_RATIOS,
                   param_name: str = "ratios") -> Optional[str]:
    """校验画面比例。``None`` 表示使用服务端默认值。"""
    if ratios is None:
        return None
    allowed = sorted(supported)
    if ratios not in supported:
        raise ValueError(f"{param_name} 仅支持 {', '.join(repr(item) for item in allowed)}，当前: {ratios!r}")
    return ratios


def validate_required_image(value: Any, param_name: str) -> None:
    """校验必填图片参数非空（拒绝 ``None``、空字符串与空列表）。"""
    if value is None:
        raise ValueError(f"{param_name} 不能为空")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{param_name} 不能为空字符串")
    if isinstance(value, (list, tuple)) and len(value) == 0:
        raise ValueError(f"{param_name} 不能为空列表")


def validate_pagination(page: int = 1, page_size: int = 20, max_page_size: int = 100) -> None:
    """校验分页参数。"""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError(f"page 必须是不小于 1 的整数，当前: {page!r}")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size < 1:
        raise ValueError(f"page_size 必须是不小于 1 的整数，当前: {page_size!r}")
    if page_size > max_page_size:
        raise ValueError(f"page_size 不能超过 {max_page_size}，当前: {page_size}")


__all__ = [
    "SUPPORTED_MODELS",
    "SUPPORTED_MODEL_TIERS",
    "SUPPORTED_VIDEO_RATIOS",
    "validate_prompt",
    "validate_model",
    "validate_model_tier",
    "validate_ratio",
    "validate_required_image",
    "validate_pagination",
]
