"""高斯裙边拟合法（method="gaussian_skirt"）的光斑圆心提取重复性分析。

数据：dataset/spot_extraction/{group1,group2}/sample-*/{cam1_002,cam2_002}.png
激光两分钟内固定不动，同组样本理论上圆心应落在同一像素位置；本脚本用高斯裙边
拟合逐图提取圆心，输出中间过程并统计组内重复度（σ）。

产物全部写入 dataset/spot_extraction/_gaussian_analysis/：
  annotated/<group>/<sample>_<cam>.png   每图标注 ROI 提取范围 + 拟合圆心
  per_image.csv                          每图中间过程数据（含平台 255 像素数）
  scatter_<group>_<cam>.png              组内圆心散点（重复性可视化）
  repeatability.txt / .json              组内 σ 汇总

从项目根运行：uv run python exp/centroid/gaussian_repeatability.py
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import curve_fit
from PIL import Image, ImageDraw, ImageFont

from dcpam.steps.spot_extraction import (
    _gauss2d,
    _locate_by_gaussian,
    GAUSSIAN_CORE_THR,
    GAUSSIAN_ROI_PAD,
    GAUSSIAN_SKIRT_FLOOR,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "dataset" / "spot_extraction"
OUT_DIR = DATA_DIR / "_gaussian_analysis"

KERNEL = 9
SIGMA = 2.0
SAT_LEVEL = 255

FONT_PATH = "/System/Library/Fonts/STHeiti Light.ttc"

# 各层配色（RGB 用于 PIL 文本/图例，BGR 用于 cv2 画线，两者一一对应）
COL_OUTER_RGB = (0, 200, 255)     # 外层裙边 15%·峰值
COL_PLATEAU_RGB = (255, 230, 0)   # 255 平台 = 内层裙边（未膨胀）
COL_EXCLUDE_RGB = (255, 150, 0)   # 拟合排除边界 = 平台 +2px（膨胀后）
COL_FIT_RGB = (0, 255, 0)         # 高斯拟合裙带（keep）
COL_CENTER_RGB = (255, 60, 60)    # 拟合圆心
COL_ROI_RGB = (180, 180, 180)     # ROI 有界框
_rgb2bgr = lambda c: (c[2], c[1], c[0])


@dataclass
class SpotFit:
    """单图高斯裙边拟合的圆心 + 中间过程数据。"""
    group: str
    sample: str
    cam: str
    u: float                 # 拟合圆心（原图像素坐标）
    v: float
    max_intensity: float     # 高斯模糊后峰值
    core_area: int           # 高阈值核连通域像素数（>core_thr·max）
    plateau_255_count: int   # 平台区：外层裙带内 =255 的饱和像素数（内层裙边包围）
    outer_skirt_count: int   # 外层裙边(15%·峰值)连通域像素数
    exclude_count: int       # 拟合排除边界(平台膨胀+2px)像素数
    plateau_radius: float    # 平台等效半径 sqrt(N/pi) px
    outer_radius: float      # 外层裙边等效半径 px
    roi_x0: int              # ROI 提取范围（有界框，实际参与拟合的区域）
    roi_y0: int
    roi_x1: int
    roi_y1: int
    fit_points: int          # 排除饱和 + 抽样后真正参与拟合的裙边点数
    sigma_x: float           # 拟合高斯的 σ（ROI 局部坐标，像素）
    sigma_y: float
    fit_ok: bool             # True=解析峰值；False=回退到平台/核质心
    prod_u: float            # 产品函数 _locate_by_gaussian 的圆心（一致性校验）
    prod_v: float


def _instrumented_gaussian(
    image: np.ndarray,
    blurred: np.ndarray,
    peak_x: int,
    peak_y: int,
    core_thr: float = GAUSSIAN_CORE_THR,
    roi_pad: int = GAUSSIAN_ROI_PAD,
    skirt_floor: float = GAUSSIAN_SKIRT_FLOOR,
    sat_level: int = SAT_LEVEL,
    max_pts: int = 6000,
):
    """完整复刻 dcpam.steps.spot_extraction._locate_by_gaussian，额外返回中间过程。

    返回 (u, v, info)，逻辑与产品实现逐行对应；info 携带 ROI 框、核面积、
    平台 255 像素数、拟合点数、σ、是否解析拟合成功。
    """
    b = blurred
    mx = float(b.max())
    core = (b > mx * core_thr).astype(np.uint8)
    _, labels, _, _ = cv2.connectedComponentsWithStats(core, 8)
    lab = int(labels[peak_y, peak_x])
    if lab == 0:
        raise ValueError("峰值不在高阈值连通域内")
    core_mask = labels == lab
    cys, cxs = np.where(core_mask)
    cu, cv = float(cxs.mean()), float(cys.mean())
    area = int(core_mask.sum())

    # 回退用的平台（核连通域内 =255），与产品实现完全一致
    plateau_core = (image >= sat_level) & core_mask

    def _fallback():
        if plateau_core.any():
            pys, pxs = np.where(plateau_core)
            return float(pxs.mean()), float(pys.mean())
        return cu, cv

    x0 = max(0, int(cxs.min()) - roi_pad)
    y0 = max(0, int(cys.min()) - roi_pad)
    x1 = min(b.shape[1] - 1, int(cxs.max()) + roi_pad)
    y1 = min(b.shape[0] - 1, int(cys.max()) + roi_pad)
    roi = b[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    roi_raw = image[y0:y1 + 1, x0:x1 + 1]

    # 外层裙边：ROI 内 >15%·峰值、含峰值的局部连通域
    loc = (roi > mx * skirt_floor).astype(np.uint8)
    _, loc_labels, _, _ = cv2.connectedComponentsWithStats(loc, 8)
    lpx, lpy = peak_x - x0, peak_y - y0
    comp_roi = (
        (loc_labels == loc_labels[lpy, lpx])
        if loc_labels[lpy, lpx] != 0
        else loc.astype(bool)
    )

    # 内层裙边（未膨胀）= 外层裙带内的 255 平台
    plateau_roi = (roi_raw >= sat_level) & comp_roi
    # 拟合排除边界 = 平台膨胀 +2px（去掉模糊渗进裙边的过渡带）
    sat = (roi_raw >= sat_level).astype(np.uint8)
    if sat.any():
        sat = cv2.dilate(sat, np.ones((5, 5), np.uint8))
    exclude_roi = sat.astype(bool)
    keep = comp_roi & (sat == 0)   # 高斯拟合裙带

    outer_area = int(comp_roi.sum())
    plateau_area = int(plateau_roi.sum())

    info = {
        "core_area": area,
        "plateau_255_count": plateau_area,
        "outer_skirt_count": outer_area,
        "exclude_count": int(exclude_roi.sum()),
        "plateau_radius": float(np.sqrt(plateau_area / np.pi)) if plateau_area else 0.0,
        "outer_radius": float(np.sqrt(outer_area / np.pi)) if outer_area else 0.0,
        "roi_x0": x0, "roi_y0": y0, "roi_x1": x1, "roi_y1": y1,
        "fit_points": 0,
        "sigma_x": float("nan"), "sigma_y": float("nan"),
        "fit_ok": False,
        # 供标注用（ROI 局部坐标）
        "_roi": roi, "_x0": x0, "_y0": y0,
        "_comp_roi": comp_roi, "_plateau_roi": plateau_roi,
        "_exclude_roi": exclude_roi, "_keep": keep,
        "_mux": None, "_muy": None,
    }

    gy, gx = np.mgrid[0:roi.shape[0], 0:roi.shape[1]]
    xk, yk, zk = gx[keep], gy[keep], roi[keep]
    if zk.size > max_pts:
        stride = zk.size // max_pts
        xk, yk, zk = xk[::stride], yk[::stride], zk[::stride]
    info["fit_points"] = int(zk.size)
    if zk.size < 20:
        u, v = _fallback()
        return u, v, info

    bg = float(np.median(b))
    r = max(np.sqrt(area / np.pi), 2.0)
    p0 = [bg, max(mx - bg, 1.0), cu - x0, cv - y0, r / 2, r / 2]
    lo = [0.0, 1.0, 0.0, 0.0, 1.0, 1.0]
    hi = [255.0, 1e5, float(roi.shape[1]), float(roi.shape[0]),
          float(roi.shape[1]), float(roi.shape[0])]
    try:
        popt, _ = curve_fit(_gauss2d, np.vstack([xk, yk]), zk, p0=p0,
                            bounds=(lo, hi), maxfev=20000)
        _B, _A, mux, muy, sx, sy = popt
        if 0 <= mux <= roi.shape[1] - 1 and 0 <= muy <= roi.shape[0] - 1:
            info["sigma_x"] = float(sx)
            info["sigma_y"] = float(sy)
            info["fit_ok"] = True
            info["_mux"] = float(mux)
            info["_muy"] = float(muy)
            return float(mux + x0), float(muy + y0), info
    except Exception:  # noqa: BLE001
        pass
    u, v = _fallback()
    return u, v, info


def process_image(path: Path, group: str, sample: str, cam: str) -> SpotFit | None:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        print(f"  [跳过] 读取失败 {path}")
        return None

    blurred = cv2.GaussianBlur(image, (KERNEL, KERNEL), SIGMA)
    _, max_val, _, peak_loc = cv2.minMaxLoc(blurred)
    peak_x, peak_y = int(peak_loc[0]), int(peak_loc[1])

    try:
        u, v, info = _instrumented_gaussian(image, blurred, peak_x, peak_y)
    except ValueError as e:
        print(f"  [跳过] {path.parent.name}/{path.name}: {e}")
        return None

    # 一致性校验：与产品函数对齐（应完全相同）
    prod_u, prod_v = _locate_by_gaussian(image, blurred, peak_x, peak_y)

    fit = SpotFit(
        group=group, sample=sample, cam=cam,
        u=u, v=v, max_intensity=float(max_val),
        core_area=info["core_area"],
        plateau_255_count=info["plateau_255_count"],
        outer_skirt_count=info["outer_skirt_count"],
        exclude_count=info["exclude_count"],
        plateau_radius=info["plateau_radius"],
        outer_radius=info["outer_radius"],
        roi_x0=info["roi_x0"], roi_y0=info["roi_y0"],
        roi_x1=info["roi_x1"], roi_y1=info["roi_y1"],
        fit_points=info["fit_points"],
        sigma_x=info["sigma_x"], sigma_y=info["sigma_y"],
        fit_ok=info["fit_ok"],
        prod_u=float(prod_u), prod_v=float(prod_v),
    )
    _save_annotated(image, fit, info, group, sample, cam)
    return fit


def _mask_contour_on(canvas, mask, offset, scale, color_bgr, thickness=2):
    """把 ROI 局部 mask 的外轮廓画到已放大的 canvas 上。"""
    ox, oy = offset
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        pts = c.reshape(-1, 2).astype(np.float64)
        pts[:, 0] = (pts[:, 0] + ox) * scale
        pts[:, 1] = (pts[:, 1] + oy) * scale
        cv2.polylines(canvas, [pts.astype(np.int32)], True, color_bgr,
                      thickness, cv2.LINE_AA)


def _save_annotated(image, fit: SpotFit, info: dict, group, sample, cam):
    """放大圆斑，画出三层边界 + 高斯拟合裙带 + 拟合圆心，附中间过程数据（中文）。

    图层（由内到外）：
      黄  255 平台 = 内层裙边（未膨胀，恰好包围饱和像素）
      橙  拟合排除边界 = 平台膨胀 +2px（去掉模糊过渡带）
      绿  高斯拟合裙带 keep（真正喂给 curve_fit 的环带，半透明填充）
      青  外层裙边 = 15%·峰值连通域（裙边最外沿，拟合区外边界）
      灰  ROI 有界框
      红  拟合圆心
    """
    H, W = image.shape
    x0, y0, x1, y1 = fit.roi_x0, fit.roi_y0, fit.roi_x1, fit.roi_y1
    M = 40  # ROI 外再留白，便于看外层裙边
    zx0, zy0 = max(0, x0 - M), max(0, y0 - M)
    zx1, zy1 = min(W, x1 + 1 + M), min(H, y1 + 1 + M)
    crop = image[zy0:zy1, zx0:zx1]

    s = 2  # 放大倍数
    canvas = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    canvas = cv2.resize(canvas, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)

    # ROI mask 在 crop 内的偏移（ROI 局部坐标 → crop 坐标）
    ox, oy = x0 - zx0, y0 - zy0

    # 半透明填充：高斯拟合裙带（绿）
    keep = info["_keep"]
    overlay = canvas.copy()
    kk = np.zeros((crop.shape[0], crop.shape[1]), np.uint8)
    kk[oy:oy + keep.shape[0], ox:ox + keep.shape[1]] = keep.astype(np.uint8)
    kk = cv2.resize(kk, (canvas.shape[1], canvas.shape[0]), interpolation=cv2.INTER_NEAREST)
    overlay[kk > 0] = _rgb2bgr(COL_FIT_RGB)
    canvas = cv2.addWeighted(overlay, 0.28, canvas, 0.72, 0)

    # 各层轮廓
    _mask_contour_on(canvas, info["_comp_roi"], (ox, oy), s, _rgb2bgr(COL_OUTER_RGB), 2)
    _mask_contour_on(canvas, info["_exclude_roi"], (ox, oy), s, _rgb2bgr(COL_EXCLUDE_RGB), 2)
    _mask_contour_on(canvas, info["_plateau_roi"], (ox, oy), s, _rgb2bgr(COL_PLATEAU_RGB), 2)

    # ROI 有界框（灰）
    cv2.rectangle(canvas, ((x0 - zx0) * s, (y0 - zy0) * s),
                  ((x1 - zx0) * s, (y1 - zy0) * s), _rgb2bgr(COL_ROI_RGB), 1)

    # 拟合圆心（红十字 + 小圈）
    cu = int(round((fit.u - zx0) * s))
    cv_ = int(round((fit.v - zy0) * s))
    cv2.drawMarker(canvas, (cu, cv_), _rgb2bgr(COL_CENTER_RGB), cv2.MARKER_CROSS, 34, 2)
    cv2.circle(canvas, (cu, cv_), 5, _rgb2bgr(COL_CENTER_RGB), 2)

    # ---- PIL 文本层（中文）----
    pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil, "RGBA")
    f_big = ImageFont.truetype(FONT_PATH, 20)
    f = ImageFont.truetype(FONT_PATH, 16)

    def txt(xy, s_, color, font=f):
        draw.text(xy, s_, fill=color, font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))

    lines = [
        (f"{group}/{sample}/{cam}   高斯裙边拟合", (255, 255, 255)),
        (f"圆心 = ({fit.u:.2f}, {fit.v:.2f}) px   拟合成功={fit.fit_ok}", COL_CENTER_RGB),
        (f"255 平台 = {fit.plateau_255_count} px  (r≈{fit.plateau_radius:.1f})", COL_PLATEAU_RGB),
        (f"外层裙边 = {fit.outer_skirt_count} px  (r≈{fit.outer_radius:.1f})", COL_OUTER_RGB),
        (f"拟合裙带点数 = {fit.fit_points}   σ=({fit.sigma_x:.2f}, {fit.sigma_y:.2f})", COL_FIT_RGB),
        (f"ROI = [{x0},{y0}]-[{x1},{y1}]  ({x1-x0+1}x{y1-y0+1})", COL_ROI_RGB),
    ]
    ty = 8
    for line, color in lines:
        txt((8, ty), line, color)
        ty += 24

    # 图例（右下角）
    legend = [
        (COL_PLATEAU_RGB, "255 平台 = 内层裙边"),
        (COL_EXCLUDE_RGB, "拟合排除边界 (平台+2px)"),
        (COL_FIT_RGB, "高斯拟合裙带"),
        (COL_OUTER_RGB, "外层裙边 15%·峰值"),
        (COL_CENTER_RGB, "拟合圆心"),
    ]
    lw, lh = 250, len(legend) * 24 + 12
    lx, ly = pil.width - lw - 8, pil.height - lh - 8
    draw.rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 150))
    for i, (color, name) in enumerate(legend):
        yy = ly + 8 + i * 24
        draw.line([lx + 10, yy + 8, lx + 34, yy + 8], fill=color, width=4)
        draw.text((lx + 42, yy), name, fill=color, font=f)

    out = OUT_DIR / "annotated" / group
    out.mkdir(parents=True, exist_ok=True)
    pil.save(out / f"{sample}_{cam}.png")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fits: list[SpotFit] = []

    for group in sorted(p.name for p in DATA_DIR.iterdir()
                        if p.is_dir() and p.name.startswith("group")):
        gdir = DATA_DIR / group
        samples = sorted(gdir.iterdir(), key=lambda p: p.name)
        print(f"[{group}] {len([s for s in samples if s.is_dir()])} samples")
        for sdir in samples:
            if not sdir.is_dir():
                continue
            for cam in ("cam1", "cam2"):
                png = sdir / f"{cam}_002.png"
                if not png.exists():
                    print(f"  [缺失] {png}")
                    continue
                fit = process_image(png, group, sdir.name, cam)
                if fit is not None:
                    fits.append(fit)

    _write_csv(fits)
    _consistency_report(fits)
    _repeatability(fits)
    print(f"\n完成。产物在 {OUT_DIR}")


def _write_csv(fits: list[SpotFit]):
    csv_path = OUT_DIR / "per_image.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(fits[0]).keys()))
        w.writeheader()
        for fit in fits:
            w.writerow(asdict(fit))
    print(f"写出 {csv_path}  ({len(fits)} 行)")


def _consistency_report(fits: list[SpotFit]):
    diffs = [np.hypot(f.u - f.prod_u, f.v - f.prod_v) for f in fits]
    diffs = np.array(diffs)
    print(f"\n与产品 _locate_by_gaussian 一致性：max Δ={diffs.max():.3e}px，"
          f"mean Δ={diffs.mean():.3e}px（应≈0）")


def _repeatability(fits: list[SpotFit]):
    """按 (group, cam) 分组，统计圆心重复度（组内 σ）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups: dict[tuple[str, str], list[SpotFit]] = {}
    for f in fits:
        groups.setdefault((f.group, f.cam), []).append(f)

    summary = {}
    lines = ["高斯裙边拟合法 圆心提取重复性（激光固定，组内理论应同点）", "=" * 64]
    for (group, cam), items in sorted(groups.items()):
        us = np.array([f.u for f in items])
        vs = np.array([f.v for f in items])
        mu_u, mu_v = us.mean(), vs.mean()
        std_u, std_v = us.std(ddof=1), vs.std(ddof=1)
        # 径向散布：各点到组内均值中心的距离
        radial = np.hypot(us - mu_u, vs - mu_v)
        rms = float(np.sqrt(np.mean(radial ** 2)))
        plateau = np.array([f.plateau_255_count for f in items])
        n_fallback = sum(1 for f in items if not f.fit_ok)

        key = f"{group}_{cam}"
        summary[key] = {
            "n": len(items),
            "mean_u": float(mu_u), "mean_v": float(mu_v),
            "std_u_px": float(std_u), "std_v_px": float(std_v),
            "rms_radial_px": rms,
            "max_radial_px": float(radial.max()),
            "plateau_255_mean": float(plateau.mean()),
            "plateau_255_min": int(plateau.min()),
            "plateau_255_max": int(plateau.max()),
            "n_fallback": n_fallback,
        }
        lines += [
            f"\n[{key}]  n={len(items)}",
            f"  圆心均值      : ({mu_u:.3f}, {mu_v:.3f}) px",
            f"  σ_u / σ_v     : {std_u:.4f} / {std_v:.4f} px",
            f"  径向 RMS      : {rms:.4f} px   (max {radial.max():.4f} px)",
            f"  平台255像素   : mean={plateau.mean():.1f}  "
            f"[{plateau.min()}, {plateau.max()}]",
            f"  回退(非解析)  : {n_fallback}/{len(items)}",
        ]

        # 散点图
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.scatter(us, vs, s=18, alpha=0.7, c="tab:blue")
        ax.scatter([mu_u], [mu_v], marker="+", s=200, c="red", label="mean")
        ax.set_title(f"{key}  σ_u={std_u:.3f} σ_v={std_v:.3f} RMS={rms:.3f}px")
        ax.set_xlabel("u (px)"); ax.set_ylabel("v (px)")
        ax.invert_yaxis(); ax.set_aspect("equal", "datalim")
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT_DIR / f"scatter_{key}.png", dpi=130)
        plt.close(fig)

    txt = "\n".join(lines)
    (OUT_DIR / "repeatability.txt").write_text(txt + "\n", encoding="utf-8")
    (OUT_DIR / "repeatability.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + txt)


if __name__ == "__main__":
    main()
