from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ..config import SpotExtractionConfig
from ..types import Point2D, SpotPair


@dataclass
class SpotQuality:
    """单个光斑提取的质量指标。

    - max_intensity:    高斯模糊后的像素峰值（0-255）。
      真光斑通常 ≥ 150；空白 / 无光斑图像多数 ≤ 60。
    - peak_to_bg_ratio: 峰值 / 全图中位数。真光斑数十到上百；空白图 ~1-3。
    - mask_pixel_count: 阈值内像素数。真光斑典型 20-400；空白图散乱分布可能远超。
    - compactness:      mask 像素到重心的平均距离 / sqrt(mask_pixel_count)。
      越小越集中；真光斑 ≈ 1-1.5；散乱噪声更大。
    - confidence:       综合 [0, 1] 置信度。UI 用这个判断"是否有效"。
    """
    max_intensity: float
    peak_to_bg_ratio: float
    mask_pixel_count: int
    compactness: float
    confidence: float


@dataclass
class SpotExtractionResult:
    """extract_spots 的完整返回：像素坐标 + 每个相机的质量指标。"""
    spots: SpotPair
    front_quality: SpotQuality
    rear_quality: SpotQuality

    # 兼容旧调用方式：允许 `spots = extract_spots(...)`（此时 spots 是 SpotPair）
    # 通过让 SpotExtractionResult.__getattr__ 代理到 self.spots 实现。
    def __getattr__(self, name: str):
        if name in ("front", "rear"):
            return getattr(self.spots, name)
        raise AttributeError(name)


def extract_spots(
    front_image: np.ndarray,
    rear_image: np.ndarray,
    config: SpotExtractionConfig,
) -> SpotExtractionResult:
    """从前后相机图像中提取光斑中心像素坐标 + 质量指标。

    返回 SpotExtractionResult；.spots 兼容旧 SpotPair，另有 front_quality / rear_quality。
    """
    (fu, fv), fq = _extract_single(front_image, config)
    (ru, rv), rq = _extract_single(rear_image, config)
    return SpotExtractionResult(
        spots=SpotPair(front=Point2D(u=fu, v=fv), rear=Point2D(u=ru, v=rv)),
        front_quality=fq,
        rear_quality=rq,
    )


def _extract_single(
    image: np.ndarray, config: SpotExtractionConfig
) -> tuple[tuple[float, float], SpotQuality]:
    """阈值加权重心法提取光斑中心，返回 (u, v) 与质量指标。"""
    blurred = cv2.GaussianBlur(
        image, (config.gaussian_kernel, config.gaussian_kernel), config.gaussian_sigma
    )

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

    quality = _compute_quality(blurred, mask, u, v, max_val)
    return (u, v), quality


def _compute_quality(
    blurred: np.ndarray,
    mask: np.ndarray,
    u: float,
    v: float,
    max_val: float,
) -> SpotQuality:
    """基于 4 个指标合成 [0, 1] 置信度。

    关键指标（在真实数据上验证）：
    - background = median(blurred)：暗背景光斑 ~10-20；饱和眩光图 ~90+
    - peak_to_bg_ratio = max / background：光斑图 >15；饱和图 ~2-3
    - mask_pixel_count：光斑图数十~数百；饱和图数百万
    - compactness：数值参考
    """
    background = float(np.median(blurred))
    peak_to_bg = max_val / max(background, 1e-6)

    ys, xs = np.where(mask)
    count = int(len(xs))

    if count > 1:
        distances = np.hypot(xs - u, ys - v)
        avg_distance = float(np.mean(distances))
        compactness = avg_distance / max(np.sqrt(count), 1.0)
    else:
        compactness = 0.0

    # 图像总像素数（用来把 mask_pixel_count 归一化）
    total_pixels = int(blurred.size)
    mask_ratio = count / max(total_pixels, 1)

    # 各子指标归一到 [0, 1]：
    # 1) 背景暗度：median < 30 是好；> 80 说明背景太亮（无有效光斑）
    dark_bg_score = _sigmoid((30.0 - background) / 8.0)

    # 2) 峰值对比：peak/bg > 15 是明显光斑；< 5 基本没光斑
    contrast_score = _sigmoid((peak_to_bg - 8.0) / 3.0)

    # 3) mask 占比：真光斑 mask 占全图 < 1%；饱和图可能 20%+
    mask_ratio_score = _sigmoid((0.01 - mask_ratio) / 0.005)

    # 4) 亮度绝对值：真光斑一般 >= 150；补充加权
    intensity_score = _sigmoid((max_val - 100.0) / 30.0)

    confidence = (
        0.35 * dark_bg_score
        + 0.30 * contrast_score
        + 0.25 * mask_ratio_score
        + 0.10 * intensity_score
    )
    confidence = float(np.clip(confidence, 0.0, 1.0))

    return SpotQuality(
        max_intensity=max_val,
        peak_to_bg_ratio=float(peak_to_bg),
        mask_pixel_count=count,
        compactness=float(compactness),
        confidence=confidence,
    )


def _sigmoid(x: float) -> float:
    """标准 sigmoid，输入 x=0 时 0.5。"""
    if x > 30:
        return 1.0
    if x < -30:
        return 0.0
    return float(1.0 / (1.0 + np.exp(-x)))
