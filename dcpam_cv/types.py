from __future__ import annotations

from datetime import datetime

import numpy as np
from pydantic import BaseModel


class Point2D(BaseModel):
    """像素坐标。"""
    u: float
    v: float


class Point3D(BaseModel):
    """三维空间坐标。"""
    x: float
    y: float
    z: float

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    @classmethod
    def from_array(cls, arr: np.ndarray) -> Point3D:
        return cls(x=float(arr[0]), y=float(arr[1]), z=float(arr[2]))


class ImageQuadrilateral(BaseModel):
    """图像中的四边形角点。"""
    top_left: Point2D
    top_right: Point2D
    bottom_right: Point2D
    bottom_left: Point2D

    def to_array(self) -> np.ndarray:
        """按左上、右上、右下、左下返回像素点。"""
        return np.array(
            [
                [self.top_left.u, self.top_left.v],
                [self.top_right.u, self.top_right.v],
                [self.bottom_right.u, self.bottom_right.v],
                [self.bottom_left.u, self.bottom_left.v],
            ],
            dtype=np.float64,
        )


class Pose3D(BaseModel):
    """刚体位姿: P_target = R @ P_source + t。"""
    rotation: list[list[float]]
    translation: Point3D

    def rotation_matrix(self) -> np.ndarray:
        return np.array(self.rotation, dtype=np.float64)

    def translation_vector(self) -> np.ndarray:
        return self.translation.to_array()


class SpotPair(BaseModel):
    """前后相机光斑像素坐标对。"""
    front: Point2D
    rear: Point2D


class LaserAxis(BaseModel):
    """激光轴线（两点定义），均在设备坐标系下。"""
    front: Point3D
    rear: Point3D

    def direction(self) -> np.ndarray:
        return self.rear.to_array() - self.front.to_array()


class MeasurementResult(BaseModel):
    """单次测量结果。"""
    model_config = {"arbitrary_types_allowed": True}

    uid: str
    timestamp: datetime
    distance: float
    laser_axis: LaserAxis
    target_point: Point3D
    spots: SpotPair

    def to_record(self) -> dict:
        """返回可 JSON 序列化的字典。"""
        return {
            "uid": self.uid,
            "timestamp": self.timestamp.isoformat(),
            "distance_mm": self.distance,
            "spots": self.spots.model_dump(),
            "laser_axis": self.laser_axis.model_dump(),
            "target_point": self.target_point.model_dump(),
        }
