"""实验 B：不同圆心提取算法对组内 σ 的影响 + 光斑不圆度分析。

背景：当前提取是"峰值 + 局部窗口强度加权重心"(centroid_threshold=0.3)。
实测光斑大而饱和（4万+像素=255）、明显不圆（轴比~1.4），低阈值加权重心会被
不对称拖尾拉偏。本实验对全体样本用多种提取法重提圆心 → 重跑反投影 → 比 σ。

用法：uv run python exp/centroid/centroid.py
"""
from __future__ import annotations

import collections
import csv
import importlib.util
import re
import statistics as st
import sys
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from dcpam_cv.config import load_config
from dcpam_cv.types import Point2D


def _load_projector_module():
    path = _ROOT / "scripts" / "20_project_spot_centers.py"
    spec = importlib.util.spec_from_file_location("project20", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 多种圆心提取器：输入灰度图，返回 (u, v)
# ---------------------------------------------------------------------------

def _blur(img: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(img, (9, 9), 2)


def extract_weighted_centroid(img: np.ndarray, thr_ratio: float = 0.3) -> tuple[float, float]:
    """baseline：峰值 + 局部窗口(±30)强度加权重心。"""
    b = _blur(img)
    _, mx, _, (px, py) = cv2.minMaxLoc(b)
    thr = mx * thr_ratio
    h, w = b.shape
    y0, y1 = max(0, py - 30), min(h, py + 31)
    x0, x1 = max(0, px - 30), min(w, px + 31)
    win = b[y0:y1, x0:x1]
    m = win > thr
    ys, xs = np.where(m)
    wt = win[ys, xs].astype(float)
    return float(((xs + x0) * wt).sum() / wt.sum()), float(((ys + y0) * wt).sum() / wt.sum())


def _global_mask(img: np.ndarray, thr_ratio: float):
    b = _blur(img)
    mx = float(b.max())
    return b, (b > mx * thr_ratio)


def extract_geometric_centroid(img: np.ndarray, thr_ratio: float = 0.5) -> tuple[float, float]:
    """阈值几何形心：mask 内像素坐标均值（不加权，弱化亮度不对称）。"""
    _, m = _global_mask(img, thr_ratio)
    ys, xs = np.where(m)
    return float(xs.mean()), float(ys.mean())


def extract_high_threshold_centroid(img: np.ndarray, thr_ratio: float = 0.7) -> tuple[float, float]:
    """高阈值加权重心：只取核心亮区，抑制不圆拖尾。"""
    b, m = _global_mask(img, thr_ratio)
    ys, xs = np.where(m)
    wt = b[ys, xs].astype(float)
    return float((xs * wt).sum() / wt.sum()), float((ys * wt).sum() / wt.sum())


def extract_ellipse(img: np.ndarray, thr_ratio: float = 0.5) -> tuple[float, float]:
    """椭圆拟合心：对最大轮廓 fitEllipse，取椭圆中心（对不圆最鲁棒）。"""
    b, m = _global_mask(img, thr_ratio)
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea)
    if len(c) >= 5:
        (cx, cy), _, _ = cv2.fitEllipse(c)
        return float(cx), float(cy)
    return extract_geometric_centroid(img, thr_ratio)


EXTRACTORS = {
    "baseline(重心0.3)": extract_weighted_centroid,
    "几何形心0.5": extract_geometric_centroid,
    "高阈值重心0.7": extract_high_threshold_centroid,
    "椭圆拟合0.5": extract_ellipse,
}


def ellipse_axis_ratio(img: np.ndarray, thr_ratio: float = 0.5) -> float:
    """不圆度：拟合椭圆长短轴比（1=正圆）。"""
    _, m = _global_mask(img, thr_ratio)
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return float("nan")
    c = max(cnts, key=cv2.contourArea)
    if len(c) < 5:
        return float("nan")
    (_, _), (MA, ma), _ = cv2.fitEllipse(c)
    return max(MA, ma) / max(min(MA, ma), 1e-6)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _read(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"读图失败: {path}")
    return img


def main() -> None:
    p20 = _load_projector_module()
    config = load_config(Path("config.toml"))
    rows = list(csv.DictReader(open("dataset/samples/1-Spot-Center.csv")))

    # 预读所有图（避免每个提取器重复 IO）
    print(f"读取 {len(rows)} 组图像…")
    imgs = [(r["name"], _read(r["front_path"]), _read(r["rear_path"])) for r in rows]

    def sigma_for(extractor) -> dict[str, float]:
        projector = p20.SpotMeasurementProjector(config)
        by_group = collections.defaultdict(list)
        for name, fimg, rimg in imgs:
            fu, fv = extractor(fimg)
            ru, rv = extractor(rimg)
            rec = projector._project_row(
                p20.SpotCenterRow(name=name, front_u=fu, front_v=fv, rear_u=ru, rear_v=rv))
            by_group[re.sub(r"-\d+$", "", name)].append(rec.distance_mm)
        return {g: st.pstdev(v) * 1000 for g, v in by_group.items() if len(v) >= 2}

    print(f"\n{'提取法':>18} {'平均σ/μm':>10}")
    all_sig = {}
    for label, ex in EXTRACTORS.items():
        sig = sigma_for(ex)
        all_sig[label] = st.mean(sig.values())
        print(f"{label:>18} {all_sig[label]:>10.1f}")
    best = min(all_sig, key=all_sig.get)
    print(f"\n最优：{best} → σ={all_sig[best]:.1f}μm（baseline {all_sig['baseline(重心0.3)']:.1f}）")

    # 不圆度分析
    ratios = [ellipse_axis_ratio(f) for _, f, _ in imgs]
    ratios = [r for r in ratios if not np.isnan(r)]
    print(f"\n光斑不圆度（前相机椭圆轴比）：均值 {np.mean(ratios):.2f} "
          f"min {min(ratios):.2f} max {max(ratios):.2f}（1=正圆）")


if __name__ == "__main__":
    main()
