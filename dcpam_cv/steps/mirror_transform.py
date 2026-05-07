from __future__ import annotations

import numpy as np

from ..config import GeometryConfig
from ..types import Point3D


def mirror_transform(point: Point3D, geometry: GeometryConfig, scale: float = 1.0) -> Point3D:
    """镜面反射变换：绕 Y 轴通过 rotation_center 旋转 scale*θ。

    scale=1 用于前相机 (θ)，scale=2 用于后相机 (2θ)。
    θ=0 时退化为 identity。
    """
    theta = geometry.rotation_angle * scale
    if theta == 0.0:
        return point

    c = np.array(geometry.rotation_center)
    p = point.to_array() - c

    cos_t, sin_t = np.cos(theta), np.sin(theta)
    R_y = np.array([
        [ cos_t, 0, sin_t],
        [     0, 1,     0],
        [-sin_t, 0, cos_t],
    ])

    return Point3D.from_array(R_y @ p + c)
