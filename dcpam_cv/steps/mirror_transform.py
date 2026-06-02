from __future__ import annotations

import numpy as np

from ..config import MirrorConfig
from ..types import Point3D


def mirror_transform(point: Point3D, mirror: MirrorConfig, scale: float = 1.0) -> Point3D:
    """镜面反射变换：绕 Y 轴通过 rotation_center 旋转 scale*θ。"""
    theta = mirror.rotation_angle * scale
    if theta == 0.0:
        return point

    c = np.array(mirror.rotation_center)
    p = point.to_array() - c

    cos_t, sin_t = np.cos(theta), np.sin(theta)
    R_y = np.array([
        [ cos_t, 0, sin_t],
        [     0, 1,     0],
        [-sin_t, 0, cos_t],
    ])

    return Point3D.from_array(R_y @ p + c)
