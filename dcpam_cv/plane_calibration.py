from __future__ import annotations

import numpy as np
from pydantic import BaseModel


class ColmapPose(BaseModel):
    """COLMAP images.txt 风格的单张图片外参。"""
    qw: float
    qx: float
    qy: float
    qz: float
    tx: float
    ty: float
    tz: float


class PlaneData(BaseModel):
    """相机坐标系下的平面。"""
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class ColmapPlanePoses(BaseModel):
    """四个光学平面的 COLMAP 原始外参。"""
    front_image_real: ColmapPose
    rear_image_real: ColmapPose
    front_reflection: ColmapPose
    rear_reflection: ColmapPose


class ColmapPlaneSource(BaseModel):
    """从 COLMAP 外参派生光学平面所需的配置。"""
    translation_scale: float = 10.0
    image_z_offset_mm: float = 2.0
    poses: ColmapPlanePoses


class ColmapPlaneConverter:
    """把 COLMAP 标定板外参转换为算法直接使用的平面。"""

    def __init__(self, translation_scale: float, image_z_offset_mm: float) -> None:
        self.translation_scale = translation_scale
        self.image_z_offset_mm = image_z_offset_mm

    def convert(self, source: ColmapPlaneSource) -> dict[str, PlaneData]:
        """转换四个光学平面。"""
        return {
            "front_image_real": self.image_plane(source.poses.front_image_real),
            "rear_image_real": self.image_plane(source.poses.rear_image_real),
            "front_reflection": self.board_plane(source.poses.front_reflection),
            "rear_reflection": self.board_plane(source.poses.rear_reflection),
        }

    def board_plane(self, pose: ColmapPose) -> PlaneData:
        """标定板 z=0 平面在相机坐标系下的表示。"""
        rotation = _rotation_from_colmap_quaternion(pose)
        normal = _unit(rotation[:, 2])
        point = np.array([pose.tx, pose.ty, pose.tz], dtype=np.float64) * self.translation_scale
        return _plane_from_point_normal(point, normal)

    def image_plane(self, pose: ColmapPose) -> PlaneData:
        """成像面：标定板平面沿相机 +Z 方向偏移。"""
        board = self.board_plane(pose)
        point = np.array(board.point, dtype=np.float64)
        point = point + np.array([0.0, 0.0, self.image_z_offset_mm], dtype=np.float64)
        normal = np.array(board.normal, dtype=np.float64)
        return _plane_from_point_normal(point, normal)


def derive_planes_from_colmap(source: ColmapPlaneSource) -> dict[str, PlaneData]:
    """从 COLMAP 原始外参派生四个光学平面。"""
    converter = ColmapPlaneConverter(source.translation_scale, source.image_z_offset_mm)
    return converter.convert(source)


def _rotation_from_colmap_quaternion(pose: ColmapPose) -> np.ndarray:
    qw, qx, qy, qz = _unit(np.array([pose.qw, pose.qx, pose.qy, pose.qz], dtype=np.float64))
    return np.array(
        [
            [1.0 - 2.0 * qy * qy - 2.0 * qz * qz, 2.0 * qx * qy - 2.0 * qz * qw, 2.0 * qx * qz + 2.0 * qy * qw],
            [2.0 * qx * qy + 2.0 * qz * qw, 1.0 - 2.0 * qx * qx - 2.0 * qz * qz, 2.0 * qy * qz - 2.0 * qx * qw],
            [2.0 * qx * qz - 2.0 * qy * qw, 2.0 * qy * qz + 2.0 * qx * qw, 1.0 - 2.0 * qx * qx - 2.0 * qy * qy],
        ],
        dtype=np.float64,
    )


def _plane_from_point_normal(point: np.ndarray, normal: np.ndarray) -> PlaneData:
    normal = _unit(normal)
    d = -float(normal @ point)
    return PlaneData(point=_tuple(point), normal=_tuple(normal), d=d)


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("零向量不能归一化")
    return vector / norm


def _tuple(vector: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(value) for value in vector)
