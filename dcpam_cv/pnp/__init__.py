"""PnP 标定：取景框图片 → 内层四边形 → 相机⇄取景框位姿 → camera⇄device 变换。"""
from .device_convention import DeviceFrameConvention, PnpDeviceConvention, load_pnp_convention
from .pose import FramePoseEstimate, FramePoseEstimator
from .rectangle import (
    FrameRectangleAnnotator,
    InnerQuadrilateral,
)

__all__ = [
    "DeviceFrameConvention",
    "FramePoseEstimate",
    "FramePoseEstimator",
    "FrameRectangleAnnotator",
    "InnerQuadrilateral",
    "PnpDeviceConvention",
    "load_pnp_convention",
]
