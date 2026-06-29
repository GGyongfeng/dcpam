"""用平均取景框四边形和 PnP 求解：相机坐标系 ↔ 设备坐标系。

输出物：
- config.toml.calibration.frame_surfaces.{front,rear}_frame_pnp：
  反投影用的相机系平面（point + normal + d）。
- config.toml.calibration.{front,rear}_camera_to_device：
  预先算好的刚体变换 R + t，pipeline 直接消费。

设备端约定（前后框各自在设备系下的中心 / 法向 / x 轴）从 pnp.toml 读入。
"""
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
    """脚本输出 CSV 的位姿记录。"""
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


class DeviceFrameConvention(BaseModel):
    """pnp.toml 里设备端取景框约定。"""
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    x_axis: tuple[float, float, float]


class PnpDeviceConvention(BaseModel):
    frame_width_mm: float
    frame_height_mm: float
    front: DeviceFrameConvention
    rear: DeviceFrameConvention


class FramePoseCalibrationRunner:
    """读取平均四边形，跑 PnP，写入 config.toml。"""

    def __init__(
        self,
        frame_dir: Path,
        config_path: Path,
        pnp_path: Path,
        output_csv: Path,
    ) -> None:
        self.frame_dir = frame_dir
        self.config_path = config_path
        self.pnp_path = pnp_path
        self.output_csv = output_csv
        self.convention = _load_pnp_convention(pnp_path)
        self.estimator = FramePoseEstimator(
            self.convention.frame_width_mm,
            self.convention.frame_height_mm,
        )

    def run(self) -> list[FramePoseRecord]:
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
            frame_width_mm=self.convention.frame_width_mm,
            frame_height_mm=self.convention.frame_height_mm,
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
        surfaces["front_frame_pnp"] = _surface_config(front)
        surfaces["rear_frame_pnp"] = _surface_config(rear)
        calibration["front_camera_to_device"] = _camera_to_device(front, self.convention.front)
        calibration["rear_camera_to_device"] = _camera_to_device(rear, self.convention.rear)
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


def _surface_config(estimate: FramePoseEstimate) -> dict:
    """写到 config.toml 的反投影平面，仅保留 pipeline 需要的字段。"""
    rotation = estimate.pose.rotation_matrix()
    translation = estimate.pose.translation_vector()
    normal = _unit(rotation[:, 2])
    return {
        "method": "pnp_frame_pose",
        "point": _vector(translation),
        "normal": _vector(normal),
        "d": -float(normal @ translation),
    }


def _camera_to_device(
    estimate: FramePoseEstimate,
    device_convention: DeviceFrameConvention,
) -> dict:
    """把 PnP 给出的取景框姿态和"设备端约定"拼成 camera_to_device 刚体变换。

    PnP 输出：取景框坐标系 → 相机坐标系，即 P_cam = R_pnp @ P_frame + t_pnp，
              所以 R_pnp 的三列分别是相机系下的 (x_frame, y_frame, z_frame) 方向。
    设备约定：设备系下框中心 = device.point，z 轴 = device.normal，x 轴 = device.x_axis。
              拼成设备系基矩阵 B_dev = [x_dev, y_dev, z_dev]（列向量）。

    令 R_cam_dev = R_pnp @ B_dev^T，则
        P_cam = R_cam_dev @ (P_dev - device.point) + t_pnp
    => P_dev = R_cam_dev^T @ (P_cam - t_pnp) + device.point
             = R_dev_cam @ P_cam + (device.point - R_dev_cam @ t_pnp)
    其中 R_dev_cam = R_cam_dev^T。这就是 camera → device。
    """
    R_pnp = estimate.pose.rotation_matrix()                # frame -> camera
    t_pnp = estimate.pose.translation_vector()             # frame -> camera

    z_dev = _unit(np.array(device_convention.normal, dtype=np.float64))
    x_dev = _unit(np.array(device_convention.x_axis, dtype=np.float64))
    # 正交化：保证 x_dev ⟂ z_dev
    x_dev = _unit(x_dev - (x_dev @ z_dev) * z_dev)
    y_dev = np.cross(z_dev, x_dev)
    B_dev = np.column_stack([x_dev, y_dev, z_dev])         # device frame basis (columns)

    p_dev_center = np.array(device_convention.point, dtype=np.float64)

    # frame 坐标系到设备坐标系：P_dev = B_dev @ P_frame + p_dev_center
    # 联立：P_cam = R_pnp @ P_frame + t_pnp
    #       P_frame = B_dev^T @ (P_dev - p_dev_center)
    # =>    P_cam = R_pnp @ B_dev^T @ (P_dev - p_dev_center) + t_pnp
    # 反解：P_dev = (R_pnp @ B_dev^T)^T @ (P_cam - t_pnp) + p_dev_center
    R_cam_to_dev = (R_pnp @ B_dev.T).T
    t_cam_to_dev = p_dev_center - R_cam_to_dev @ t_pnp

    return {
        "rotation": [_vector(row) for row in R_cam_to_dev],
        "translation": _vector(t_cam_to_dev),
    }


def _load_pnp_convention(path: Path) -> PnpDeviceConvention:
    raw = _read_toml(path)
    frame = raw["frame"]
    return PnpDeviceConvention(
        frame_width_mm=float(frame["width_mm"]),
        frame_height_mm=float(frame["height_mm"]),
        front=DeviceFrameConvention(**raw["front_frame"]),
        rear=DeviceFrameConvention(**raw["rear_frame"]),
    )


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
    parser = argparse.ArgumentParser(description="用 PnP 求解前后取景框位姿并写入相机⇄设备变换")
    parser.add_argument("--frame-dir", type=Path, default=Path("dataset/frame"))
    parser.add_argument("--config", type=Path, default=DCPAMPaths().config_file)
    parser.add_argument("--pnp", type=Path, default=Path("pnp.toml"))
    parser.add_argument("--output", type=Path, default=Path("docs/design/frame-pose-pnp-results.csv"))
    args = parser.parse_args()

    records = FramePoseCalibrationRunner(
        frame_dir=args.frame_dir,
        config_path=args.config,
        pnp_path=args.pnp,
        output_csv=args.output,
    ).run()
    for record in records:
        print(record.model_dump())
    print(f"输出 CSV: {args.output}")
    print(f"已更新配置: {args.config}")


if __name__ == "__main__":
    main()
