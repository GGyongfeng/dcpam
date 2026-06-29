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
    """双相机硬件配置。"""
    front: SingleCameraHardware = SingleCameraHardware()
    rear: SingleCameraHardware = SingleCameraHardware()


# ---------------------------------------------------------------------------
# Calibration config
# ---------------------------------------------------------------------------

class CameraIntrinsics(BaseModel):
    """相机内参。"""
    model: str = "OPENCV"
    focal_lengths: tuple[float, float]
    principal_point: tuple[float, float]
    distortion_coeffs: tuple[float, float, float, float]
    resolution: tuple[int, int]

    def k_matrix(self) -> np.ndarray:
        """3x3 内参矩阵。"""
        fx, fy = self.focal_lengths
        cx, cy = self.principal_point
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)

    model_config = {"arbitrary_types_allowed": True}


class PlaneConfig(BaseModel):
    """相机坐标系下的平面表示。"""
    method: str | None = None
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class PlaneCalibrationConfig(BaseModel):
    """四个光学平面的标定结果。"""
    front_image_real: PlaneConfig | None = None
    rear_image_real: PlaneConfig | None = None
    front_reflection: PlaneConfig | None = None
    rear_reflection: PlaneConfig | None = None


class FrameSurfaceConfig(BaseModel):
    """PnP 得到的取景框平面（相机坐标系下，仅 pipeline 反投影使用的字段）。"""
    method: str = "pnp_frame_pose"
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class FrameSurfaceCalibrationConfig(BaseModel):
    """取景框在相机坐标系下的直接几何表示。"""
    front_frame_pnp: FrameSurfaceConfig | None = None
    rear_frame_pnp: FrameSurfaceConfig | None = None


class CameraToDeviceConfig(BaseModel):
    """相机坐标系 → 设备坐标系的刚体变换：p_device = R @ p_camera + t。"""
    rotation: list[tuple[float, float, float]]  # 3x3, 按行
    translation: tuple[float, float, float]


class CalibrationConfig(BaseModel):
    """完整标定配置。"""
    front_camera: CameraIntrinsics
    rear_camera: CameraIntrinsics
    planes: PlaneCalibrationConfig = PlaneCalibrationConfig()
    frame_surfaces: FrameSurfaceCalibrationConfig = FrameSurfaceCalibrationConfig()
    front_camera_to_device: CameraToDeviceConfig | None = None
    rear_camera_to_device: CameraToDeviceConfig | None = None


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------

class SpotExtractionConfig(BaseModel):
    """光斑提取参数。"""
    method: str = "improved_circle_fit"
    gaussian_kernel: int = 9
    gaussian_sigma: float = 2.0
    centroid_threshold: float = 0.3


class PipelineConfig(BaseModel):
    """Pipeline 完整配置。"""
    spot_extraction: SpotExtractionConfig = SpotExtractionConfig()


# ---------------------------------------------------------------------------
# Device config
# ---------------------------------------------------------------------------

class DeviceReflectionGeometryConfig(BaseModel):
    """设备坐标系下的反射平面。"""
    point: tuple[float, float, float]
    normal: tuple[float, float, float]


class ProbeRodGeometryConfig(BaseModel):
    """设备坐标系下的探测杆。"""
    root: tuple[float, float, float]
    length_mm: float


class DeviceGeometryConfig(BaseModel):
    """算法关心的设备几何。"""
    front_reflection: DeviceReflectionGeometryConfig
    rear_reflection: DeviceReflectionGeometryConfig
    probe_rod: ProbeRodGeometryConfig


class DeviceConfig(BaseModel):
    """设备完整配置。"""
    geometry: DeviceGeometryConfig


class AppConfig(BaseModel):
    """项目根目录 config.toml 的完整结构。"""
    camera: CameraConfig = CameraConfig()
    calibration: CalibrationConfig
    pipeline: PipelineConfig = PipelineConfig()
    device: DeviceConfig


def load_config(path: Path) -> AppConfig:
    """加载统一配置文件。"""
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "rb") as file:
        return AppConfig(**tomllib.load(file))


def load_camera_config(path: Path) -> CameraConfig:
    """从统一或旧相机 TOML 加载相机配置。"""
    data = _load_toml(path)
    return CameraConfig(**_section(data, path, "camera"))


def load_calibration(path: Path) -> CalibrationConfig:
    """从统一或旧标定 TOML 加载标定配置。"""
    data = _load_toml(path)
    return CalibrationConfig(**_section(data, path, "calibration"))


def load_pipeline_config(path: Path) -> PipelineConfig:
    """从统一或旧 pipeline TOML 加载 pipeline 配置。"""
    data = _load_toml(path)
    return PipelineConfig(**_section(data, path, "pipeline"))


def load_device_config(path: Path) -> DeviceConfig:
    """从统一或旧设备 TOML 加载设备配置。"""
    data = _load_toml(path)
    return DeviceConfig(**_section(data, path, "device"))


def _load_toml(path: Path) -> dict:
    """读取 TOML 为 dict。"""
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "rb") as file:
        return tomllib.load(file)


def _section(data: dict, path: Path, name: str) -> dict:
    """统一配置返回指定 section，旧配置直接返回顶层。"""
    if path.name == "config.toml":
        return data[name]
    return data
