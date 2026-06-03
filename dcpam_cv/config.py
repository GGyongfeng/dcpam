import tomllib
from pathlib import Path

import numpy as np
from pydantic import BaseModel, model_validator

from .plane_calibration import ColmapPlaneSource, derive_planes_from_colmap


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


class PlaneConfig(BaseModel):
    """相机坐标系下的平面表示。"""
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class PlaneCalibrationConfig(BaseModel):
    """四个光学平面的标定结果。"""
    front_image_real: PlaneConfig
    rear_image_real: PlaneConfig
    front_reflection: PlaneConfig
    rear_reflection: PlaneConfig


class PlaneSourceConfig(BaseModel):
    """光学平面原始标定来源。"""
    colmap: ColmapPlaneSource | None = None


class FramePoseConfig(BaseModel):
    """取景框坐标系到相机坐标系的外参。"""
    frame_width_mm: float | None = None
    frame_height_mm: float | None = None
    rotation_frame_to_camera: list[list[float]]
    translation_frame_to_camera: list[float]
    matrix_frame_to_camera: list[list[float]] | None = None
    matrix_camera_to_frame: list[list[float]] | None = None
    reprojection_error_px: float

    def rotation_matrix(self) -> np.ndarray:
        return np.array(self.rotation_frame_to_camera, dtype=np.float64)

    def translation_vector(self) -> np.ndarray:
        return np.array(self.translation_frame_to_camera, dtype=np.float64)

    model_config = {"arbitrary_types_allowed": True}


class FrameCalibrationConfig(BaseModel):
    """前后取景框位姿标定结果。"""
    front_frame_pose: FramePoseConfig | None = None
    rear_frame_pose: FramePoseConfig | None = None


class CalibrationConfig(BaseModel):
    """完整标定配置。"""
    front_camera: CameraIntrinsics
    rear_camera: CameraIntrinsics
    transform: TransformConfig
    planes: PlaneCalibrationConfig
    plane_sources: PlaneSourceConfig | None = None
    frames: FrameCalibrationConfig = FrameCalibrationConfig()

    @model_validator(mode="before")
    @classmethod
    def derive_planes(cls, data: dict) -> dict:
        """配置未直接提供 planes 时，从原始标定来源派生。"""
        if data.get("planes") is not None:
            return data
        sources = data.get("plane_sources") or {}
        colmap = sources.get("colmap")
        if colmap is None:
            return data
        source = ColmapPlaneSource(**colmap)
        data["planes"] = {
            name: plane.model_dump()
            for name, plane in derive_planes_from_colmap(source).items()
        }
        return data


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

class ToolConfig(BaseModel):
    """被测工具参数 (mm)。"""
    mount_position: tuple[float, float, float]
    bar_length: float


class DeviceConfig(BaseModel):
    """设备完整配置。"""
    tool: ToolConfig


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
