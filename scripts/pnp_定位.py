"""一站式 PnP 定位入口。

输入：一个 frame 目录，下含 front/ 和 rear/ 两个子目录。
流程：内层四边形检测（dcpam_cv.pnp.FrameRectangleAnnotator）
      → 平面 PnP 求解（dcpam_cv.pnp.FramePoseEstimator）
      → 把相机系下取景框平面 + camera_to_device 刚体变换写回 config.toml。
"""
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import numpy as np

from dcpam_cv.config import load_config
from dcpam_cv.path import DCPAMPaths
from dcpam_cv.pnp import (
    DeviceFrameConvention,
    FramePoseEstimate,
    FramePoseEstimator,
    FrameRectangleAnnotator,
    load_pnp_convention,
)


def run(frame_dir: Path, config_path: Path, pnp_path: Path) -> None:
    averages = FrameRectangleAnnotator(frame_dir).run()
    print(f"四边形检测完成: {frame_dir}")

    convention = load_pnp_convention(pnp_path)
    estimator = FramePoseEstimator(convention.frame_width_mm, convention.frame_height_mm)
    config = load_config(config_path)

    estimates: dict[str, FramePoseEstimate] = {}
    for role in ("front", "rear"):
        intrinsics = config.calibration.front_camera if role == "front" else config.calibration.rear_camera
        estimates[role] = estimator.estimate(averages[role].to_image_quadrilateral(), intrinsics)

    _write_config(config_path, estimates, convention)
    _print_summary(estimates)
    print(f"已更新配置: {config_path}")


def _write_config(
    config_path: Path,
    estimates: dict[str, FramePoseEstimate],
    convention,
) -> None:
    with config_path.open("rb") as file:
        raw = tomllib.load(file)
    calibration = raw.setdefault("calibration", {})
    calibration.pop("frames", None)
    surfaces = calibration.setdefault("frame_surfaces", {})
    surfaces["front_frame_pnp"] = _surface_config(estimates["front"])
    surfaces["rear_frame_pnp"] = _surface_config(estimates["rear"])
    calibration["front_camera_to_device"] = _camera_to_device(estimates["front"], convention.front)
    calibration["rear_camera_to_device"] = _camera_to_device(estimates["rear"], convention.rear)
    config_path.write_text(_render_toml(raw), encoding="utf-8")


def _surface_config(estimate: FramePoseEstimate) -> dict:
    rotation = estimate.pose.rotation_matrix()
    translation = estimate.pose.translation_vector()
    normal = _unit(rotation[:, 2])
    return {
        "method": "pnp_frame_pose",
        "point": _vector(translation),
        "normal": _vector(normal),
        "d": -float(normal @ translation),
    }


def _camera_to_device(estimate: FramePoseEstimate, device: DeviceFrameConvention) -> dict:
    """把 PnP 给出的 frame→camera 姿态和设备端约定拼成 camera→device 刚体变换。"""
    R_pnp = estimate.pose.rotation_matrix()
    t_pnp = estimate.pose.translation_vector()

    z_dev = _unit(np.array(device.normal, dtype=np.float64))
    x_dev = _unit(np.array(device.x_axis, dtype=np.float64))
    x_dev = _unit(x_dev - (x_dev @ z_dev) * z_dev)
    y_dev = np.cross(z_dev, x_dev)
    B_dev = np.column_stack([x_dev, y_dev, z_dev])

    p_dev_center = np.array(device.point, dtype=np.float64)
    R_cam_to_dev = (R_pnp @ B_dev.T).T
    t_cam_to_dev = p_dev_center - R_cam_to_dev @ t_pnp

    return {
        "rotation": [_vector(row) for row in R_cam_to_dev],
        "translation": _vector(t_cam_to_dev),
    }


def _print_summary(estimates: dict[str, FramePoseEstimate]) -> None:
    for role, estimate in estimates.items():
        translation = estimate.pose.translation
        rotation = estimate.pose.rotation_matrix()
        normal = rotation @ [0.0, 0.0, 1.0]
        print(
            f"{role}: center=({translation.x:.4f}, {translation.y:.4f}, {translation.z:.4f}) mm, "
            f"normal=({normal[0]:.4f}, {normal[1]:.4f}, {normal[2]:.4f}), "
            f"reproj={estimate.reprojection_error_px:.2f}px",
        )


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / float(np.linalg.norm(vector))


def _vector(vector: np.ndarray) -> list[float]:
    return [float(value) for value in vector]


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
    parser = argparse.ArgumentParser(description="一站式 PnP 定位：检测 + 求解 + 写回 config.toml")
    parser.add_argument(
        "--frame-dir",
        type=Path,
        required=True,
        help="包含 front/ 和 rear/ 两个子目录的取景框根目录",
    )
    parser.add_argument("--config", type=Path, default=DCPAMPaths().config_file)
    parser.add_argument("--pnp", type=Path, default=Path("pnp.toml"))
    args = parser.parse_args()

    run(args.frame_dir, args.config, args.pnp)


if __name__ == "__main__":
    main()
