"""IXSPY AI 图片生成客户端。

新增任务类型只需在 :data:`TASK_SPECS` 中加一行声明，再写一个薄包装方法 ——
必填校验、``None`` 清理、默认值、图片归一化与模型校验都由
:meth:`ImageClient.create_task` 统一驱动，不必逐方法重复。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

from .ai_client import (
    DEFAULT_WAIT_TIMEOUT,
    AIClient,
    ImageInput,
    TaskFailedError,
    wait_for_task,
)
from .types import (
    TASK_STATUS_ERROR,
    ImageTaskResult,
    TaskListPage,
)
from .validation import validate_model, validate_pagination, validate_prompt, validate_required_image


@dataclass(frozen=True)
class TaskSpec:
    """单个图片任务类型的参数声明。

    属性:
        required: 必填字段名。
        optional: 可选字段名及其默认值（默认值为 ``None`` 表示未提供时不下发）。
        image_fields: 需要归一化为图片输入的字段名。
        list_inputs: ``image_fields`` 中「同时接受单张与列表」的字段。
            ``custom_composition_multi`` 的 ``original_image`` 即为此类：它接收
            多张图，但字段名是单数，因此需要显式声明。
    """

    required: FrozenSet[str] = field(default_factory=frozenset)
    optional: Mapping[str, Any] = field(default_factory=dict)
    image_fields: FrozenSet[str] = field(default_factory=frozenset)
    list_inputs: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def known_fields(self) -> FrozenSet[str]:
        """该任务类型接受的全部参数名。"""
        return self.required | frozenset(self.optional) | self.image_fields


def _spec(required: Tuple[str, ...] = (),
          optional: Optional[Dict[str, Any]] = None,
          image_fields: Tuple[str, ...] = (),
          list_inputs: Tuple[str, ...] = ()) -> TaskSpec:
    return TaskSpec(
        required=frozenset(required),
        optional=dict(optional or {}),
        image_fields=frozenset(image_fields),
        list_inputs=frozenset(list_inputs),
    )


#: 图片任务类型 → 参数声明。新增接口在此加一行即可。
TASK_SPECS: Dict[str, TaskSpec] = {
    'custom_composition_multi': _spec(
        required=('prompt',),
        optional={'ratios': 'auto', 'model': None},
        image_fields=('original_image',),
        list_inputs=('original_image',),
    ),
    'custom_composition': _spec(
        required=('prompt',),
        optional={'ratios': 'auto', 'model': None},
        image_fields=('original_image',),
    ),
    'scene_replacement': _spec(
        required=('original_image',),
        optional={'prompt': None, 'ratios': 'auto', 'model': None},
        image_fields=('original_image', 'reference_image'),
    ),
    'product_replacement': _spec(
        required=('original_image', 'reference_image'),
        optional={'prompt': None, 'model': None},
        image_fields=('original_image', 'reference_image'),
    ),
    'product_recoloring': _spec(
        required=('original_image', 'color'),
        optional={'model': None},
        image_fields=('original_image',),
    ),
    'partial_redraw': _spec(
        required=('original_image', 'prompt'),
        optional={'reference_image': None, 'model': None},
        image_fields=('original_image', 'reference_image'),
    ),
    'smart_expand': _spec(
        required=('original_image', 'direction', 'ratios'),
        optional={'model': None},
        image_fields=('original_image',),
    ),
    'translation': _spec(
        required=('original_image', 'source_language', 'target_language'),
        optional={'model': None},
        image_fields=('original_image',),
    ),
    'ai_upscale_2k': _spec(
        required=('original_image',),
        image_fields=('original_image',),
    ),
}

#: 支持 ``model`` 参数的任务类型（用于给出更准确的错误信息）。
MODEL_SELECTABLE_TYPES = frozenset(
    task_type for task_type, spec in TASK_SPECS.items() if 'model' in spec.optional
)


class ImageClient(AIClient):
    """IXSPY AI 图片生成 API 客户端。"""

    # 自由构图，多张原图。
    TYPE_CUSTOM_COMPOSITION_MULTI = 'custom_composition_multi'

    # 自由构图，单张原图。
    TYPE_CUSTOM_COMPOSITION = 'custom_composition'

    # 场景替换。
    TYPE_SCENE_REPLACEMENT = 'scene_replacement'

    # 商品替换。
    TYPE_PRODUCT_REPLACEMENT = 'product_replacement'

    # 商品换色。
    TYPE_PRODUCT_RECOLORING = 'product_recoloring'

    # 局部重绘。
    TYPE_PARTIAL_REDRAW = 'partial_redraw'

    # 智能延展。
    TYPE_SMART_EXPAND = 'smart_expand'

    # 图片翻译。
    TYPE_TRANSLATION = 'translation'

    # AI 超清 2K。
    TYPE_AI_UPSCALE_2K = 'ai_upscale_2k'

    MODEL_AUTO = 'auto'
    MODEL_GEMINI = 'gemini'
    MODEL_CHATGPT = 'chatgpt'

    #: 高清图就绪前的默认轮询间隔（秒）。
    DEFAULT_HD_POLL_INTERVAL: float = 5

    #: ``get_hd_image`` 可能出现的 URL 字段名（按优先级）。
    HD_IMAGE_FIELDS: Tuple[str, ...] = ('hd_image_url', 'hd_url', 'image_url')

    # ------------------------------------------------------------------ #
    # 参数校验与载荷构造
    # ------------------------------------------------------------------ #

    def _validate_model(self, task_type: str, model: Optional[str]) -> Optional[str]:
        """校验模型名，并拒绝不支持 ``model`` 的任务类型。"""
        if model is not None and task_type not in MODEL_SELECTABLE_TYPES:
            raise ValueError(f"任务类型 {task_type!r} 不支持 model 参数")
        return validate_model(model)

    def _validate_required(self, task_type: str, spec: TaskSpec, values: Dict[str, Any]) -> None:
        """校验必填字段，一次性汇总所有缺失项。"""
        missing: List[str] = []
        for name in sorted(spec.required):
            value = values.get(name)
            if name in spec.image_fields:
                try:
                    validate_required_image(value, name)
                except ValueError:
                    missing.append(name)
                continue
            if isinstance(value, str):
                if not value.strip():
                    missing.append(name)
            elif value is None:
                missing.append(name)
        if missing:
            raise ValueError(f"{task_type} 缺少必填参数: {', '.join(missing)}")

    def _normalize_image_fields(self, spec: TaskSpec, values: Dict[str, Any]) -> None:
        """把图片字段就地归一化为 CDN URL。"""
        for name in spec.image_fields:
            value = values.get(name)
            if value is None:
                continue
            values[name] = (
                self._prepare_image_list(value) if name in spec.list_inputs
                else self._prepare_single_image(value)
            )

    def _drop_unset_optional_fields(self, spec: TaskSpec, values: Dict[str, Any]) -> None:
        """清理未提供的可选参数与图片参数。

        规则：可选参数或图片参数取值为 ``None``、空字符串、空列表时不写入请求体
        —— 这样「未提供」与「提供了空值」的行为一致，也避免把
        ``"original_image": null`` 这类字段发给服务端。必填字段的缺失仍由
        :meth:`_validate_required` 在清理之后统一报错。
        """
        for name in set(spec.optional) | set(spec.image_fields):
            value = values.get(name)
            if value is None or isinstance(value, (str, list, tuple)) and not value:
                values.pop(name, None)

    def create_task(self, task_type: str, **kwargs: Any) -> int:
        """创建图片生成任务。

        参数:
            task_type: 图片任务类型，建议使用 ``TYPE_*`` 常量。
            **kwargs: 任务参数，取值见 :data:`TASK_SPECS`。图片字段接受本地路径、
                http(s) URL 或 Base64 数据；``model`` 可选 ``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。

        抛出:
            ValueError: 任务类型未知、缺少必填参数，或参数取值非法。
            FileNotFoundError: 图片路径不存在。
            APIError: API 调用失败。
        """
        if task_type not in TASK_SPECS:
            known = ', '.join(sorted(TASK_SPECS))
            raise ValueError(f"未知的图片任务类型: {task_type!r}。可选值: {known}")

        spec = TASK_SPECS[task_type]
        unknown = set(kwargs) - set(spec.known_fields)
        if unknown:
            raise ValueError(
                f"{task_type} 不支持参数: {', '.join(sorted(unknown))}；"
                f"可用参数: {', '.join(sorted(spec.known_fields))}"
            )

        self._drop_unset_optional_fields(spec, kwargs)
        self._validate_required(task_type, spec, kwargs)

        # 文本参数统一走共享校验，消除 `if prompt is None` 与 `if prompt:` 的差异。
        if kwargs.get('prompt') is not None:
            kwargs['prompt'] = validate_prompt(kwargs['prompt'])

        if 'model' in spec.optional:
            if kwargs.get('model') is None:
                kwargs.pop('model', None)
            else:
                kwargs['model'] = self._validate_model(task_type, kwargs['model'])

        for name, default in spec.optional.items():
            if name == 'model' or name in kwargs:
                continue
            if default is not None:
                kwargs[name] = default

        self._normalize_image_fields(spec, kwargs)

        endpoint = f"/v1/images/generations/{task_type}"
        data = self._request('POST', endpoint, json=kwargs)
        return self._require_int(data, 'task_id', f'创建图片任务 {task_type}')

    # ------------------------------------------------------------------ #
    # 各任务类型（薄包装，仅提供具名签名与文档）
    # ------------------------------------------------------------------ #

    def create_custom_composition_multi(self,
                                        original_images: Optional[List[ImageInput]] = None,
                                        prompt: Optional[str] = None,
                                        ratios: str = "auto",
                                        model: Optional[str] = None) -> int:
        """创建多图自由构图任务。

        参数:
            original_images: 可选原图列表，元素可为本地路径、URL 或 Base64 字符串。
            prompt: 图片生成描述，必填。
            ratios: 输出图片比例，默认 ``"auto"``。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        payload: Dict[str, Any] = {"prompt": prompt, "ratios": ratios, "model": model}
        if original_images:
            payload["original_image"] = list(original_images)
        return self.create_task(self.TYPE_CUSTOM_COMPOSITION_MULTI, **payload)

    def create_custom_composition(self,
                                  original_image: Optional[ImageInput] = None,
                                  prompt: Optional[str] = None,
                                  ratios: str = "auto",
                                  model: Optional[str] = None) -> int:
        """创建自由构图任务（``original_image`` 可省略，即纯文生图）。

        参数:
            original_image: 可选原图路径、URL 或 Base64 字符串。
            prompt: 图片生成描述，必填。
            ratios: 输出图片比例，默认 ``"auto"``。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_CUSTOM_COMPOSITION,
            original_image=original_image,
            prompt=prompt,
            ratios=ratios,
            model=model,
        )

    def create_scene_replacement(self,
                                 original_image: ImageInput,
                                 ratios: str = "auto",
                                 prompt: Optional[str] = None,
                                 reference_image: Optional[ImageInput] = None,
                                 model: Optional[str] = None) -> int:
        """创建场景替换任务。

        ``prompt`` 与 ``reference_image`` 至少提供一个。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            ratios: 输出图片比例，默认 ``"auto"``。
            prompt: 场景描述。
            reference_image: 场景参考图路径、URL 或 Base64 字符串。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        if prompt is None and reference_image is None:
            raise ValueError("prompt 和 reference_image 不能同时为空")
        return self.create_task(
            self.TYPE_SCENE_REPLACEMENT,
            original_image=original_image,
            ratios=ratios,
            prompt=prompt,
            reference_image=reference_image,
            model=model,
        )

    def create_product_replacement(self,
                                   original_image: ImageInput,
                                   reference_image: ImageInput,
                                   prompt: Optional[str] = None,
                                   model: Optional[str] = None) -> int:
        """创建商品替换任务。

        参数:
            original_image: 商品原图路径、URL 或 Base64 字符串。
            reference_image: 参考图路径、URL 或 Base64 字符串。
            prompt: 可选的商品描述。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_PRODUCT_REPLACEMENT,
            original_image=original_image,
            reference_image=reference_image,
            prompt=prompt,
            model=model,
        )

    def create_product_recoloring(self,
                                  original_image: ImageInput,
                                  color: str,
                                  model: Optional[str] = None) -> int:
        """创建商品换色任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            color: 目标颜色，使用带透明度的十六进制格式，例如 ``"#ff4500ff"``。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_PRODUCT_RECOLORING,
            original_image=original_image,
            color=color,
            model=model,
        )

    def create_partial_redraw(self,
                              original_image: ImageInput,
                              prompt: str,
                              reference_image: Optional[ImageInput] = None,
                              model: Optional[str] = None) -> int:
        """创建局部重绘任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            prompt: 描述如何重绘图片。
            reference_image: 可选参考图路径、URL 或 Base64 字符串。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_PARTIAL_REDRAW,
            original_image=original_image,
            prompt=prompt,
            reference_image=reference_image,
            model=model,
        )

    def create_smart_expand(self,
                            original_image: ImageInput,
                            direction: str,
                            ratios: str,
                            model: Optional[str] = None) -> int:
        """创建智能延展任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            direction: 延展方向，例如 ``"top_left"`` 或 ``"auto"``。
            ratios: 目标比例，例如 ``"1:1"`` 或 ``"16:9"``。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_SMART_EXPAND,
            original_image=original_image,
            direction=direction,
            ratios=ratios,
            model=model,
        )

    def create_translation(self,
                           original_image: ImageInput,
                           source_language: str,
                           target_language: str,
                           model: Optional[str] = None) -> int:
        """创建图片翻译任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            source_language: 原语言，例如 ``"auto"`` 或 ``"Chinese"``。
            target_language: 目标语言，例如 ``"English"``。
            model: 可选模型名：``auto``/``gemini``/``chatgpt``。

        返回:
            任务 ID。
        """
        return self.create_task(
            self.TYPE_TRANSLATION,
            original_image=original_image,
            source_language=source_language,
            target_language=target_language,
            model=model,
        )

    def create_ai_upscale_2k(self, original_image: ImageInput) -> int:
        """创建 AI 超清 2K 任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。

        返回:
            任务 ID。
        """
        return self.create_task(self.TYPE_AI_UPSCALE_2K, original_image=original_image)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get_task_status(self, task_id: int) -> ImageTaskResult:
        """查询单个图片任务的状态和结果数据。"""
        return self._request_as(ImageTaskResult, 'GET', f"/v1/images/generations/tasks/{task_id}")

    def get_hd_image(self, task_id: int) -> Optional[str]:
        """获取已完成图片任务的高清图 URL。

        高清图在标清图完成后再异步生成，因此本方法在尚未就绪时返回 ``None``，
        而不是抛 ``KeyError``。若需要等待其就绪，请使用 :meth:`wait_for_hd_image`。
        """
        data = self._request('GET', f"/v1/images/upscale/{task_id}")
        for field_name in self.HD_IMAGE_FIELDS:
            value = data.get(field_name)
            if isinstance(value, str) and value:
                return value
        return None

    def wait_for_hd_image(self,
                          task_id: int,
                          poll_interval: float = DEFAULT_HD_POLL_INTERVAL,
                          timeout: Optional[Union[int, float]] = DEFAULT_WAIT_TIMEOUT) -> str:
        """轮询直到高清图就绪。

        取代「``time.sleep(30)`` 然后祈祷」的用法。

        参数:
            task_id: 已完成任务的 ID。
            poll_interval: 轮询间隔（秒），默认 5。
            timeout: **总等待上限**（秒），默认 180；``None``/``0`` 表示不限制。

        返回:
            高清图 URL。

        抛出:
            TaskFailedError: 查询过程中任务状态变为 ``error``。
            TaskTimeoutError: 超时仍不可用。
        """
        def _fetch() -> Dict[str, Any]:
            url = self.get_hd_image(task_id)
            if url:
                return {'status': 'completed', 'url': url}
            status = self.get_task_status(task_id)
            if status.get('status') == TASK_STATUS_ERROR:
                raise TaskFailedError(
                    message=f"图片任务 {task_id} 执行失败: {status.get('error') or '服务端未返回失败原因'}",
                    task_id=task_id,
                )
            return {'status': 'processing'}

        result = wait_for_task(
            _fetch, task_id, poll_interval=poll_interval, timeout=timeout, task_label="高清图任务",
        )
        return result['url']

    def list_tasks(self,
                   page: int = 1,
                   page_size: int = 20,
                   status: Optional[str] = None,
                   task_type: Optional[str] = None) -> TaskListPage:
        """查询图片任务列表。

        参数:
            page: 页码，从 1 开始。
            page_size: 每页数量，最大 100。
            status: 状态过滤；``None`` 或 ``"all"`` 表示不按状态过滤。
            task_type: 任务类型过滤，取值同 :data:`TASK_SPECS` 的键。

        返回:
            含 ``total`` 与任务列表的分页数据。
        """
        validate_pagination(page, page_size)
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        if task_type:
            if task_type not in TASK_SPECS:
                raise ValueError(f"未知的图片任务类型: {task_type!r}")
            params["type"] = task_type
        return self._request_as(TaskListPage, 'GET', '/v1/images/tasks-list', params=params)

    # ------------------------------------------------------------------ #
    # 等待
    # ------------------------------------------------------------------ #

    def wait_for_completion(self,
                            task_id: int,
                            poll_interval: float = 3,
                            timeout: Optional[Union[int, float]] = DEFAULT_WAIT_TIMEOUT) -> ImageTaskResult:
        """轮询图片任务，直到完成、失败或超时。

        参数:
            task_id: 图片任务 ID。
            poll_interval: 两次查询之间的间隔（秒），支持小数。
            timeout: **总等待上限**（秒），默认 180。``None`` 或 ``0`` 表示不限制。
                注意与 ``AIClient`` 的单次请求超时区分。

        返回:
            已完成任务的数据，通常包含 ``sd_image_url``。

        抛出:
            TaskFailedError: 任务状态为 ``error``。
            TaskTimeoutError: 超过 ``timeout`` 仍未完成（任务可能仍在服务端运行）。
            APIError: 返回了未知状态或请求失败。
        """
        return wait_for_task(
            lambda: self.get_task_status(task_id),
            task_id,
            poll_interval=poll_interval,
            timeout=timeout,
            task_label="图片任务",
        )

    def generate(self,
                 task_type: str,
                 wait: bool = True,
                 poll_interval: float = 3,
                 timeout: Optional[Union[int, float]] = DEFAULT_WAIT_TIMEOUT,
                 **params: Any) -> Union[int, ImageTaskResult]:
        """创建图片任务，并可选地等待其完成。

        这是通用便捷接口；为了让代码更清晰，推荐优先使用具体任务创建方法配合
        :meth:`wait_for_completion`。

        参数:
            task_type: 图片任务类型，取值同 :data:`TASK_SPECS`。
            wait: 是否等待任务完成。``False`` 时直接返回任务 ID。
            poll_interval: 轮询间隔（秒），仅 ``wait=True`` 时生效。
            timeout: **总等待上限**（秒），默认 180，与 :meth:`wait_for_completion`
                保持一致。``None`` 或 ``0`` 表示无限等待。
            **params: 透传给 :meth:`create_task` 的任务参数。

        返回:
            ``wait=False`` 时返回任务 ID（``int``）；否则返回完成后的任务数据，
            其中额外包含 ``task_id`` 字段。
        """
        task_id = self.create_task(task_type, **params)
        if not wait:
            return task_id
        result = self.wait_for_completion(task_id, poll_interval=poll_interval, timeout=timeout)
        result['task_id'] = task_id
        return result


__all__ = ["ImageClient", "TaskSpec", "TASK_SPECS", "MODEL_SELECTABLE_TYPES"]
