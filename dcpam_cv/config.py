import tomllib
from pathlib import Path

import numpy as np
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Camera hardware config (camera.toml)
# ---------------------------------------------------------------------------

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
    """从 TOML 文件加载相机配置。"""
    if not path.exists():
        raise FileNotFoundError(f"相机配置文件不存在: {path}")
    with open(path, "rb") as f:
        return CameraConfig(**tomllib.load(f))


# ---------------------------------------------------------------------------
# Calibration config (calibration.toml)
# ---------------------------------------------------------------------------

class CameraIntrinsics(BaseModel):
    """SIMPLE_RADIAL 相机内参。"""
    focal_length: float
    principal_point: tuple[float, float]
    distortion: float
    resolution: tuple[int, int]

    def k_matrix(self) -> np.ndarray:
        """3x3 内参矩阵。"""
        f = self.focal_length
        cx, cy = self.principal_point
        return np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], dtype=np.float64)

    model_config = {"arbitrary_types_allowed": True}


class GeometryConfig(BaseModel):
    """镜面几何参数（兼容旧 calibration.toml，已迁移至 device.toml）。"""
    zs: float = 5.0
    rotation_center: tuple[float, float, float] = (0.0, 0.0, 5.0)
    rotation_angle: float = 0.0


class TransformConfig(BaseModel):
    """前→后相机刚体变换。"""
    r_rear_from_front: list[list[float]]
    t_rear_from_front: list[float]
    baseline_norm: float

    def rotation_matrix(self) -> np.ndarray:
        return np.array(self.r_rear_from_front, dtype=np.float64)

    def translation_vector(self) -> np.ndarray:
        return np.array(self.t_rear_from_front, dtype=np.float64)

    model_config = {"arbitrary_types_allowed": True}


class CalibrationConfig(BaseModel):
    """calibration.toml 完整结构。"""
    front_camera: CameraIntrinsics
    rear_camera: CameraIntrinsics
    geometry: GeometryConfig = GeometryConfig()
    transform: TransformConfig


def load_calibration(path: Path) -> CalibrationConfig:
    """加载标定配置，文件不存在则 raise FileNotFoundError。"""
    if not path.exists():
        raise FileNotFoundError(f"标定文件不存在: {path}")
    with open(path, "rb") as f:
        return CalibrationConfig(**tomllib.load(f))


# ---------------------------------------------------------------------------
# Pipeline config (pipeline.toml)
# ---------------------------------------------------------------------------

class SpotExtractionConfig(BaseModel):
    """光斑提取参数。"""
    method: str = "improved_circle_fit"
    gaussian_kernel: int = 9
    gaussian_sigma: float = 2.0
    centroid_threshold: float = 0.3


class PipelineConfig(BaseModel):
    """pipeline.toml 完整结构。"""
    spot_extraction: SpotExtractionConfig = SpotExtractionConfig()


def load_pipeline_config(path: Path) -> PipelineConfig:
    """加载 pipeline 配置。"""
    if not path.exists():
        raise FileNotFoundError(f"Pipeline 配置文件不存在: {path}")
    with open(path, "rb") as f:
        return PipelineConfig(**tomllib.load(f))


# ---------------------------------------------------------------------------
# Device config (device.toml)
# ---------------------------------------------------------------------------

class ScreenConfig(BaseModel):
    """接收屏参数 (mm)。"""
    zs: float


class MirrorConfig(BaseModel):
    """反射镜参数 (mm / rad)。"""
    rotation_center: tuple[float, float, float]
    rotation_angle: float


class ToolConfig(BaseModel):
    """被测工具参数 (mm)。"""
    mount_position: tuple[float, float, float]
    bar_length: float


class DeviceConfig(BaseModel):
    """device.toml 完整结构。"""
    screen: ScreenConfig
    mirror: MirrorConfig
    tool: ToolConfig


def load_device_config(path: Path) -> DeviceConfig:
    """加载设备配置。"""
    if not path.exists():
        raise FileNotFoundError(f"设备配置文件不存在: {path}")
    with open(path, "rb") as f:
        return DeviceConfig(**tomllib.load(f))

