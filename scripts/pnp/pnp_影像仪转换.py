"""把影像仪测量的成像面标定点转换到各成像面的设备局部坐标系。

背景
----
前/后两个成像面分别在影像仪下测量（各自独立的测量坐标系，Z 轴向上）。
每个成像面上贴有 5 个圆点，测量顺序为：左上、右上、中、左下、右下。
表格里同时给出了取景框四条边（up/down/left/right）的起点与方向向量，
用于恢复"设备坐标系"的朝向与取景框中心。

设备局部坐标系（每个成像面各建一套，原点在各自取景框矩形中心）
    +X：沿上下边框，从右往左
    +Y：沿左右边框，从上到下
    +Z：右手系，X × Y（出平面）
    原点：四条边框直线两两相交得到的矩形中心

输出
----
dataset/pnp/imaging_plane_points_device.csv
    每行一个圆点在其成像面设备局部坐标系下的坐标（mm）。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import openpyxl

POINT_LABELS = ["左上", "右上", "中", "左下", "右下"]


def _load_block(rows: list[tuple], header_key: str) -> tuple[np.ndarray, dict[str, dict]]:
    """定位以 header_key（'1 号'/'2 号'）开头的数据块，返回圆点坐标与四边框。"""
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == header_key)

    points = []
    for r in rows[header_idx + 1 : header_idx + 6]:
        points.append([float(r[1]), float(r[2]), float(r[3])])

    edges: dict[str, dict] = {}
    for r in rows[header_idx + 1 : header_idx + 5]:
        name = r[7]
        edges[name] = {
            "start": np.array([float(r[8]), float(r[9]), float(r[10])]),
            "dir": np.array([float(r[11]), float(r[12]), float(r[13])]),
        }
    return np.array(points), edges


def _device_axes(edges: dict[str, dict]) -> np.ndarray:
    """由四条边框方向恢复设备坐标轴（影像仪系下的列向量 [X̂ Ŷ Ẑ]）。

    影像仪从圆点面正上方（Z 向上）测量，而相机是透过成像面从另一侧拍摄，
    两个视角对面内 X 方向的感知恰好左右镜像。为让 object points 与相机实际
    看到的成像面一致（否则 PnP 解出的成像面法线会指向 −Z，与设备规格
    “Z 正 = 远离相机”相反，并使测量重复度显著劣化），这里把 X 轴取到
    相机视角方向，并同步翻转 Z 以保持右手系（等价于绕 Y 轴转 180°）。
    """
    # 影像仪系里 +X 沿上下边框、从右往左：down 边方向指向左侧，up 边方向指向右侧需取反。
    x_axis_meas = -edges["up"]["dir"] + edges["down"]["dir"]
    x_axis_meas /= np.linalg.norm(x_axis_meas)

    # +Y 沿左右边框、从上到下：left/right 边方向都指向下方。
    y_axis = edges["left"]["dir"] + edges["right"]["dir"]
    y_axis -= np.dot(y_axis, x_axis_meas) * x_axis_meas  # 对 X 正交化
    y_axis /= np.linalg.norm(y_axis)

    # 相机视角与影像仪视角对 X 左右镜像：翻 X；同步翻 Z 保持右手系。
    x_axis = -x_axis_meas
    z_axis = np.cross(x_axis, y_axis)
    return np.column_stack([x_axis, y_axis, z_axis])


def _rectangle_center(edges: dict[str, dict], z_value: float) -> np.ndarray:
    """四条边框直线两两相交得到 4 个角点，取平均作为矩形中心（影像仪系）。"""

    def intersect(name_a: str, name_b: str) -> np.ndarray:
        p1, d1 = edges[name_a]["start"][:2], edges[name_a]["dir"][:2]
        p2, d2 = edges[name_b]["start"][:2], edges[name_b]["dir"][:2]
        matrix = np.array([d1, -d2]).T
        t = np.linalg.solve(matrix, p2 - p1)
        return p1 + t[0] * d1

    corners = [
        intersect("up", "left"),
        intersect("up", "right"),
        intersect("down", "right"),
        intersect("down", "left"),
    ]
    center_xy = np.mean(corners, axis=0)
    return np.array([center_xy[0], center_xy[1], z_value])


def convert(xlsx_path: Path, out_path: Path) -> None:
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    rows = list(workbook["Sheet1"].iter_rows(values_only=True))

    records = []
    # 影像仪按镜子编号测量：1 号镜、2 号镜。安装时 1 号镜在后、2 号镜在前，
    # 故 1 号 → 设备 rear，2 号 → 设备 front。
    for plane, header_key in [("rear", "1 号"), ("front", "2 号")]:
        points, edges = _load_block(rows, header_key)
        rotation = _device_axes(edges)
        origin = _rectangle_center(edges, z_value=float(points[:, 2].mean()))

        local = (points - origin) @ rotation  # p_device = Rᵀ (P - O)
        for idx, coord in enumerate(local):
            records.append(
                {
                    "plane": plane,
                    "point": idx + 1,
                    "label": POINT_LABELS[idx],
                    "x_mm": round(float(coord[0]), 4),
                    "y_mm": round(float(coord[1]), 4),
                    "z_mm": round(float(coord[2]), 4),
                }
            )

        print(f"[{plane}] 矩形中心(影像仪系) = {np.round(origin, 4)}")
        print(f"[{plane}] X̂={np.round(rotation[:, 0], 5)}  "
              f"Ŷ={np.round(rotation[:, 1], 5)}  Ẑ={np.round(rotation[:, 2], 5)}")
        rms_z = float(np.sqrt(np.mean(local[:, 2] ** 2)))
        print(f"[{plane}] 圆点离面 RMS = {rms_z:.4f} mm（应接近 0，验证平面性）")

    with out_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=["plane", "point", "label", "x_mm", "y_mm", "z_mm"]
        )
        writer.writeheader()
        writer.writerows(records)
    print(f"已写出 {len(records)} 行 → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xlsx", type=Path, default=Path("dataset/pnp/20260702.xlsx")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("dataset/pnp/imaging_plane_points_device.csv")
    )
    args = parser.parse_args()
    convert(args.xlsx, args.out)


if __name__ == "__main__":
    main()
