from __future__ import annotations

import numpy as np

from .config import (
    CalibrationConfig,
    DeviceConfig,
    DeviceFrameGeometryConfig,
    DeviceReflectionGeometryConfig,
    FrameSurfaceConfig,
    PlaneConfig,
)
from .types import Point3D


class DeviceToCameraTransform:
    """设备坐标系到单个相机坐标系的刚体变换。"""

    def __init__(
        self,
        device_frame: DeviceFrameGeometryConfig,
        camera_frame: FrameSurfaceConfig,
    ) -> None:
        source_rotation = _basis(
            device_frame.rect_corners[1],
            device_frame.rect_corners[0],
            device_frame.rect_corners[3],
            device_frame.normal,
        )
        target_rotation = _basis(
            camera_frame.x_axis,
            (0.0, 0.0, 0.0),
            camera_frame.y_axis,
            camera_frame.normal,
        )
        self.rotation = target_rotation @ source_rotation.T
        self.translation = np.array(camera_frame.point, dtype=np.float64) - self.rotation @ np.array(
            device_frame.point,
            dtype=np.float64,
        )

    def point(self, value: tuple[float, float, float]) -> np.ndarray:
        """变换设备坐标系下的点。"""
        return self.rotation @ np.array(value, dtype=np.float64) + self.translation

    def vector(self, value: tuple[float, float, float]) -> np.ndarray:
        """变换设备坐标系下的方向向量。"""
        return _unit(self.rotation @ np.array(value, dtype=np.float64))


class CameraToDeviceTransform:
    """单个相机坐标系到设备坐标系的刚体变换。"""

    def __init__(
        self,
        device_frame: DeviceFrameGeometryConfig,
        camera_frame: FrameSurfaceConfig,
    ) -> None:
        device_to_camera = DeviceToCameraTransform(device_frame, camera_frame)
        self.rotation = device_to_camera.rotation.T
        self.translation = -self.rotation @ device_to_camera.translation

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

        self.front_image_real = _plane_from_frame(front_frame)
        self.rear_image_real = _plane_from_frame(rear_frame)
        self.front_camera_to_device = CameraToDeviceTransform(device.geometry.front_frame, front_frame)
        self.rear_camera_to_device = CameraToDeviceTransform(device.geometry.rear_frame, rear_frame)
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


def _basis(
    x_point: tuple[float, float, float],
    origin: tuple[float, float, float],
    y_point: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> np.ndarray:
    x_axis = _unit(np.array(x_point, dtype=np.float64) - np.array(origin, dtype=np.float64))
    z_axis = _unit(np.array(normal, dtype=np.float64))
    y_axis = _unit(np.array(y_point, dtype=np.float64) - np.array(origin, dtype=np.float64))
    return np.column_stack([x_axis, y_axis, z_axis])


def _unit(vector: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise ValueError("无法归一化零向量")
    return vector / length
