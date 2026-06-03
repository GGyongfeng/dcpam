# DCPAM-CV 架构设计文档

> 本文档描述 dcpam_cv 模块的整体架构设计，包括全局配置系统、相机采集、
> 测量 pipeline、精度分析模块和 CLI 接口。
> 这是一个长期迭代的设计蓝图，分阶段实施。


## 1. 全局目录 `~/.dcpam/`

所有配置、标定结果、采集图像存放在用户主目录下，与项目代码解耦。

```
~/.dcpam/
├── calibration.toml       # 标定结果（内参、外参、Zs、H1、H2）
├── pipeline.toml          # pipeline 运行参数
├── camera.toml            # 相机硬件参数（序列号、曝光、增益）
└── images/                # 采集图像存档
    ├── 20250701_143025_front_a1b2c3.png
    ├── 20250701_143025_rear_a1b2c3.png
    └── ...
```


## 2. 代码目录结构

```
dcpam/
├── dcpam_cv/
│   ├── __init__.py
│   ├── path.py                      # 路径管理（~/.dcpam/ 为中心）
│   ├── config.py                    # Pydantic 配置模型 + TOML 加载
│   ├── types.py                     # 公共数据类型
│   ├── camera.py                    # DualCamera 相机采集类
│   ├── pipeline.py                  # DCPAMPipeline 核心测量类
│   │
│   ├── steps/                       # Pipeline 5 步
│   │   ├── __init__.py
│   │   ├── spot_extraction.py
│   │   ├── back_projection.py
│   │   ├── mirror_transform.py
│   │   ├── coordinate_transform.py
│   │   └── distance.py
│   │
│   └── precision/                   # 精度分析
│       ├── __init__.py
│       ├── analysis.py
│       └── visualization.py
│
├── scripts/
│   └── run_analysis.py
│
└── pyproject.toml                   # [project.scripts] dcpam = "dcpam_cv.cli:main"
```


## 3. 路径管理 — `path.py`

```python
from pathlib import Path


class DCPAMPaths:
    """~/.dcpam/ 全局路径管理。"""

    def __init__(self, root: Path | None = None):
        self.root = root or Path.home() / ".dcpam"

    @property
    def calibration_file(self) -> Path:
        return self.root / "calibration.toml"

    @property
    def pipeline_file(self) -> Path:
        return self.root / "pipeline.toml"

    @property
    def camera_file(self) -> Path:
        return self.root / "camera.toml"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    def ensure_dirs(self) -> None:
        """首次运行时创建目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
```

**设计要点：**
- 默认 `~/.dcpam/`，外层可传入自定义 root（测试、容器化场景）
- CLI / Pipeline / Camera 统一通过 `DCPAMPaths` 获取路径


## 4. Config 系统 — `config.py`

### 4.1 TOML 文件

#### `~/.dcpam/calibration.toml`

```toml
[front_camera]
model = "OPENCV"
focal_lengths = [2957.8241766856004, 2942.0409977296185]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.22671473034572842, 0.09224214298554129, -0.004102850618949305, -0.0009831445506355439]
resolution = [2592, 1944]

[rear_camera]
model = "OPENCV"
focal_lengths = [3061.8876511556277, 3057.0360889301282]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.24188566048129059, 0.10469978497759738, 0.0002845737129601245, 0.00018629382738589062]
resolution = [2592, 1944]

[transform]
r_rear_from_front = [
    [0.99981958, -0.01442669, -0.01235624],
    [0.01451016, 0.99987232, 0.00669294],
    [0.01225810, -0.00687103, 0.99990126],
]
t_rear_from_front = [-7.86547923, 0.15503238, 0.70268141]
baseline_norm = 7.89832639

[planes.front_image_real]
point = [0.89568958305, 11.6958981485, 5.23343140273]
normal = [0.00492360142167, -0.0832961234852, 0.996512676267]
d = -4.24536777526

[planes.rear_image_real]
point = [8.40410009288, 11.0517674219, 4.08626158655]
normal = [0.014021645213, 0.0867422307864, 0.996132109142]
d = -5.14695064286

[planes.front_reflection]
point = [-47.8575602765, -8.18769513583, 15.0908206393]
normal = [0.433725569982, 0.0533280620017, 0.899465534496]
d = 7.62000847045

[planes.rear_reflection]
point = [-41.314707067, -2.88091562171, 11.0941717449]
normal = [0.445325119069, 0.2168568307, 0.868710914692]
d = 9.38559499095
```

#### `~/.dcpam/pipeline.toml`

```toml
[spot_extraction]
method = "improved_circle"
gaussian_kernel = [9, 9]
gaussian_sigma = 2.0
centroid_threshold = 0.3
canny_low = 50
canny_high = 150
sobel_ksize = 5

[tool]
mount_position = [0.0, 0.0, 0.0]
bar_length = 200.0

[analysis]
error_range_um = 1.0
monte_carlo_samples = 10000
derivative_delta = 1e-8
```

#### `~/.dcpam/camera.toml`

```toml
[front]
serial = "KE0210040001"       # 大恒相机序列号
exposure_auto = true
gain_auto = true
# exposure_time = 10000.0     # 手动曝光时使用（μs）
# gain = 5.0                  # 手动增益时使用（dB）

[rear]
serial = "KE0210040002"
exposure_auto = true
gain_auto = true
```


### 4.2 Pydantic 模型

```python
import numpy as np
from pydantic import BaseModel


# ---------- 标定 ----------

class CameraIntrinsics(BaseModel):
    model: str = "OPENCV"
    focal_lengths: tuple[float, float]
    principal_point: tuple[float, float]
    distortion_coeffs: tuple[float, float, float, float]
    resolution: tuple[int, int]

    def to_matrix(self) -> np.ndarray:
        fx, fy = self.focal_lengths
        cx, cy = self.principal_point
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])


class TransformConfig(BaseModel):
    r_rear_from_front: list[list[float]]
    t_rear_from_front: list[float]
    baseline_norm: float


class PlaneConfig(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class PlaneCalibrationConfig(BaseModel):
    front_image_real: PlaneConfig
    rear_image_real: PlaneConfig
    front_reflection: PlaneConfig
    rear_reflection: PlaneConfig


class CalibrationConfig(BaseModel):
    front_camera: CameraIntrinsics
    rear_camera: CameraIntrinsics
    transform: TransformConfig
    planes: PlaneCalibrationConfig


# ---------- Pipeline ----------

class SpotExtractionConfig(BaseModel):
    method: str = "improved_circle"
    gaussian_kernel: tuple[int, int] = (9, 9)
    gaussian_sigma: float = 2.0
    centroid_threshold: float = 0.3
    canny_low: int = 50
    canny_high: int = 150
    sobel_ksize: int = 5


class ToolConfig(BaseModel):
    mount_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bar_length: float = 200.0


class AnalysisConfig(BaseModel):
    error_range_um: float = 1.0
    monte_carlo_samples: int = 10000
    derivative_delta: float = 1e-8


class PipelineConfig(BaseModel):
    spot_extraction: SpotExtractionConfig = SpotExtractionConfig()
    tool: ToolConfig = ToolConfig()
    analysis: AnalysisConfig = AnalysisConfig()


# ---------- 相机硬件 ----------

class SingleCameraHardware(BaseModel):
    serial: str = ""
    exposure_auto: bool = True
    gain_auto: bool = True
    exposure_time: float | None = None    # μs，手动模式时使用
    gain: float | None = None             # dB，手动模式时使用


class CameraConfig(BaseModel):
    front: SingleCameraHardware = SingleCameraHardware()
    rear: SingleCameraHardware = SingleCameraHardware()
```


### 4.3 加载函数

```python
import tomllib
from pathlib import Path


def load_calibration(path: Path) -> CalibrationConfig:
    with open(path, "rb") as f:
        return CalibrationConfig(**tomllib.load(f))


def load_pipeline_config(path: Path) -> PipelineConfig:
    with open(path, "rb") as f:
        return PipelineConfig(**tomllib.load(f))


def load_camera_config(path: Path) -> CameraConfig:
    with open(path, "rb") as f:
        return CameraConfig(**tomllib.load(f))
```


## 5. 相机采集 — `camera.py`

### 5.1 DualCamera 类

```python
import uuid
from datetime import datetime

import numpy as np

from .config import CameraConfig, SingleCameraHardware
from .path import DCPAMPaths


class ImagePair(BaseModel):
    """一次采集的图像对。"""
    front: np.ndarray           # BGR 图像
    rear: np.ndarray            # BGR 图像
    timestamp: datetime
    uid: str                    # 6 位短 UUID
    front_path: Path | None = None
    rear_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


class DualCamera:
    """双相机采集控制器。

    职责：
    1. 根据 CameraConfig 按序列号打开指定的 front / rear 相机
    2. 应用曝光、增益等硬件参数
    3. capture() 瞬时采集一对同步图像
    4. save() 保存图像到 ~/.dcpam/images/

    用法：
        camera = DualCamera()                      # 从 ~/.dcpam/camera.toml 加载
        camera = DualCamera(config=my_config)       # 外部传入
        camera.open()
        pair = camera.capture()                     # 瞬时采集
        camera.save(pair)                           # 保存到 images/
        camera.close()
    """

    def __init__(
        self,
        config: CameraConfig | None = None,
        paths: DCPAMPaths | None = None,
    ):
        self.paths = paths or DCPAMPaths()
        self.config = config or load_camera_config(self.paths.camera_file)
        self._front_cam = None
        self._rear_cam = None

    def open(self) -> None:
        """按序列号打开两个相机，应用硬件参数，开启数据流。"""
        ...

    def close(self) -> None:
        """关闭数据流和设备。"""
        ...

    def capture(self) -> ImagePair:
        """瞬时采集一对图像。

        两个相机尽可能同时触发，取当前帧。
        生成 timestamp + uid 标识这次采集。
        """
        timestamp = datetime.now()
        uid = uuid.uuid4().hex[:6]

        front_frame = self._grab_frame(self._front_cam)
        rear_frame = self._grab_frame(self._rear_cam)

        return ImagePair(
            front=front_frame,
            rear=rear_frame,
            timestamp=timestamp,
            uid=uid,
        )

    def save(self, pair: ImagePair) -> ImagePair:
        """保存图像对到 ~/.dcpam/images/。

        命名：{YYYYMMDD_HHMMSS}_{front|rear}_{uid}.png
        返回更新了 front_path / rear_path 的 ImagePair。
        """
        self.paths.ensure_dirs()
        ts = pair.timestamp.strftime("%Y%m%d_%H%M%S")

        front_path = self.paths.images_dir / f"{ts}_front_{pair.uid}.png"
        rear_path = self.paths.images_dir / f"{ts}_rear_{pair.uid}.png"

        cv2.imwrite(str(front_path), pair.front)
        cv2.imwrite(str(rear_path), pair.rear)

        pair.front_path = front_path
        pair.rear_path = rear_path
        return pair

    def _grab_frame(self, cam) -> np.ndarray:
        """从单个相机获取当前帧，转为 BGR。"""
        ...

    def _apply_hardware_config(self, cam, hw: SingleCameraHardware) -> None:
        """应用曝光、增益等参数。"""
        ...

    def __enter__(self): ...
    def __exit__(self, *args): ...
```

**设计要点：**
- `capture()` 只做瞬时读取，不做任何图像处理
- `save()` 和 `capture()` 分离 — 可以先采集再决定是否保存
- 支持 context manager（`with DualCamera() as cam:`）
- 按序列号打开指定相机，而非按索引顺序（确保 front/rear 不会因为插拔顺序搞混）


### 5.2 相机配置的自动发现

首次运行时如果 `~/.dcpam/camera.toml` 不存在，DualCamera 可以提供 `discover()` 方法：
扫描连接的相机，列出序列号，让用户指定哪个是 front、哪个是 rear，然后写入 camera.toml。

```python
@classmethod
def discover(cls, paths: DCPAMPaths | None = None) -> CameraConfig:
    """扫描已连接的相机，交互式指定 front/rear，写入 camera.toml。"""
    ...
```


## 6. 核心类 — `pipeline.py`

### 6.1 DCPAMPipeline

```python
import numpy as np

from .config import CalibrationConfig, PipelineConfig, load_calibration, load_pipeline_config
from .path import DCPAMPaths
from .types import MeasurementResult, Point3D


class DCPAMPipeline:
    """DCPAM-CV 核心测量类。

    核心方法：
        measure(front_image, rear_image) -> MeasurementResult

    用法：
        pipeline = DCPAMPipeline()
        result = pipeline.measure(front_img, rear_img)
        print(result.distance)
    """

    def __init__(
        self,
        calibration: CalibrationConfig | None = None,
        config: PipelineConfig | None = None,
        paths: DCPAMPaths | None = None,
    ):
        self.paths = paths or DCPAMPaths()
        self.calibration = calibration or load_calibration(
            self.paths.calibration_file
        )
        self.config = config or load_pipeline_config(
            self.paths.pipeline_file
        )

    def measure(
        self,
        front_image: np.ndarray,
        rear_image: np.ndarray,
    ) -> MeasurementResult:
        """接收两张图片，返回目标点到激光轴线的距离。

        内部执行 5 步 pipeline：
        1. 光斑提取 → SpotPair
        2. 反投影   → RealPointPair
        3. 镜面变换 → VirtualPointPair
        4. 坐标变换 → LaserAxis
        5. 距离计算 → float
        """
        spots = extract_spots(front_image, rear_image, self.config.spot_extraction)
        real_points = back_project(spots, self.calibration)
        virtual_points = mirror_transform(real_points, self.calibration)
        laser_axis = coordinate_transform(virtual_points, self.calibration)
        target = self._build_target_point()
        distance = compute_distance(laser_axis, target)

        return MeasurementResult(
            distance=distance,
            target_point=target,
            laser_axis=laser_axis,
        )

    def _build_target_point(self) -> Point3D:
        x0, y0, z0 = self.config.tool.mount_position
        return Point3D(x=x0, y=y0, z=z0 + self.config.tool.bar_length)
```


### 6.2 Pipeline 5 步（同前，略）

每步是独立的纯函数，参见第 3 章。


## 7. CLI — `dcpam` 命令

### 7.1 注册入口

`pyproject.toml`:
```toml
[project.scripts]
dcpam = "dcpam_cv.cli:main"
```

安装后即可在终端使用 `dcpam` 命令。


### 7.2 交互流程

```
$ dcpam

  DCPAM — Dual-Camera Point-to-Axis Measurement
  Config: ~/.dcpam/

  [INFO] Loading calibration...  ✓
  [INFO] Loading pipeline config...  ✓
  [INFO] Opening cameras (front: KE0210040001, rear: KE0210040002)...  ✓
  [INFO] Ready. Press ENTER to capture + measure, Q to quit.

  > [ENTER]
  [14:30:25] Captured pair (uid: a1b2c3)
  [14:30:25] Saved: ~/.dcpam/images/20250701_143025_front_a1b2c3.png
  [14:30:25] Saved: ~/.dcpam/images/20250701_143025_rear_a1b2c3.png
  [14:30:26] Distance H = 0.3742 cm

  > [ENTER]
  [14:30:31] Captured pair (uid: d4e5f6)
  [14:30:31] Distance H = 0.3738 cm

  > Q
  [INFO] Cameras closed. Bye.
```


### 7.3 CLI 实现骨架

```python
from .camera import DualCamera
from .config import load_calibration, load_pipeline_config
from .path import DCPAMPaths
from .pipeline import DCPAMPipeline


def main() -> None:
    paths = DCPAMPaths()
    paths.ensure_dirs()

    pipeline = DCPAMPipeline(paths=paths)

    with DualCamera(paths=paths) as camera:
        print("Ready. Press ENTER to capture + measure, Q to quit.\n")

        while True:
            user_input = input("> ").strip().lower()
            if user_input == "q":
                break

            pair = camera.capture()
            camera.save(pair)
            result = pipeline.measure(pair.front, pair.rear)
            print(f"  Distance H = {result.distance:.4f} cm\n")

    print("Cameras closed. Bye.")
```

**设计要点：**
- 相机在进入循环前就已经打开并保持数据流（连续模式）
- ENTER 触发 `capture()` → 瞬时读取当前帧（不等待新帧）
- 采集与计算分离：采集是瞬时的（ms 级），计算可以慢一点
- 每次采集自动保存图片，再送入 pipeline 计算


## 8. 类关系总览

```
┌────────────────────┐     ┌───────────────────┐
│   DCPAMPaths       │     │   CameraConfig    │
│   (~/.dcpam/)      │     │   (camera.toml)   │
└────────┬───────────┘     └─────────┬─────────┘
         │                           │
         ├───────────────────────────┤
         │                           │
         ▼                           ▼
┌────────────────────┐     ┌───────────────────┐
│  CalibrationConfig │     │    DualCamera     │
│  PipelineConfig    │     │                   │
│  (TOML → Pydantic) │     │  .open()          │
└────────┬───────────┘     │  .capture() → ImagePair
         │                 │  .save(pair)       │
         ▼                 │  .close()          │
┌────────────────────┐     └─────────┬─────────┘
│  DCPAMPipeline     │               │
│                    │    ImagePair.front ──┐
│  .measure(         │    ImagePair.rear  ──┤
│    front_image,         │◄────────────────────┘
│    rear_image           │
│  ) → MeasurementResult
│                    │
│  内部 5 步:         │
│  extract_spots     │
│  back_project      │
│  mirror_transform  │
│  coord_transform   │
│  compute_distance  │
└────────────────────┘
```


## 9. 分阶段实施路线

### Phase 1: 基础设施
- [ ] `dcpam_cv/path.py` — DCPAMPaths
- [ ] `dcpam_cv/config.py` — Pydantic 模型 + 加载函数
- [ ] `dcpam_cv/types.py` — 公共数据类型
- [ ] `~/.dcpam/` 目录初始化 + 默认 TOML 模板

### Phase 2: 相机采集
- [ ] `dcpam_cv/camera.py` — DualCamera 类
- [ ] 从 `dual_daheng_capture.py` 迁移核心逻辑
- [ ] `camera.toml` 读写
- [ ] 图片命名与保存

### Phase 3: Pipeline 骨架
- [ ] `dcpam_cv/steps/` — 5 个步骤（函数签名 + pass）
- [ ] `dcpam_cv/pipeline.py` — DCPAMPipeline

### Phase 4: Pipeline 实现
- [ ] Step 5: distance.py（从现有代码迁移）
- [ ] Step 2: back_projection.py
- [ ] Step 3: mirror_transform.py
- [ ] Step 4: coordinate_transform.py
- [ ] Step 1: spot_extraction.py（从 center.py 重构）

### Phase 5: CLI
- [ ] `dcpam_cv/cli.py` — main() 交互式命令
- [ ] `pyproject.toml` 注册 `[project.scripts]`

### Phase 6: 精度分析重构
- [ ] PrecisionAnalyzer 重构
- [ ] visualization 重构
- [ ] run_analysis.py 更新

### Phase 7: 集成验证
- [ ] 端到端测试
- [ ] 清理旧代码
