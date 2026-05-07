import tomllib
from pathlib import Path

from pydantic import BaseModel


class SingleCameraHardware(BaseModel):
    """单个相机的硬件参数。"""
    serial: str = ""
    exposure_auto: bool = True
    gain_auto: bool = True
    exposure_time: float | None = None
    gain: float | None = None


class CameraConfig(BaseModel):
    """双相机硬件配置（对应 camera.toml）。"""
    front: SingleCameraHardware = SingleCameraHardware()
    rear: SingleCameraHardware = SingleCameraHardware()


def load_camera_config(path: Path) -> CameraConfig:
    """从 TOML 文件加载相机配置，文件不存在则返回默认值。"""
    if not path.exists():
        return CameraConfig()
    with open(path, "rb") as f:
        return CameraConfig(**tomllib.load(f))
