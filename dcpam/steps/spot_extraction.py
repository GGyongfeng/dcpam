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
#   LOCAL_WINDOW_HALF  = 150 px：旧"峰值±窗口加权重心"的窗口半宽。生产已弃用
#                             （改连通域轮廓拟合，见 _locate_by_contour），此常量
#                             仅保留供 exp/centroid 分析脚本画旧窗口对照。
INTENSITY_FLOOR = 30.0
SATURATION_CEIL = 0.15
LOCAL_WINDOW_HALF = 150

# 高斯裙边拟合（method="gaussian_skirt"）ROI 参数：
#   GAUSSIAN_CORE_THR = 0.8：先取含峰值的高阈值连通域作「核」——背景远低于它，
#                            绝不会顺着微弱光晕 balloon 到整帧（旧低阈值全局洪水会，
#                            曾把某图中心拉飞，见提交说明）。
#   GAUSSIAN_ROI_PAD  = 6 px：核包围盒外扩这么多得到有界 ROI，只在框内拟合裙边。
#                            远裙边不对称会抬高方差，故取小。实测该组合 σ≈111μm。
GAUSSIAN_CORE_THR = 0.8
GAUSSIAN_ROI_PAD = 6
GAUSSIAN_SKIRT_FLOOR = 0.15


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
    """连通域轮廓拟合提取光斑中心，返回 (u, v) 与质量指标。

    步骤：
    1. 高斯模糊。
    2. cv2.minMaxLoc 找全局峰值位置——仅用于选定"含峰值的连通域"，不再当中心。
    3. 硬门槛（防止在垃圾图上返回伪坐标）：
       - max_val < INTENSITY_FLOOR：几乎全黑，只有传感器噪声，抛异常。
       - 全局 mask 占比 > SATURATION_CEIL：大面积饱和（拍到取景框而非圆版），抛异常。
    4. 光斑定位：按 config.method 分发（见 _locate_by_method）。可选：
       - "contour_ellipse"（别名 "improved_circle_fit"，默认）：含峰值连通域椭圆拟合。
       - "plateau_centroid"：饱和平台(=255)几何质心，实测最优档 ~105μm。
       - "gaussian_skirt"：排除饱和像素的 2D 高斯裙边拟合，取解析峰值。
       三者组内 σ 对比见 exp/centroid。
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

    u, v = _locate_by_method(image, blurred, global_mask, peak_x, peak_y, config)

    quality = _compute_quality(blurred, global_mask, u, v, max_val)
    return (u, v), quality


def _locate_by_method(
    image: np.ndarray,
    blurred: np.ndarray,
    global_mask: np.ndarray,
    peak_x: int,
    peak_y: int,
    config: SpotExtractionConfig,
) -> tuple[float, float]:
    """按 config.method 选择定位算法。未知方法抛异常（防配置写错静默走默认）。"""
    method = (config.method or "").strip().lower()
    if method in ("contour_ellipse", "improved_circle_fit"):
        return _locate_by_contour(blurred, global_mask, peak_x, peak_y)
    if method == "plateau_centroid":
        return _locate_by_plateau(image, global_mask, peak_x, peak_y)
    if method == "gaussian_skirt":
        return _locate_by_gaussian(image, blurred, peak_x, peak_y)
    raise ValueError(
        f"未知的光斑提取方法 method={config.method!r}；可选："
        "contour_ellipse / plateau_centroid / gaussian_skirt"
    )


def _locate_by_contour(
    blurred: np.ndarray, global_mask: np.ndarray, peak_x: int, peak_y: int
) -> tuple[float, float]:
    """在含峰值的连通域上定位光斑中心。

    优先 cv2.fitEllipse（对不圆光斑最鲁棒，实测最优）；轮廓点 < 5 或拟合异常时
    回退到连通域几何形心（不加权的坐标均值，实测精度几乎等同且无失败风险）。

    连通域天然是自适应窗口：随光斑实际大小伸缩，不依赖峰值点位置，
    因此不受"峰值偏上"影响。
    """
    mask_u8 = global_mask.astype(np.uint8)
    num, labels, _, _ = cv2.connectedComponentsWithStats(mask_u8, 8)
    peak_label = int(labels[peak_y, peak_x])
    if peak_label == 0:
        # 峰值不在任何前景块内（理论上不会发生，因 threshold < peak）——兜底用峰值
        raise ValueError("光斑提取失败：峰值不在任何阈值连通域内")

    component = (labels == peak_label).astype(np.uint8)
    ys, xs = np.where(component)

    # 几何形心（回退值，同时用于椭圆失败时）
    geom_u = float(xs.mean())
    geom_v = float(ys.mean())

    # 椭圆拟合：对连通域外轮廓 fitEllipse，取椭圆中心
    contours, _ = cv2.findContours(
        component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if contours:
        contour = max(contours, key=cv2.contourArea)
        if len(contour) >= 5:
            try:
                (cx, cy), _axes, _angle = cv2.fitEllipse(contour)
                # 合理性校验：椭圆中心应落在连通域包围盒内，否则视为病态拟合
                if xs.min() <= cx <= xs.max() and ys.min() <= cy <= ys.max():
                    return float(cx), float(cy)
            except cv2.error:
                pass

    return geom_u, geom_v


def _locate_by_plateau(
    image: np.ndarray, global_mask: np.ndarray, peak_x: int, peak_y: int,
    sat_level: int = 255,
) -> tuple[float, float]:
    """饱和平台几何质心：含峰值连通域内 =sat_level 像素的坐标均值。

    重度饱和下核心大且近正圆、质心极稳，又完全避开不对称脏裙边，实测 ~105μm
    （见 exp/centroid）。无平台（未来不饱和图）时回退连通域几何形心。
    """
    _, labels, _, _ = cv2.connectedComponentsWithStats(global_mask.astype(np.uint8), 8)
    peak_label = int(labels[peak_y, peak_x])
    if peak_label == 0:
        raise ValueError("光斑提取失败：峰值不在任何阈值连通域内")
    component = labels == peak_label
    plateau = (image >= sat_level) & component
    ys, xs = np.where(plateau) if plateau.any() else np.where(component)
    return float(xs.mean()), float(ys.mean())


def _gauss2d(xy, B, A, mx, my, sx, sy):
    """2D 轴对齐椭圆高斯：I = B + A·exp(-((x-mx)²/2sx² + (y-my)²/2sy²))。"""
    x, y = xy
    return B + A * np.exp(-(((x - mx) ** 2) / (2 * sx ** 2) + ((y - my) ** 2) / (2 * sy ** 2)))


def _locate_by_gaussian(
    image: np.ndarray, blurred: np.ndarray, peak_x: int, peak_y: int,
    core_thr: float = GAUSSIAN_CORE_THR, roi_pad: int = GAUSSIAN_ROI_PAD,
    skirt_floor: float = GAUSSIAN_SKIRT_FLOOR, sat_level: int = 255,
    max_pts: int = 6000,
) -> tuple[float, float]:
    """排除饱和像素的 2D 椭圆高斯拟合，取解析峰值 μ 作光斑中心。

    有平台→剔除=255像素靠裙边外推峰值；无平台→全像素参与，一套逻辑兼容两种图。

    ROI 用「稳健核 + 有界外扩」而非低阈值全局洪水：先取含峰值的高阈值连通域
    （core_thr，背景远低于它、绝不 balloon）作核，把包围盒外扩 roi_pad 得到有界
    ROI，只在框内按 skirt_floor 取局部连通域拟合。避免低阈值洪水顺微弱光晕蔓延到
    整帧、把中心拉飞。拟合失败/病态回退：核内饱和平台质心，否则核几何形心。
    实测 σ≈111μm（见提交说明）。
    """
    from scipy.optimize import curve_fit  # 延迟导入：非该方法时不加载 scipy

    b = blurred
    mx = float(b.max())
    core = (b > mx * core_thr).astype(np.uint8)
    _, labels, _, _ = cv2.connectedComponentsWithStats(core, 8)
    lab = int(labels[peak_y, peak_x])
    if lab == 0:
        raise ValueError("光斑提取失败：峰值不在高阈值连通域内")
    core_mask = labels == lab
    cys, cxs = np.where(core_mask)
    cu, cv = float(cxs.mean()), float(cys.mean())
    area = int(core_mask.sum())

    def _fallback() -> tuple[float, float]:
        plateau = (image >= sat_level) & core_mask
        if plateau.any():
            pys, pxs = np.where(plateau)
            return float(pxs.mean()), float(pys.mean())
        return cu, cv

    # 有界 ROI：核包围盒外扩 roi_pad
    x0, y0 = max(0, int(cxs.min()) - roi_pad), max(0, int(cys.min()) - roi_pad)
    x1 = min(b.shape[1] - 1, int(cxs.max()) + roi_pad)
    y1 = min(b.shape[0] - 1, int(cys.max()) + roi_pad)
    roi = b[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    roi_raw = image[y0:y1 + 1, x0:x1 + 1]

    # ROI 内按 skirt_floor 取含峰值的局部连通域（洪水被 ROI 限制，不会蔓延全帧）
    loc = (roi > mx * skirt_floor).astype(np.uint8)
    _, loc_labels, _, _ = cv2.connectedComponentsWithStats(loc, 8)
    lpx, lpy = peak_x - x0, peak_y - y0
    comp_roi = (loc_labels == loc_labels[lpy, lpx]) if loc_labels[lpy, lpx] != 0 else loc.astype(bool)

    sat = (roi_raw >= sat_level).astype(np.uint8)
    if sat.any():
        sat = cv2.dilate(sat, np.ones((5, 5), np.uint8))  # 去掉模糊把255渗进裙边的过渡带
    keep = comp_roi & (sat == 0)

    gy, gx = np.mgrid[0:roi.shape[0], 0:roi.shape[1]]
    xk, yk, zk = gx[keep], gy[keep], roi[keep]
    if zk.size > max_pts:                                # 等距抽样加速（确定性）
        stride = zk.size // max_pts
        xk, yk, zk = xk[::stride], yk[::stride], zk[::stride]
    if zk.size < 20:
        return _fallback()

    bg = float(np.median(b))
    r = max(np.sqrt(area / np.pi), 2.0)
    p0 = [bg, max(mx - bg, 1.0), cu - x0, cv - y0, r / 2, r / 2]
    lo = [0.0, 1.0, 0.0, 0.0, 1.0, 1.0]
    hi = [255.0, 1e5, float(roi.shape[1]), float(roi.shape[0]),
          float(roi.shape[1]), float(roi.shape[0])]
    try:
        popt, _ = curve_fit(_gauss2d, np.vstack([xk, yk]), zk, p0=p0,
                            bounds=(lo, hi), maxfev=20000)
        _B, _A, mux, muy, _sx, _sy = popt
        if 0 <= mux <= roi.shape[1] - 1 and 0 <= muy <= roi.shape[0] - 1:
            return float(mux + x0), float(muy + y0)
    except Exception:  # noqa: BLE001 - curve_fit 不收敛/奇异都回退
        pass
    return _fallback()


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
