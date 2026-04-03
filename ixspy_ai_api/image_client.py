"""
AI 图像/视频生成 Python SDK
- 基类: AIClient (通用请求、认证、图片上传)
- 图片客户端: ImageClient (9种作图、状态轮询、高清图、任务列表)
- 视频客户端: VideoClient (视频生成、状态轮询、任务列表)
"""

import os
import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from ixspy_ai_api import AIClient, APIError

class ImageClient(AIClient):
    """AI 图像生成客户端"""

    # 自由构图-多图
    TYPE_CUSTOM_COMPOSITION_MULTI = 'custom_composition_multi'

    # 自由构图
    TYPE_CUSTOM_COMPOSITION = 'custom_composition'

    # 场景替换
    TYPE_SCENE_REPLACEMENT = 'scene_replacement'

    # 商品替换
    TYPE_PRODUCT_REPLACEMENT = 'product_replacement'

    # 商品换色
    TYPE_PRODUCT_RECOLORING = 'product_recoloring'

    # 局部重绘
    TYPE_PARTIAL_REDRAW = 'partial_redraw'

    # 智能延展
    TYPE_SMART_EXPAND = 'smart_expand'

    # 图片翻译
    TYPE_TRANSLATION = 'translation'

    # AI超清-2K
    TYPE_AI_UPSCALE_2K = 'ai_upscale_2k'

    # ---------- 发起作图任务（通用 + 便捷方法） ----------
    def create_task(self, task_type: str, **kwargs) -> int:
        """
        通用作图方法

        Args:
            task_type: 作图类型，可选值见文档
            **kwargs: 特定参数，需包含 original_image 及其他类型所需参数

        Returns:
            task_id
        """
        # 预处理 original_image
        if 'original_image' in kwargs:
            kwargs['original_image'] = self._prepare_images(kwargs['original_image'])
        # 预处理 reference_image（某些类型需要）
        if 'reference_image' in kwargs:
            kwargs['reference_image'] = self._prepare_single_image(kwargs['reference_image'])

        endpoint = f"/v1/images/generations/{task_type}"
        data = self._request('POST', endpoint, json=kwargs)
        return int(data['task_id'])

    # ----- 自由构图-多图 -----
    def create_custom_composition_multi(self,
                                        original_images: List[Union[str, Path]],
                                        prompt: str,
                                        ratios: str = "auto") -> int:
        """
        自由构图-多图（支持最多5张图片）

        :param original_images: 原图列表（文件路径、URL或Base64），最多5张
        :param prompt: 画面描述
        :param ratios: 图片比例，默认 "auto"
        :return: 任务ID
        """
        return self.create_task(
            ImageClient.TYPE_CUSTOM_COMPOSITION_MULTI,
            original_image=original_images,
            prompt=prompt,
            ratios=ratios
        )

    # ----- 自由构图 -----
    def create_custom_composition(self,
                                  original_image: Union[str, Path],
                                  prompt: str,
                                  ratios: str = "auto") -> int:
        """
        自由构图

        :param original_image: 原图（文件路径、URL或Base64）
        :param prompt: 画面描述
        :param ratios: 图片比例，默认 "auto"
        :return: 任务ID
        """
        return self.create_task(
            ImageClient.TYPE_CUSTOM_COMPOSITION,
            original_image=original_image,
            prompt=prompt,
            ratios=ratios
        )

    # ----- 场景替换 -----
    def create_scene_replacement(self,
                                 original_image: Union[str, Path],
                                 ratios: str = "auto",
                                 prompt: Optional[str] = None,
                                 reference_image: Optional[Union[str, Path]] = None) -> int:
        """
        场景替换（prompt 和 reference_image 至少需要有一個有值）

        :param original_image: 原图（文件路径、URL或Base64）
        :param prompt: 场景描述文本
        :param reference_image: 场景参考图（文件路径、URL或Base64）
        :param ratios: 图片比例，默认 "auto"
        :return: 任务ID
        """
        if (prompt is None)  and (reference_image is None):
            raise ValueError("prompt 和 reference_image 不能同時爲空")
        
        payload = {"original_image": original_image, "ratios": ratios}
        if prompt:
            payload["prompt"] = prompt
        if reference_image:
            payload["reference_image"] = reference_image
        return self.create_task(ImageClient.TYPE_SCENE_REPLACEMENT, **payload)

    # ----- 商品替换 -----
    def create_product_replacement(self,
                                   original_image: Union[str, Path],
                                   reference_image: Union[str, Path],
                                   prompt: Optional[str] = None) -> int:
        """
        商品替换

        :param original_image: 原图（文件路径、URL或Base64）
        :param reference_image: 参考图，以此为背景（文件路径、URL或Base64）
        :param prompt: 商品描述（可选）
        :return: 任务ID
        """
        payload = {"original_image": original_image, "reference_image": reference_image}
        if prompt:
            payload["prompt"] = prompt
        return self.create_task(ImageClient.TYPE_PRODUCT_REPLACEMENT, **payload)

    # ----- 商品换色 -----
    def create_product_recoloring(self,
                                  original_image: Union[str, Path],
                                  color: str) -> int:
        """
        商品换色

        :param original_image: 原图（文件路径、URL或Base64）
        :param color: 目标颜色，十六进制格式（含透明度），如 "#ff4500ff"
        :return: 任务ID
        """
        return self.create_task(
            "product_recoloring",
            original_image=original_image,
            color=color
        )

    # ----- 局部重绘 -----
    def create_partial_redraw(self,
                              original_image: Union[str, Path],
                              prompt: str,
                              reference_image: Optional[Union[str, Path]] = None) -> int:
        """
        局部重绘

        :param original_image: 原图（文件路径、URL或Base64）
        :param prompt: 描述如何重绘
        :param reference_image: 参考图（可选，文件路径、URL或Base64）
        :return: 任务ID
        """
        payload = {"original_image": original_image, "prompt": prompt}
        if reference_image:
            payload["reference_image"] = reference_image
        return self.create_task(ImageClient.TYPE_PRODUCT_RECOLORING, **payload)

    # ----- 智能延展 -----
    def create_smart_expand(self,
                            original_image: Union[str, Path],
                            direction: str,
                            ratios: str) -> int:
        """
        智能延展

        :param original_image: 原图（文件路径、URL或Base64）
        :param direction: 延展方向，如 "top_left", "auto" 等
        :param ratios: 目标比例，如 "1:1", "16:9"
        :return: 任务ID
        """
        return self.create_task(
            ImageClient.TYPE_SMART_EXPAND,
            original_image=original_image,
            direction=direction,
            ratios=ratios
        )

    # ----- 图片翻译 -----
    def create_translation(self,
                           original_image: Union[str, Path],
                           source_language: str,
                           target_language: str) -> int:
        """
        图片翻译

        :param original_image: 原图（文件路径、URL或Base64）
        :param source_language: 原语言，如 "auto", "Chinese"
        :param target_language: 目标语言，如 "English"
        :return: 任务ID
        """
        return self.create_task(
            ImageClient.TYPE_TRANSLATION,
            original_image=original_image,
            source_language=source_language,
            target_language=target_language
        )

    # ----- AI 超清-2K -----
    def create_ai_upscale_2k(self, original_image: Union[str, Path]) -> int:
        """
        AI超清-2K（仅需原图）

        :param original_image: 原图（文件路径、URL或Base64）
        :return: 任务ID
        """
        return self.create_task(ImageClient.TYPE_AI_UPSCALE_2K, original_image=original_image)

    # ---------- 查询作图结果 ----------
    def get_task_status(self, task_id: int) -> Dict[str, Any]:
        """查询单个作图任务状态"""
        endpoint = f"/v1/images/generations/tasks/{task_id}"
        return self._request('GET', endpoint)

    # ---------- 获取高清图片 ----------
    def get_hd_image(self, task_id: int) -> str:
        """获取作图任务的高清图片 URL（任务需已完成）"""
        endpoint = f"/v1/images/upscale/{task_id}"
        data = self._request('GET', endpoint)
        return data['hd_image_url']

    # ---------- 获取作图任务列表 ----------
    def list_tasks(self,
                   page: int = 1,
                   page_size: int = 20,
                   status: Optional[str] = None,
                   task_type: Optional[str] = None) -> Dict[str, Any]:
        """获取作图任务列表，支持分页、状态和类型过滤"""
        params = {"page": page, "page_size": page_size}
        if status and status != 'all':
            params["status"] = status
        if task_type:
            params["type"] = task_type
        return self._request('GET', '/v1/images/tasks-list', params=params)

    # ---------- 高级封装 ----------

    # ---------- 轮询等待作图任务完成 ----------
    def wait_for_completion(self, task_id: int, poll_interval: int = 3, timeout: int = 180) -> Dict[str, Any]:
        start_time = time.time()
        while True:
            data = self.get_task_status(task_id)
            status = data.get('status')
            if status == 'completed':
                return data
            elif status == 'error':
                raise APIError(1000, f"Task {task_id} failed")
            elif status in ('queued', 'processing'):
                if timeout and (time.time() - start_time) > timeout:
                    raise APIError(1001, f"Task {task_id} timeout after {timeout}s")
                time.sleep(poll_interval)
            else:
                raise APIError(1002, f"Unknown status: {status}")
        '''
        # 暫時註釋掉
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise APIError(-1, f"任务 {task_id} 轮询超时", 0)

            data = self.get_task_status(task_id)
            status = data.get('status')
            if status == 'completed':
                return data
            if status == 'error':
                raise APIError(-1, f"任务 {task_id} 执行失败", 0)
            time.sleep(poll_interval)
        '''

    # ---------- 发起任务并等待完成 ----------
    def generate(self, task_type: str, wait: bool = True,
                 poll_interval: int = 3, timeout: Optional[int] = None,
                 **params) -> Union[str, Dict[str, Any]]:
        """
        一键生成：发起任务并等待完成
        注意：推荐使用专用方法 + wait_for_completion，此方法为通用便捷接口
        """
        task_id = self.create_task(task_type, **params)
        if not wait:
            return task_id
        result = self.wait_for_completion(task_id, poll_interval, timeout)
        result['task_id'] = task_id
        return result
