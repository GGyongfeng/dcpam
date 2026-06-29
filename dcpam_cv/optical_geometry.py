from __future__ import annotations

import numpy as np

from .config import (
    CalibrationConfig,
    CameraToDeviceConfig,
    DeviceConfig,
    DeviceReflectionGeometryConfig,
    FrameSurfaceConfig,
    PlaneConfig,
)
from .types import Point3D


class CameraToDeviceTransform:
    """相机坐标系 → 设备坐标系的刚体变换。直接读 config 里预先算好的 R, t。"""

    def __init__(self, config: CameraToDeviceConfig) -> None:
        self.rotation = np.array(config.rotation, dtype=np.float64)
        self.translation = np.array(config.translation, dtype=np.float64)

    def point(self, value: Point3D) -> Point3D:
        """将相机坐标系下的点变换到设备坐标系。"""
        point = self.rotation @ value.to_array() + self.translation
        return Point3D.from_array(point)


class OpticalGeometry:
    """当前 pipeline 使用的几何对象，全部位于设备坐标系下。"""

    def __init__(self, calibration: CalibrationConfig, device: DeviceConfig) -> None:
        front_frame = calibration.frame_surfaces.front_frame_pnp
        rear_frame = calibration.frame_surfaces.rear_frame_pnp
        if front_frame is None or rear_frame is None:
            raise ValueError("配置缺少 PnP 实像面，无法构建光学几何")
        if calibration.front_camera_to_device is None or calibration.rear_camera_to_device is None:
            raise ValueError("配置缺少 camera_to_device 变换，先跑 scripts/10_estimate_frame_poses.py")

        self.front_image_real = _plane_from_frame(front_frame)
        self.rear_image_real = _plane_from_frame(rear_frame)
        self.front_camera_to_device = CameraToDeviceTransform(calibration.front_camera_to_device)
        self.rear_camera_to_device = CameraToDeviceTransform(calibration.rear_camera_to_device)
        self.front_reflection = _plane_from_device(device.geometry.front_reflection)
        self.rear_reflection = _plane_from_device(device.geometry.rear_reflection)
        self.target_point = _probe_target(device)


def _plane_from_frame(frame: FrameSurfaceConfig) -> PlaneConfig:
    return PlaneConfig(
        method=frame.method,
        point=frame.point,
        normal=frame.normal,
        d=frame.d,
    )


def _plane_from_device(source: DeviceReflectionGeometryConfig) -> PlaneConfig:
    point = np.array(source.point, dtype=np.float64)
    normal = _unit(np.array(source.normal, dtype=np.float64))
    return PlaneConfig(
        method="device_geometry",
        point=tuple(float(value) for value in point),
        normal=tuple(float(value) for value in normal),
        d=float(-normal @ point),
    )


def _probe_target(device: DeviceConfig) -> Point3D:
    root_x, root_y, root_z = device.geometry.probe_rod.root
    return Point3D(
        x=root_x,
        y=root_y,
        z=root_z - device.geometry.probe_rod.length_mm,
    )


def _unit(vector: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise ValueError("无法归一化零向量")
    return vector / length
