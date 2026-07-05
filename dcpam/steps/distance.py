from __future__ import annotations

import numpy as np

from ..types import LaserAxis, Point3D


def point_to_line_distance(target: Point3D, axis: LaserAxis) -> float:
    """点到直线（激光轴线）的距离: H = |L × w| / |L|。"""
    pf = axis.front.to_array()
    pr = axis.rear.to_array()
    pt = target.to_array()

    L = pr - pf
    w = pt - pf

    cross = np.cross(L, w)
    return float(np.linalg.norm(cross) / np.linalg.norm(L))
