from __future__ import annotations

import numpy as np

from ..config import PlaneConfig
from ..types import Point3D


def mirror_transform(point: Point3D, reflection_plane: PlaneConfig) -> Point3D:
    """点关于反射平面做镜像。"""
    p = point.to_array()
    normal = np.array(reflection_plane.normal, dtype=np.float64)
    signed_distance = float(normal @ p + reflection_plane.d)
    return Point3D.from_array(p - 2.0 * signed_distance * normal)
