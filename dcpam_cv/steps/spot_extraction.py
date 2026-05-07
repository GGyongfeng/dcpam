from __future__ import annotations

import cv2
import numpy as np

from ..config import SpotExtractionConfig
from ..types import Point2D, SpotPair


def extract_spots(
    front_image: np.ndarray,
    rear_image: np.ndarray,
    config: SpotExtractionConfig,
) -> SpotPair:
    """从前后相机图像中提取光斑中心像素坐标。"""
    fu, fv = _extract_single(front_image, config)
    ru, rv = _extract_single(rear_image, config)
    return SpotPair(front=Point2D(u=fu, v=fv), rear=Point2D(u=ru, v=rv))


def _extract_single(image: np.ndarray, config: SpotExtractionConfig) -> tuple[float, float]:
    """阈值加权重心法提取光斑中心，返回 (u, v)。"""
    blurred = cv2.GaussianBlur(image, (config.gaussian_kernel, config.gaussian_kernel), config.gaussian_sigma)

    max_val = float(np.max(blurred))
    threshold = max_val * config.centroid_threshold
    mask = blurred > threshold

    if not np.any(mask):
        raise ValueError("光斑提取失败：未检测到有效光斑")

    ys, xs = np.where(mask)
    weights = blurred[ys, xs].astype(np.float64)
    total = weights.sum()

    u = float((xs * weights).sum() / total)
    v = float((ys * weights).sum() / total)
    return u, v
