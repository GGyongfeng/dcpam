"""pnp.toml 里的设备端约定：每个取景框在设备系下的中心、法向、x 轴。"""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class DeviceFrameConvention(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    x_axis: tuple[float, float, float]


class PnpDeviceConvention(BaseModel):
    frame_width_mm: float
    frame_height_mm: float
    front: DeviceFrameConvention
    rear: DeviceFrameConvention


def load_pnp_convention(path: Path) -> PnpDeviceConvention:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    frame = raw["frame"]
    return PnpDeviceConvention(
        frame_width_mm=float(frame["width_mm"]),
        frame_height_mm=float(frame["height_mm"]),
        front=DeviceFrameConvention(**raw["front_frame"]),
        rear=DeviceFrameConvention(**raw["rear_frame"]),
    )
