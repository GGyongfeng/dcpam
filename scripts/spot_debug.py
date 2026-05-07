"""光斑提取中间步骤可视化调试脚本。

用法：
    uv run python scripts/spot_debug.py
    uv run python scripts/spot_debug.py --front path/to/front.png --rear path/to/rear.png
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np


OUTPUT_DIR = Path("dataset")
MOCK_DIR = Path.home() / ".dcpam" / "mock"

GAUSSIAN_KERNEL = 9
GAUSSIAN_SIGMA = 2.0
THRESHOLD_RATIO = 0.95
MIN_SPOT_AREA = 500


def _debug_single(
    image: np.ndarray,
    name: str,
    out: Path,
    threshold_ratio: float,
    min_area: int,
) -> tuple[float, float]:
    """对单张灰度图执行光斑提取，保存每一步中间结果到 out/。"""
    out.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(out / "01_original.png"), image)

    blurred = cv2.GaussianBlur(image, (GAUSSIAN_KERNEL, GAUSSIAN_KERNEL), GAUSSIAN_SIGMA)
    cv2.imwrite(str(out / "02_blurred.png"), blurred)

    max_val = float(np.max(blurred))
    threshold = max_val * threshold_ratio
    mask = (blurred > threshold).astype(np.uint8) * 255
    cv2.imwrite(str(out / "03_binary_mask.png"), mask)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    labels_vis = np.zeros((*image.shape, 3), dtype=np.uint8)
    rng = np.random.default_rng(42)
    colors = rng.integers(80, 255, size=(num_labels, 3))
    for i in range(1, num_labels):
        labels_vis[labels == i] = colors[i]
    cv2.imwrite(str(out / "04_connected_components.png"), labels_vis)

    best_label = -1
    best_area = 0
    print(f"\n  [{name}] max_val={max_val:.0f}  threshold={threshold:.1f}  components={num_labels - 1}")
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        cx, cy = centroids[i]
        print(f"    component {i}: area={area}  centroid=({cx:.1f}, {cy:.1f})")
        if area >= min_area and area > best_area:
            best_area = area
            best_label = i

    if best_label == -1:
        print(f"  [{name}] WARNING: 未找到面积 >= {min_area} 的连通域，回退全局重心")
        region_mask = mask > 0
    else:
        region_mask = labels == best_label

    ys, xs = np.where(region_mask)
    weights = blurred[ys, xs].astype(np.float64)
    total = weights.sum()
    u = float((xs * weights).sum() / total)
    v = float((ys * weights).sum() / total)
    print(f"  [{name}] spot center: ({u:.1f}, {v:.1f})  area={len(ys)}")

    marked = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    cu, cv_ = int(round(u)), int(round(v))
    cv2.drawMarker(marked, (cu, cv_), (0, 0, 255), cv2.MARKER_CROSS, 40, 2)
    cv2.circle(marked, (cu, cv_), 30, (0, 255, 0), 2)
    cv2.putText(marked, f"({u:.1f}, {v:.1f})", (cu + 15, cv_ - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.imwrite(str(out / "05_result.png"), marked)

    return u, v


def main() -> None:
    parser = argparse.ArgumentParser(description="光斑提取调试 — 保存中间步骤")
    parser.add_argument("--front", type=str, default=str(MOCK_DIR / "front.png"))
    parser.add_argument("--rear", type=str, default=str(MOCK_DIR / "rear.png"))
    parser.add_argument("--threshold", type=float, default=THRESHOLD_RATIO,
                        help=f"阈值比例 (default: {THRESHOLD_RATIO})")
    parser.add_argument("--min-area", type=int, default=MIN_SPOT_AREA,
                        help=f"最小连通域面积 (default: {MIN_SPOT_AREA})")
    args = parser.parse_args()

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    for role, path_str in [("front", args.front), ("rear", args.rear)]:
        path = Path(path_str)
        if not path.exists():
            print(f"  [ERROR] 图片不存在: {path}")
            continue
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"  [ERROR] 图片读取失败: {path}")
            continue
        _debug_single(img, role, OUTPUT_DIR / role, args.threshold, args.min_area)

    print(f"\n  输出目录: {OUTPUT_DIR.resolve()}/")
    print("  每张图片的中间步骤:")
    print("    01_original.png       — 原始灰度图")
    print("    02_blurred.png        — 高斯模糊后")
    print("    03_binary_mask.png    — 二值化掩码")
    print("    04_connected_components.png — 连通域标记")
    print("    05_result.png         — 最终标注结果")


if __name__ == "__main__":
    main()
