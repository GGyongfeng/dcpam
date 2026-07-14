"""三种光斑圆心提取法在「两分钟固定采样」数据上的重复性对比。

对同一批固定激光图像，分别用 contour_ellipse / plateau_centroid / gaussian_skirt
提取圆心，按 (组, 相机) 统计组内散布（径向 RMS），比较哪种方法重复性最好。

数据：dataset/spot_extraction/{group1,group2}/sample-*/{cam1_002,cam2_002}.png
从项目根运行：uv run python exp/centroid/method_compare.py
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from dcpam.steps.spot_extraction import (
    _locate_by_gaussian,
    _locate_by_plateau,
    _locate_by_contour,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "dataset" / "spot_extraction"
KER, SIG, THR = 9, 2.0, 0.8

METHODS = ("contour_ellipse", "plateau_centroid", "gaussian_skirt")


def centers(img: np.ndarray) -> dict[str, tuple[float, float]]:
    b = cv2.GaussianBlur(img, (KER, KER), SIG)
    _, mx, _, pk = cv2.minMaxLoc(b)
    px, py = int(pk[0]), int(pk[1])
    gmask = b > mx * THR
    return {
        "contour_ellipse": _locate_by_contour(b, gmask, px, py),
        "plateau_centroid": _locate_by_plateau(img, gmask, px, py),
        "gaussian_skirt": _locate_by_gaussian(img, b, px, py),
    }


def main():
    acc: dict[tuple[str, str], dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for group in ("group1", "group2"):
        for sdir in sorted((DATA / group).iterdir()):
            if not sdir.is_dir():
                continue
            for cam in ("cam1", "cam2"):
                p = sdir / f"{cam}_002.png"
                if not p.exists():
                    continue
                img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                for m, uv in centers(img).items():
                    acc[(group, cam)][m].append(uv)

    print(f"{'组·相机':<13}{'方法':<18}{'σ_u':>7}{'σ_v':>7}{'RMS':>8}{'max':>8}")
    print("-" * 61)
    overall: dict[str, list] = defaultdict(list)
    for key in sorted(acc):
        for m in METHODS:
            pts = np.array(acc[key][m])
            u, v = pts[:, 0], pts[:, 1]
            mu, mv = u.mean(), v.mean()
            su, sv = u.std(ddof=1), v.std(ddof=1)
            rad = np.hypot(u - mu, v - mv)
            rms = float(np.sqrt((rad ** 2).mean()))
            overall[m].append(rms)
            print(f"{key[0]}·{key[1]:<7}{m:<18}{su:>7.3f}{sv:>7.3f}"
                  f"{rms:>8.3f}{rad.max():>8.3f}")
        print()
    print("各方法 4 组 RMS 平均：")
    for m in METHODS:
        print(f"  {m:<18}{np.mean(overall[m]):.3f} px")


if __name__ == "__main__":
    main()
