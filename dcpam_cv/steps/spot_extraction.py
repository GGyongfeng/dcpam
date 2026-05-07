from __future__ import annotations

import numpy as np

from ..center import improved_circle_fit
from ..config import SpotExtractionConfig
from ..types import Point2D, SpotPair


def extract_spots(
    front_image: np.ndarray,
    rear_image: np.ndarray,
    config: SpotExtractionConfig,
) -> SpotPair:
    """从前后相机图像中提取光斑中心像素坐标。"""
    fu, fv = _extract_single(front_image)
    ru, rv = _extract_single(rear_image)
    return SpotPair(front=Point2D(u=fu, v=fv), rear=Point2D(u=ru, v=rv))


def _extract_single(image: np.ndarray) -> tuple[float, float]:
    """单张图像光斑提取，返回 (u, v)。"""
    x, y, _ = improved_circle_fit(image)
    if x is None:
        raise ValueError("光斑提取失败：未检测到有效光斑")
    return float(x), float(y)
