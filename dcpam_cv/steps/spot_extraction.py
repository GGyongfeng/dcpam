from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..config import SpotExtractionConfig
from ..types import Point2D, SpotPair


# 提取端硬门槛（在真实数据上校准，见 _compute_quality 文档）：
#   INTENSITY_FLOOR    = 30：真光斑 peak=255，全黑噪声 peak=8-11；30 是安全下限
#   SATURATION_CEIL    = 15%：0701 高曝光批次真光斑 mask 5-12%，饱和取景框 ≥ 30%；
#                             15% 仍能干净分离两类（旧值 5% 会误杀高曝光真光斑）
#   LOCAL_WINDOW_HALF  = 30 px：约覆盖真光斑主体（含 halo）而不至于卷入远处散乱噪声
INTENSITY_FLOOR = 30.0
SATURATION_CEIL = 0.15
LOCAL_WINDOW_HALF = 30


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
    """局部窗口加权重心提取光斑中心，返回 (u, v) 与质量指标。

    步骤：
    1. 高斯模糊。
    2. cv2.minMaxLoc 找全局峰值位置——这是唯一物理上有意义的候选中心。
    3. 硬门槛（防止在垃圾图上返回伪坐标）：
       - max_val < INTENSITY_FLOOR：几乎全黑，只有传感器噪声，抛异常。
       - 全局 mask 占比 > SATURATION_CEIL：大面积饱和（拍到取景框而非圆版），抛异常。
    4. 只在峰值 ±LOCAL_WINDOW_HALF 窗口内做加权重心。局部窗口天然过滤远处的散乱噪声，
       避免旧实现"全局 mask 内加权重心 → 落在图像中心"的伪坐标。
    5. quality 仍用全局 mask 计算，用来在 UI 层再兜一层"无效采样"的判断。
    """
    blurred = cv2.GaussianBlur(
        image, (config.gaussian_kernel, config.gaussian_kernel), config.gaussian_sigma
    )

    min_val, max_val_raw, _, peak_loc = cv2.minMaxLoc(blurred)
    del min_val
    max_val = float(max_val_raw)
    peak_x, peak_y = int(peak_loc[0]), int(peak_loc[1])

    threshold = max_val * config.centroid_threshold
    global_mask = blurred > threshold
    total_pixels = int(blurred.size)
    global_mask_count = int(global_mask.sum())
    global_mask_ratio = global_mask_count / max(total_pixels, 1)

    # 硬门槛 1：峰值太低 = 传感器噪声，不存在有效光斑
    if max_val < INTENSITY_FLOOR:
        raise ValueError(
            f"光斑提取失败：峰值 {max_val:.1f} 低于门槛 {INTENSITY_FLOOR:.0f}，"
            f"图像无有效信号"
        )

    # 硬门槛 2：饱和区域占比过大 = 拍到取景框 / 大面积眩光，不是光斑
    if global_mask_ratio > SATURATION_CEIL:
        raise ValueError(
            f"光斑提取失败：饱和区域占比 {global_mask_ratio:.1%} 超过 "
            f"{SATURATION_CEIL:.0%}，视野内不是圆版"
        )

    # 局部窗口重心
    height, width = blurred.shape[:2]
    y0 = max(0, peak_y - LOCAL_WINDOW_HALF)
    y1 = min(height, peak_y + LOCAL_WINDOW_HALF + 1)
    x0 = max(0, peak_x - LOCAL_WINDOW_HALF)
    x1 = min(width, peak_x + LOCAL_WINDOW_HALF + 1)

    window = blurred[y0:y1, x0:x1]
    window_mask = window > threshold
    if not np.any(window_mask):
        raise ValueError("光斑提取失败：峰值周围窗口内无有效像素")

    ys_local, xs_local = np.where(window_mask)
    weights = window[ys_local, xs_local].astype(np.float64)
    total = weights.sum()
    u = float(((xs_local + x0) * weights).sum() / total)
    v = float(((ys_local + y0) * weights).sum() / total)

    quality = _compute_quality(blurred, global_mask, u, v, max_val)
    return (u, v), quality


def _compute_quality(
    blurred: np.ndarray,
    mask: np.ndarray,
    u: float,
    v: float,
    max_val: float,
) -> SpotQuality:
    """基于 4 个指标合成 [0, 1] 置信度。

    在真实数据上校准（negative n=79, positive n=192）；两类典型区间：
    - 真光斑：peak=255, pk/bg=10-25, mask 占比 0.02%-3%, compactness=0.4-1
    - 全黑无信号：peak=8-11（噪声）, pk/bg 看似高但没有意义, compactness=40-80
    - 饱和取景框：peak≈250, pk/bg=5-6, mask 占比 5-30%, compactness=0.4

    用 min(4 子分) 而非加权和：任意一维不合格即拉低整体，避免"三高一低"混过。
    compactness 必须纳入公式，否则无法排除全黑图上噪声形成的散乱伪光斑。
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

    total_pixels = int(blurred.size)
    mask_ratio = count / max(total_pixels, 1)

    # 1) 绝对亮度：真光斑 peak ≥ 150；噪声峰 ~10。中心 80，宽度 20。
    intensity_score = _sigmoid((max_val - 80.0) / 20.0)

    # 2) 峰值对比：真光斑 pk/bg ≥ 10；饱和取景框 ~5。中心 8，宽度 2。
    contrast_score = _sigmoid((peak_to_bg - 8.0) / 2.0)

    # 3) mask 占比：真光斑 ≤ 3%（含大halo）；饱和取景框 ≥ 5%。中心 4%，宽度 1.5%。
    mask_ratio_score = _sigmoid((0.04 - mask_ratio) / 0.015)

    # 4) 紧凑度：真光斑 ≤ 1.5；噪声散点几十。中心 3，宽度 1.5。
    compactness_score = _sigmoid((3.0 - compactness) / 1.5)

    # min = 最短板，任意一维差就整体差
    confidence = float(min(
        intensity_score, contrast_score, mask_ratio_score, compactness_score
    ))
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
