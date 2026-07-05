from __future__ import annotations

import numpy as np

from .config import (
    CalibrationConfig,
    DeviceReflectionGeometryConfig,
    FrameSurfaceConfig,
    GeometryConfig,
    PlaneConfig,
    RigidTransformConfig,
)
from .types import Point3D


class RigidTransform:
    """刚体变换 p_out = R @ p_in + t。"""

    def __init__(self, rotation: np.ndarray, translation: np.ndarray) -> None:
        self.rotation = np.asarray(rotation, dtype=np.float64)
        self.translation = np.asarray(translation, dtype=np.float64)

    @classmethod
    def from_config(cls, config: RigidTransformConfig) -> "RigidTransform":
        return cls(np.array(config.rotation, dtype=np.float64), np.array(config.translation, dtype=np.float64))

    def point(self, value: Point3D) -> Point3D:
        """把 in 坐标系下的点变换到 out 坐标系。"""
        return Point3D.from_array(self.rotation @ value.to_array() + self.translation)

    def compose(self, inner: "RigidTransform") -> "RigidTransform":
        """返回 self ∘ inner：先施加 inner，再施加 self。"""
        return RigidTransform(
            self.rotation @ inner.rotation,
            self.rotation @ inner.translation + self.translation,
        )


class OpticalGeometry:
    """当前 pipeline 使用的几何对象，全部位于设备坐标系（=前取景框局部系）下。"""

    def __init__(self, calibration: CalibrationConfig, geometry: GeometryConfig) -> None:
        front_frame = calibration.frame_surfaces.front_frame_pnp
        rear_frame = calibration.frame_surfaces.rear_frame_pnp
        if front_frame is None or rear_frame is None:
            raise ValueError("配置缺少 PnP 实像面，无法构建光学几何")
        if calibration.front_camera_to_frame is None or calibration.rear_camera_to_frame is None:
            raise ValueError("配置缺少 camera_to_frame 变换，先跑 scripts/pnp/pnp_定位.py")
        if geometry.rear_to_front is None:
            raise ValueError("配置缺少 geometry.rear_to_front 装配变换")

        self.front_image_real = _plane_from_frame(front_frame)
        self.rear_image_real = _plane_from_frame(rear_frame)

        # 前框局部系即设备系原点，故 camera→设备系 = camera→前框局部系。
        self.front_camera_to_device = RigidTransform.from_config(calibration.front_camera_to_frame)
        # 后相机点先到后框局部系，再经装配变换 rear_to_front 并入前框系（=设备系）。
        self.rear_camera_to_frame = RigidTransform.from_config(calibration.rear_camera_to_frame)
        self.rear_to_front = RigidTransform.from_config(geometry.rear_to_front)
        self.rear_camera_to_device = self.rear_to_front.compose(self.rear_camera_to_frame)

        self.front_reflection = _plane_from_device(geometry.front_reflection)
        self.rear_reflection = _plane_from_device(geometry.rear_reflection)
        self.target_point = _probe_target(geometry)


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


def _probe_target(geometry: GeometryConfig) -> Point3D:
    root_x, root_y, root_z = geometry.probe_rod.root
    return Point3D(
        x=root_x,
        y=root_y,
        z=root_z - geometry.probe_rod.length_mm,
    )


def _unit(vector: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise ValueError("无法归一化零向量")
    return vector / length
