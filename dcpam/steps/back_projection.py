from __future__ import annotations

import numpy as np

from ..config import CameraIntrinsics, PlaneConfig
from ..types import Point2D, Point3D


def back_project(
    pixel: Point2D,
    intrinsics: CameraIntrinsics,
    image_plane: PlaneConfig,
) -> Point3D:
    """像素坐标 → 相机射线与成像面交点。"""
    K_inv = np.linalg.inv(intrinsics.k_matrix())
    p_homo = np.array([pixel.u, pixel.v, 1.0])
    p_norm = K_inv @ p_homo

    p_undist = _undistort_opencv(p_norm[:2], intrinsics.distortion_coeffs)
    ray = np.array([p_undist[0], p_undist[1], 1.0], dtype=np.float64)
    return Point3D.from_array(_intersect_ray_with_plane(ray, image_plane))


def _intersect_ray_with_plane(ray: np.ndarray, plane: PlaneConfig) -> np.ndarray:
    """相机光心出发的射线与平面求交。"""
    normal = np.array(plane.normal, dtype=np.float64)
    denominator = float(normal @ ray)
    if abs(denominator) < 1e-12:
        raise ValueError("相机射线与成像面近似平行，无法求交")
    scale = -plane.d / denominator
    return scale * ray


def _undistort_opencv(
    p_dist: np.ndarray,
    coeffs: tuple[float, float, float, float],
    iterations: int = 8,
) -> np.ndarray:
    """OpenCV k1/k2/p1/p2 畸变模型迭代去畸变。"""
    k1, k2, p1, p2 = coeffs
    p = p_dist.copy()
    for _ in range(iterations):
        x, y = p
        r2 = x * x + y * y
        radial = 1.0 + k1 * r2 + k2 * r2 * r2
        tangential = np.array([
            2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x),
            p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y,
        ])
        p = (p_dist - tangential) / radial
    return p
