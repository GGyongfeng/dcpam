"""pnp.toml 里的设备端约定：每个成像面在设备系下的中心、法向、x 轴，
以及贴在该面上的 5 个圆点在设备局部坐标系下的坐标（PnP 的 object points）。"""
from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
from pydantic import BaseModel


class DeviceFrameConvention(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    x_axis: tuple[float, float, float]
    # 5 圆点在本成像面设备局部坐标系下的坐标(mm)，顺序：左上, 右上, 中, 左下, 右下。
    object_points: list[tuple[float, float, float]]

    def object_points_array(self) -> np.ndarray:
        """返回 (N, 3) 的 object points 数组，供 PnP 求解使用。"""
        return np.array(self.object_points, dtype=np.float64)


class PnpDeviceConvention(BaseModel):
    front: DeviceFrameConvention
    rear: DeviceFrameConvention


def load_pnp_convention(path: Path) -> PnpDeviceConvention:
    with path.open("rb") as file:
        raw = tomllib.load(file)

    def build(section: dict) -> DeviceFrameConvention:
        return DeviceFrameConvention(
            point=section["point"],
            normal=section["normal"],
            x_axis=section["x_axis"],
            object_points=section["points"],
        )

    return PnpDeviceConvention(
        front=build(raw["front_frame"]),
        rear=build(raw["rear_frame"]),
    )
