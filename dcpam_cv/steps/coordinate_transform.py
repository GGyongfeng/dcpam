from __future__ import annotations

import numpy as np

from ..config import TransformConfig
from ..types import Point3D


def rear_to_front(point_rear: Point3D, transform: TransformConfig) -> Point3D:
    """将后相机坐标系 C2 的点变换到前相机坐标系 C1。"""
    R21 = transform.rotation_matrix()
    t21 = transform.translation_vector()

    R12 = R21.T
    t12 = -R12 @ t21

    p_front = R12 @ point_rear.to_array() + t12
    return Point3D.from_array(p_front)
