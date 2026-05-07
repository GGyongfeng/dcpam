from __future__ import annotations

import numpy as np

from ..config import CameraIntrinsics, GeometryConfig
from ..types import Point2D, Point3D


def back_project(
    pixel: Point2D,
    intrinsics: CameraIntrinsics,
    geometry: GeometryConfig,
) -> Point3D:
    """像素坐标 → 相机坐标系下的三维点 (SIMPLE_RADIAL 去畸变 + Zs 缩放)。"""
    K_inv = np.linalg.inv(intrinsics.k_matrix())
    p_homo = np.array([pixel.u, pixel.v, 1.0])
    p_norm = K_inv @ p_homo

    p_undist = _undistort_simple_radial(p_norm[:2], intrinsics.distortion)
    point_3d = geometry.zs * np.array([p_undist[0], p_undist[1], 1.0])
    return Point3D.from_array(point_3d)


def _undistort_simple_radial(
    p_dist: np.ndarray, k: float, iterations: int = 5
) -> np.ndarray:
    """SIMPLE_RADIAL 畸变模型迭代去畸变: x_dist = x * (1 + k*r²)。"""
    p = p_dist.copy()
    for _ in range(iterations):
        r2 = p[0] ** 2 + p[1] ** 2
        p = p_dist / (1.0 + k * r2)
    return p
