"""用平均取景框四边形和 PnP 求解取景框坐标系位姿。"""
from __future__ import annotations

import argparse
import csv
import tomllib
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from dcpam_cv.config import AppConfig, load_config
from dcpam_cv.path import DCPAMPaths
from dcpam_cv.steps.frame_pose import FramePoseEstimate, FramePoseEstimator
from dcpam_cv.types import ImageQuadrilateral, Point2D


class FramePoseRecord(BaseModel):
    """用于保存脚本输出 CSV 的位姿记录。"""
    role: str
    frame_width_mm: float
    frame_height_mm: float
    center_x_camera_mm: float
    center_y_camera_mm: float
    center_z_camera_mm: float
    normal_x_camera: float
    normal_y_camera: float
    normal_z_camera: float
    reprojection_error_px: float


class FramePoseCalibrationRunner:
    """读取平均四边形、执行 PnP、写入统一配置。"""

    def __init__(
        self,
        frame_dir: Path,
        config_path: Path,
        output_csv: Path,
        frame_width_mm: float,
        frame_height_mm: float,
    ) -> None:
        self.frame_dir = frame_dir
        self.config_path = config_path
        self.output_csv = output_csv
        self.estimator = FramePoseEstimator(frame_width_mm, frame_height_mm)
        self.frame_width_mm = frame_width_mm
        self.frame_height_mm = frame_height_mm

    def run(self) -> list[FramePoseRecord]:
        """求解前后取景框位姿并写入结果。"""
        config = load_config(self.config_path)
        front = self._estimate("front", config)
        rear = self._estimate("rear", config)
        records = [
            self._record("front", front),
            self._record("rear", rear),
        ]
        self._write_config(front, rear)
        self._write_csv(records)
        return records

    def _estimate(self, role: str, config: AppConfig) -> FramePoseEstimate:
        corners = _read_average_quadrilateral(
            self.frame_dir / role / "rectangle_detection" / "average_inner_quadrilateral.csv",
        )
        intrinsics = config.calibration.front_camera if role == "front" else config.calibration.rear_camera
        return self.estimator.estimate(corners, intrinsics)

    def _record(self, role: str, estimate: FramePoseEstimate) -> FramePoseRecord:
        rotation = estimate.pose.rotation_matrix()
        normal = rotation @ [0.0, 0.0, 1.0]
        translation = estimate.pose.translation
        return FramePoseRecord(
            role=role,
            frame_width_mm=self.frame_width_mm,
            frame_height_mm=self.frame_height_mm,
            center_x_camera_mm=translation.x,
            center_y_camera_mm=translation.y,
            center_z_camera_mm=translation.z,
            normal_x_camera=float(normal[0]),
            normal_y_camera=float(normal[1]),
            normal_z_camera=float(normal[2]),
            reprojection_error_px=estimate.reprojection_error_px,
        )

    def _write_config(self, front: FramePoseEstimate, rear: FramePoseEstimate) -> None:
        raw = _read_toml(self.config_path)
        calibration = raw.setdefault("calibration", {})
        calibration.pop("frames", None)
        surfaces = calibration.setdefault("frame_surfaces", {})
        surfaces["front_frame_pnp"] = _surface_config(front, self.frame_width_mm, self.frame_height_mm)
        surfaces["rear_frame_pnp"] = _surface_config(rear, self.frame_width_mm, self.frame_height_mm)
        self.config_path.write_text(_render_toml(raw), encoding="utf-8")

    def _write_csv(self, records: list[FramePoseRecord]) -> None:
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.output_csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(FramePoseRecord.model_fields))
            writer.writeheader()
            for record in records:
                writer.writerow(record.model_dump())


def _read_average_quadrilateral(path: Path) -> ImageQuadrilateral:
    with path.open(newline="", encoding="utf-8") as file:
        row = next(csv.DictReader(file))
    return ImageQuadrilateral(
        top_left=Point2D(u=float(row["top_left_x"]), v=float(row["top_left_y"])),
        top_right=Point2D(u=float(row["top_right_x"]), v=float(row["top_right_y"])),
        bottom_right=Point2D(u=float(row["bottom_right_x"]), v=float(row["bottom_right_y"])),
        bottom_left=Point2D(u=float(row["bottom_left_x"]), v=float(row["bottom_left_y"])),
    )


def _surface_config(estimate: FramePoseEstimate, width_mm: float, height_mm: float) -> dict:
    rotation = estimate.pose.rotation_matrix()
    translation = estimate.pose.translation_vector()
    normal = _unit(rotation[:, 2])
    corners = _frame_corners(rotation, translation, width_mm, height_mm)
    return {
        "method": "pnp_frame_pose",
        "width_mm": width_mm,
        "height_mm": height_mm,
        "point": _vector(translation),
        "x_axis": _vector(_unit(rotation[:, 0])),
        "y_axis": _vector(_unit(rotation[:, 1])),
        "normal": _vector(normal),
        "d": -float(normal @ translation),
        "corners": [_vector(corner) for corner in corners],
        "reprojection_error_px": estimate.reprojection_error_px,
    }


def _frame_corners(
    rotation: np.ndarray,
    translation: np.ndarray,
    width_mm: float,
    height_mm: float,
) -> np.ndarray:
    half_width = width_mm / 2.0
    half_height = height_mm / 2.0
    local = np.array(
        [
            [-half_width, -half_height, 0.0],
            [half_width, -half_height, 0.0],
            [half_width, half_height, 0.0],
            [-half_width, half_height, 0.0],
        ],
        dtype=np.float64,
    )
    return (rotation @ local.T).T + translation


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / float(np.linalg.norm(vector))


def _vector(vector: np.ndarray) -> list[float]:
    return [float(value) for value in vector]


def _read_toml(path: Path) -> dict:
    with path.open("rb") as file:
        return tomllib.load(file)


def _render_toml(data: dict) -> str:
    return _render_section("", data).strip() + "\n"


def _render_section(prefix: str, data: dict) -> str:
    scalar_lines = []
    child_blocks = []
    for key, value in data.items():
        if isinstance(value, dict):
            name = f"{prefix}.{key}" if prefix else key
            child_blocks.append(_render_section(name, value))
        else:
            scalar_lines.append(f"{key} = {_render_value(value)}")

    blocks = []
    if prefix and scalar_lines:
        blocks.append("\n".join([f"[{prefix}]", *scalar_lines]))
    elif scalar_lines:
        blocks.append("\n".join(scalar_lines))
    blocks.extend(block for block in child_blocks if block)
    return "\n\n".join(blocks)


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return _render_list(value)
    return str(value)


def _render_list(values: list) -> str:
    if values and all(isinstance(item, list) for item in values):
        rows = [f"    {_render_list(row)}," for row in values]
        return "[\n" + "\n".join(rows) + "\n]"
    return "[" + ", ".join(_render_value(value) for value in values) + "]"


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="用 PnP 求解前后取景框坐标系位姿")
    parser.add_argument("--frame-dir", type=Path, default=Path("dataset/frame"))
    parser.add_argument("--config", type=Path, default=DCPAMPaths().config_file)
    parser.add_argument("--output", type=Path, default=Path("docs/design/frame-pose-pnp-results.csv"))
    parser.add_argument("--width-mm", type=float, default=22.0)
    parser.add_argument("--height-mm", type=float, default=17.0)
    args = parser.parse_args()

    records = FramePoseCalibrationRunner(
        frame_dir=args.frame_dir,
        config_path=args.config,
        output_csv=args.output,
        frame_width_mm=args.width_mm,
        frame_height_mm=args.height_mm,
    ).run()
    for record in records:
        print(record.model_dump())
    print(f"输出 CSV: {args.output}")
    print(f"已更新配置: {args.config}")


if __name__ == "__main__":
    main()
