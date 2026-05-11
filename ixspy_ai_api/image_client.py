"""
IXSPY AI 图片生成客户端。

ImageClient 提供图片生成任务创建、任务轮询、高清图获取和任务列表查询能力。
"""

import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient, APIError


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

    SUPPORTED_MODELS = {MODEL_AUTO, MODEL_GEMINI, MODEL_CHATGPT}
    UNSUPPORTED_MODELS_BY_TYPE = {
        TYPE_AI_UPSCALE_2K: {MODEL_CHATGPT},
    }

    def _validate_model(self, task_type: str, model: Optional[str]) -> None:
        if model is None:
            return
        if model not in self.SUPPORTED_MODELS:
            raise ValueError("model 仅支持 'auto'、'gemini' 或 'chatgpt'")
        if model in self.UNSUPPORTED_MODELS_BY_TYPE.get(task_type, set()):
            raise ValueError(f"{task_type} 不支持 model={model}")

    def create_task(self, task_type: str, **kwargs) -> int:
        """
        创建图片生成任务。

        参数:
            task_type: 图片任务类型，建议使用类中的 TYPE_* 常量。
            **kwargs: 任务参数，例如 `original_image`、`prompt`、
                `reference_image`、`ratios` 或 `model`。

        返回:
            任务 ID。
        """
        model = kwargs.get('model')
        self._validate_model(task_type, model)
        if model is None:
            kwargs.pop('model', None)

        if 'original_image' in kwargs:
            kwargs['original_image'] = self._prepare_images(kwargs['original_image'])
        if 'reference_image' in kwargs:
            kwargs['reference_image'] = self._prepare_single_image(kwargs['reference_image'])

        endpoint = f"/v1/images/generations/{task_type}"
        data = self._request('POST', endpoint, json=kwargs)
        return int(data['task_id'])

    def create_custom_composition_multi(self,
                                        original_images: List[Union[str, Path]],
                                        prompt: str,
                                        ratios: str = "auto",
                                        model: Optional[str] = None) -> int:
        """
        创建多图自由构图任务。

        参数:
            original_images: 原图列表，元素可以是本地路径、URL 或 Base64 字符串。
            prompt: 图片生成描述。
            ratios: 输出图片比例，默认 "auto"。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_images, "prompt": prompt, "ratios": ratios}
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_CUSTOM_COMPOSITION_MULTI, **payload)

    def create_custom_composition(self,
                                  original_image: Union[str, Path],
                                  prompt: str,
                                  ratios: str = "auto",
                                  model: Optional[str] = None) -> int:
        """
        创建自由构图任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            prompt: 图片生成描述。
            ratios: 输出图片比例，默认 "auto"。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_image, "prompt": prompt, "ratios": ratios}
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_CUSTOM_COMPOSITION, **payload)

    def create_scene_replacement(self,
                                 original_image: Union[str, Path],
                                 ratios: str = "auto",
                                 prompt: Optional[str] = None,
                                 reference_image: Optional[Union[str, Path]] = None,
                                 model: Optional[str] = None) -> int:
        """
        创建场景替换任务。

        `prompt` 和 `reference_image` 至少需要提供一个。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            ratios: 输出图片比例，默认 "auto"。
            prompt: 场景描述。
            reference_image: 场景参考图路径、URL 或 Base64 字符串。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        if (prompt is None) and (reference_image is None):
            raise ValueError("prompt 和 reference_image 不能同时为空")

        payload = {"original_image": original_image, "ratios": ratios}
        if prompt:
            payload["prompt"] = prompt
        if reference_image:
            payload["reference_image"] = reference_image
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_SCENE_REPLACEMENT, **payload)

    def create_product_replacement(self,
                                   original_image: Union[str, Path],
                                   reference_image: Union[str, Path],
                                   prompt: Optional[str] = None,
                                   model: Optional[str] = None) -> int:
        """
        创建商品替换任务。

        参数:
            original_image: 商品原图路径、URL 或 Base64 字符串。
            reference_image: 参考图路径、URL 或 Base64 字符串。
            prompt: 可选的商品描述。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_image, "reference_image": reference_image}
        if prompt:
            payload["prompt"] = prompt
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_PRODUCT_REPLACEMENT, **payload)

    def create_product_recoloring(self,
                                  original_image: Union[str, Path],
                                  color: str,
                                  model: Optional[str] = None) -> int:
        """
        创建商品换色任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            color: 目标颜色，使用带透明度的十六进制格式，例如 "#ff4500ff"。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_image, "color": color}
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_PRODUCT_RECOLORING, **payload)

    def create_partial_redraw(self,
                              original_image: Union[str, Path],
                              prompt: str,
                              reference_image: Optional[Union[str, Path]] = None,
                              model: Optional[str] = None) -> int:
        """
        创建局部重绘任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            prompt: 描述如何重绘图片。
            reference_image: 可选参考图路径、URL 或 Base64 字符串。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_image, "prompt": prompt}
        if reference_image:
            payload["reference_image"] = reference_image
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_PARTIAL_REDRAW, **payload)

    def create_smart_expand(self,
                            original_image: Union[str, Path],
                            direction: str,
                            ratios: str,
                            model: Optional[str] = None) -> int:
        """
        创建智能延展任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            direction: 延展方向，例如 "top_left" 或 "auto"。
            ratios: 目标比例，例如 "1:1" 或 "16:9"。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {"original_image": original_image, "direction": direction, "ratios": ratios}
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_SMART_EXPAND, **payload)

    def create_translation(self,
                           original_image: Union[str, Path],
                           source_language: str,
                           target_language: str,
                           model: Optional[str] = None) -> int:
        """
        创建图片翻译任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。
            source_language: 原语言，例如 "auto" 或 "Chinese"。
            target_language: 目标语言，例如 "English"。
            model: 可选模型名："auto"、"gemini" 或 "chatgpt"。

        返回:
            任务 ID。
        """
        payload = {
            "original_image": original_image,
            "source_language": source_language,
            "target_language": target_language,
        }
        if model is not None:
            payload["model"] = model
        return self.create_task(ImageClient.TYPE_TRANSLATION, **payload)

    def create_ai_upscale_2k(self, original_image: Union[str, Path]) -> int:
        """
        创建 AI 超清 2K 任务。

        参数:
            original_image: 原图路径、URL 或 Base64 字符串。

        返回:
            任务 ID。
        """
        return self.create_task(ImageClient.TYPE_AI_UPSCALE_2K, original_image=original_image)

    def get_task_status(self, task_id: int) -> Dict[str, Any]:
        """查询单个图片任务的状态和结果数据。"""
        endpoint = f"/v1/images/generations/tasks/{task_id}"
        return self._request('GET', endpoint)

    def get_hd_image(self, task_id: int) -> str:
        """获取已完成图片任务的高清图 URL。"""
        endpoint = f"/v1/images/upscale/{task_id}"
        data = self._request('GET', endpoint)
        return data['hd_image_url']

    def list_tasks(self,
                   page: int = 1,
                   page_size: int = 20,
                   status: Optional[str] = None,
                   task_type: Optional[str] = None) -> Dict[str, Any]:
        """查询图片任务列表，支持分页、状态和任务类型过滤。"""
        params = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        if task_type:
            params["type"] = task_type
        return self._request('GET', '/v1/images/tasks-list', params=params)

    def wait_for_completion(self, task_id: int, poll_interval: int = 3, timeout: int = 180) -> Dict[str, Any]:
        """
        轮询图片任务，直到任务完成、失败或超时。

        参数:
            task_id: 图片任务 ID。
            poll_interval: 每次查询状态之间的间隔，单位为秒。
            timeout: 最大等待时间，单位为秒。传入 0 或 None 表示不限制。

        返回:
            已完成任务的数据。

        抛出:
            APIError: 任务失败、超时或返回未知状态时抛出。
        """
        start_time = time.time()
        while True:
            data = self.get_task_status(task_id)
            status = data.get('status')
            if status == 'completed':
                return data
            elif status == 'error':
                raise APIError(1000, f"任务 {task_id} 执行失败")
            elif status in ('queued', 'processing'):
                if timeout and (time.time() - start_time) > timeout:
                    raise APIError(1001, f"任务 {task_id} 在 {timeout}s 后超时")
                time.sleep(poll_interval)
            else:
                raise APIError(1002, f"未知任务状态: {status}")

    def generate(self, task_type: str, wait: bool = True,
                 poll_interval: int = 3, timeout: Optional[int] = None,
                 **params) -> Union[str, Dict[str, Any]]:
        """
        创建图片任务，并可选择等待任务完成。

        这是通用便捷接口。为了让代码更清晰，推荐优先使用具体任务创建方法
        加 `wait_for_completion()`。
        """
        task_id = self.create_task(task_type, **params)
        if not wait:
            return task_id
        result = self.wait_for_completion(task_id, poll_interval, timeout)
        result['task_id'] = task_id
        return result
