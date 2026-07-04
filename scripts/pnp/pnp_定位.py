"""一站式 PnP 定位入口。

输入：一个 frame 目录，下含 front/ 和 rear/ 两个子目录，每个里面是同一成像面
      不同光照重复拍摄的标定图。
流程：5 圆点圆心检测（dcpam_cv.pnp.CircleCenterDetector）
      → 通用平面 PnP 求解（dcpam_cv.pnp.FramePoseEstimator）
      → 把「相机→各自取景框局部系」写回 config.toml（前后独立，不含装配尺寸）；
        后框→前框（设备系）的 80mm 装配变换以 geometry.rear_to_front 单独维护。
"""
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import numpy as np

from dcpam_cv.config import load_config
from dcpam_cv.path import DCPAMPaths
from dcpam_cv.pnp import (
    CircleCenterDetector,
    DeviceFrameConvention,
    FramePoseEstimate,
    FramePoseEstimator,
    load_pnp_convention,
)


def run(frame_dir: Path, config_path: Path, pnp_path: Path) -> None:
    convention = load_pnp_convention(pnp_path)
    config = load_config(config_path)
    detector = CircleCenterDetector()
    estimator = FramePoseEstimator()

    planes = {"front": convention.front, "rear": convention.rear}
    intrinsics = {
        "front": config.calibration.front_camera,
        "rear": config.calibration.rear_camera,
    }

    estimates: dict[str, FramePoseEstimate] = {}
    for role in ("front", "rear"):
        image_points = detector.detect_role(frame_dir / role)
        # front 配 front、rear 配 rear；图内 5 点顺序未知，用排列择优对应。
        estimate, _ = estimator.estimate_unordered(
            planes[role].object_points_array(),
            image_points,
            intrinsics[role],
        )
        estimates[role] = estimate

    _write_config(config_path, estimates, planes)
    _print_summary(estimates)
    print(f"已更新配置: {config_path}")


def _write_config(
    config_path: Path,
    estimates: dict[str, FramePoseEstimate],
    planes: dict[str, DeviceFrameConvention],
) -> None:
    with config_path.open("rb") as file:
        raw = tomllib.load(file)
    calibration = raw.setdefault("calibration", {})
    calibration.pop("frames", None)
    # 清除解耦前的旧键（相机→设备系），避免 round-trip 残留。
    calibration.pop("front_camera_to_device", None)
    calibration.pop("rear_camera_to_device", None)
    surfaces = calibration.setdefault("frame_surfaces", {})
    surfaces["front_frame_pnp"] = _surface_config(estimates["front"])
    surfaces["rear_frame_pnp"] = _surface_config(estimates["rear"])
    calibration["front_camera_to_frame"] = _camera_to_frame(estimates["front"], planes["front"])
    calibration["rear_camera_to_frame"] = _camera_to_frame(estimates["rear"], planes["rear"])
    # 注意：后框→前框装配变换 geometry.rear_to_front 属设备物理测量，由人手动填写，
    # 标定脚本不写、不动它。
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


def _camera_to_frame(estimate: FramePoseEstimate, frame: DeviceFrameConvention) -> dict:
    """把 PnP 给出的 frame→camera 姿态拼成 camera→取景框局部系 刚体变换。

    frame.point 为该框局部系原点（前后都取框中心 [0,0,0]）；normal/x_axis 定义
    局部系朝向。装配尺寸（后框相对前框的 80mm 等）不在此处，已解耦到 rear_to_front。
    """
    R_pnp = estimate.pose.rotation_matrix()
    t_pnp = estimate.pose.translation_vector()

    z_dev = _unit(np.array(frame.normal, dtype=np.float64))
    x_dev = _unit(np.array(frame.x_axis, dtype=np.float64))
    x_dev = _unit(x_dev - (x_dev @ z_dev) * z_dev)
    y_dev = np.cross(z_dev, x_dev)
    B_dev = np.column_stack([x_dev, y_dev, z_dev])

    p_frame_center = np.array(frame.point, dtype=np.float64)
    R_cam_to_frame = (R_pnp @ B_dev.T).T
    t_cam_to_frame = p_frame_center - R_cam_to_frame @ t_pnp

    return {
        "rotation": [_vector(row) for row in R_cam_to_frame],
        "translation": _vector(t_cam_to_frame),
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
    parser = argparse.ArgumentParser(description="一站式 PnP 定位：5 圆点检测 + 求解 + 写回 config.toml")
    parser.add_argument(
        "--frame-dir",
        type=Path,
        required=True,
        help="包含 front/ 和 rear/ 两个子目录的成像面标定图根目录",
    )
    parser.add_argument("--config", type=Path, default=DCPAMPaths().config_file)
    parser.add_argument("--pnp", type=Path, default=Path("pnp.toml"))
    args = parser.parse_args()

    run(args.frame_dir, args.config, args.pnp)


if __name__ == "__main__":
    main()
