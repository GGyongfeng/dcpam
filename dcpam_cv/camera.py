from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from .config import CameraConfig, SingleCameraHardware, load_config
from .path import DCPAMPaths

if TYPE_CHECKING:
    from gi.repository import Aravis


# ---------------------------------------------------------------------------
#  数据类型
# ---------------------------------------------------------------------------

class ImagePair(BaseModel):
    """一次采集的图像对。"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    front: np.ndarray
    rear: np.ndarray
    timestamp: datetime
    uid: str
    front_path: Path | None = None
    rear_path: Path | None = None


# ---------------------------------------------------------------------------
#  SDK 延迟导入
# ---------------------------------------------------------------------------

_aravis = None
_gxipy = None


def _get_aravis():
    """延迟导入 Aravis（macOS/Linux）。"""
    global _aravis
    if _aravis is None:
        try:
            import gi
            gi.require_version("Aravis", "0.8")
            from gi.repository import Aravis as _Arv
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                "相机功能需要 Aravis + PyGObject。请安装：\n"
                "  brew install aravis pygobject3 libffi\n"
                "  PKG_CONFIG_PATH=\"/opt/homebrew/opt/libffi/lib/pkgconfig\" "
                "uv pip install 'dcpam[camera]'"
            ) from exc
        _aravis = _Arv
    return _aravis


_GALAXY_SDK_ROOTS = [
    Path("D:/Camera_Galaxy/GalaxySDK"),
    Path("C:/Program Files/Daheng Imaging/GalaxySDK"),
    Path("C:/Program Files/GalaxySDK"),
]


def _configure_galaxy_paths() -> None:
    """把 Galaxy SDK 的 Python/DLL/GenTL 路径加进当前进程。"""
    for root in _GALAXY_SDK_ROOTS:
        py_path = root / "Development" / "Samples" / "Python"
        dll_path = root / "APIDll" / "Win64"
        gentl_path = root / "GenICam" / "bin" / "Win64_x64"

        if py_path.exists() and str(py_path) not in sys.path:
            sys.path.insert(0, str(py_path))

        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        prepend: list[str] = []
        if dll_path.exists() and str(dll_path) not in path_parts:
            prepend.append(str(dll_path))
        if gentl_path.exists() and str(gentl_path) not in path_parts:
            prepend.append(str(gentl_path))
        if prepend:
            os.environ["PATH"] = os.pathsep.join(prepend + [os.environ.get("PATH", "")])


def _get_gxipy():
    """延迟导入大恒 gxipy（Windows）。"""
    global _gxipy
    if _gxipy is None:
        if int(np.__version__.split(".")[0]) >= 2:
            raise RuntimeError(
                "gxipy 依赖 numpy.compat，要求 numpy < 2。请：\n"
                "  uv pip install \"numpy<2\""
            )
        _configure_galaxy_paths()
        try:
            import gxipy as _gx
        except ImportError as exc:
            raise RuntimeError(
                "相机功能需要大恒 Galaxy SDK 及其 Python 绑定 gxipy。\n"
                "请安装 Galaxy SDK（包含 Python 样例），常见路径：\n"
                "  D:/Camera_Galaxy/GalaxySDK/Development/Samples/Python"
            ) from exc
        _gxipy = _gx
    return _gxipy


# ---------------------------------------------------------------------------
#  Aravis 后端（macOS / Linux）
# ---------------------------------------------------------------------------

@dataclass
class _AravisHandle:
    camera: object
    stream: object
    serial: str
    name: str
    width: int
    height: int


class _DualCameraAravis:
    """基于 Aravis GigE Vision 的双相机后端。"""

    def __init__(self, config: CameraConfig, paths: DCPAMPaths):
        self.paths = paths
        self.config = config
        self._front: _AravisHandle | None = None
        self._rear: _AravisHandle | None = None

    def open(self) -> None:
        arv = _get_aravis()
        arv.update_device_list()
        n = arv.get_n_devices()
        if n < 2:
            raise RuntimeError(f"需要至少 2 个相机，当前检测到 {n} 个")

        serials = {arv.get_device_serial_nbr(i): i for i in range(n)}
        self._front = self._open_one(serials, self.config.front, "front")
        self._rear = self._open_one(serials, self.config.rear, "rear")

    def close(self) -> None:
        for handle in (self._front, self._rear):
            if handle is None:
                continue
            try:
                handle.stream.set_emit_signals(False)
            except Exception:
                pass
        self._front = None
        self._rear = None

    def capture(self) -> ImagePair:
        if self._front is None or self._rear is None:
            raise RuntimeError("相机未打开，请先调用 open()")

        timestamp = datetime.now()
        uid = f"C_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        return ImagePair(
            front=self._grab_frame(self._front),
            rear=self._grab_frame(self._rear),
            timestamp=timestamp,
            uid=uid,
        )

    def _open_one(
        self,
        serials: dict[str, int],
        hw: SingleCameraHardware,
        role: str,
    ) -> _AravisHandle:
        arv = _get_aravis()

        if hw.serial:
            if hw.serial not in serials:
                raise RuntimeError(f"{role} 相机序列号 {hw.serial} 未找到")
            device_id = arv.get_device_id(serials[hw.serial])
        else:
            idx = 0 if role == "front" else 1
            device_id = arv.get_device_id(idx)

        camera = arv.Camera.new(device_id)
        self._apply_hardware(camera, hw)

        camera.set_acquisition_mode(arv.AcquisitionMode.CONTINUOUS)
        stream = camera.create_stream(None, None)

        payload = camera.get_payload()
        for _ in range(10):
            stream.push_buffer(arv.Buffer.new_allocate(payload))

        camera.start_acquisition()

        width = camera.get_region()[2]
        height = camera.get_region()[3]

        return _AravisHandle(
            camera=camera,
            stream=stream,
            serial=hw.serial or device_id,
            name=role,
            width=width,
            height=height,
        )

    def _apply_hardware(self, camera: "Aravis.Camera", hw: SingleCameraHardware) -> None:
        arv = _get_aravis()

        if hw.exposure_auto:
            camera.set_exposure_time_auto(arv.Auto.CONTINUOUS)
        elif hw.exposure_time is not None:
            camera.set_exposure_time_auto(arv.Auto.OFF)
            camera.set_exposure_time(hw.exposure_time)

        if hw.gain_auto:
            camera.set_gain_auto(arv.Auto.CONTINUOUS)
        elif hw.gain is not None:
            camera.set_gain_auto(arv.Auto.OFF)
            camera.set_gain(hw.gain)

    def _grab_frame(self, handle: _AravisHandle) -> np.ndarray:
        arv = _get_aravis()

        while True:
            buf = handle.stream.try_pop_buffer()
            if buf is None:
                break
            handle.stream.push_buffer(buf)

        for _ in range(5):
            latest = handle.stream.timeout_pop_buffer(3_000_000)
            if latest is None:
                raise RuntimeError(f"{handle.name} 相机帧获取超时")
            if latest.get_status() == arv.BufferStatus.SUCCESS:
                break
            handle.stream.push_buffer(latest)
        else:
            raise RuntimeError(f"{handle.name} 帧状态异常")

        data = latest.get_data()
        arr = np.frombuffer(data, dtype=np.uint8)
        pixel_format = handle.camera.get_pixel_format_as_string()

        if "Bayer" in pixel_format:
            raw = arr.reshape(handle.height, handle.width)
            frame = cv2.cvtColor(raw, cv2.COLOR_BayerRG2BGR)
        elif "Mono" in pixel_format or "Grey" in pixel_format:
            frame = arr.reshape(handle.height, handle.width).copy()
        elif "RGB" in pixel_format:
            rgb = arr.reshape(handle.height, handle.width, 3)
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            frame = arr.reshape(handle.height, handle.width, -1).copy()

        handle.stream.push_buffer(latest)
        return frame


# ---------------------------------------------------------------------------
#  Daheng gxipy 后端（Windows）
# ---------------------------------------------------------------------------

@dataclass
class _DahengHandle:
    camera: object
    serial: str
    name: str


class _DualCameraDaheng:
    """基于大恒 Galaxy SDK (gxipy) 的双相机后端。"""

    def __init__(self, config: CameraConfig, paths: DCPAMPaths):
        self.paths = paths
        self.config = config
        self._device_manager = None
        self._front: _DahengHandle | None = None
        self._rear: _DahengHandle | None = None

    def open(self) -> None:
        gx = _get_gxipy()

        self._device_manager = gx.DeviceManager()
        dev_num, dev_info_list = self._device_manager.update_device_list()
        if dev_num < 2:
            raise RuntimeError(f"需要至少 2 个相机，当前检测到 {dev_num} 个")

        serial_to_index = {
            info.get("sn", ""): idx + 1  # gxipy 索引从 1 开始
            for idx, info in enumerate(dev_info_list)
        }

        self._front = self._open_one(dev_info_list, serial_to_index, self.config.front, "front", 1)
        self._rear = self._open_one(dev_info_list, serial_to_index, self.config.rear, "rear", 2)

    def close(self) -> None:
        for handle in (self._front, self._rear):
            if handle is None:
                continue
            try:
                handle.camera.stream_off()
            except Exception:
                pass
            try:
                handle.camera.close_device()
            except Exception:
                pass
        self._front = None
        self._rear = None
        self._device_manager = None

    def capture(self) -> ImagePair:
        if self._front is None or self._rear is None:
            raise RuntimeError("相机未打开，请先调用 open()")
        timestamp = datetime.now()
        uid = f"C_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        return ImagePair(
            front=self._grab_frame(self._front),
            rear=self._grab_frame(self._rear),
            timestamp=timestamp,
            uid=uid,
        )

    def _open_one(
        self,
        dev_info_list: list,
        serial_to_index: dict[str, int],
        hw: SingleCameraHardware,
        role: str,
        default_index: int,
    ) -> _DahengHandle:
        gx = _get_gxipy()

        if hw.serial:
            if hw.serial not in serial_to_index:
                raise RuntimeError(f"{role} 相机序列号 {hw.serial} 未找到")
            index = serial_to_index[hw.serial]
        else:
            index = default_index

        camera = self._device_manager.open_device_by_index(index)
        info = dev_info_list[index - 1]
        serial = info.get("sn", f"cam{index}")

        # 连续采集模式，方便预览 + 抓帧
        camera.TriggerMode.set(gx.GxSwitchEntry.OFF)
        self._apply_hardware(gx, camera, hw)

        camera.stream_on()
        return _DahengHandle(camera=camera, serial=serial, name=role)

    @staticmethod
    def _apply_hardware(gx, camera, hw: SingleCameraHardware) -> None:
        if hw.exposure_auto:
            if camera.ExposureAuto.is_implemented() and camera.ExposureAuto.is_writable():
                camera.ExposureAuto.set(gx.GxAutoEntry.CONTINUOUS)
        elif hw.exposure_time is not None and camera.ExposureTime.is_writable():
            if camera.ExposureAuto.is_writable():
                camera.ExposureAuto.set(gx.GxAutoEntry.OFF)
            camera.ExposureTime.set(float(hw.exposure_time))

        if hw.gain_auto:
            if camera.GainAuto.is_implemented() and camera.GainAuto.is_writable():
                camera.GainAuto.set(gx.GxAutoEntry.CONTINUOUS)
        elif hw.gain is not None and camera.Gain.is_writable():
            if camera.GainAuto.is_writable():
                camera.GainAuto.set(gx.GxAutoEntry.OFF)
            camera.Gain.set(float(hw.gain))

    def _grab_frame(self, handle: _DahengHandle) -> np.ndarray:
        raw = handle.camera.data_stream[0].get_image(timeout=2000)
        if raw is None:
            raise RuntimeError(f"{handle.name} 相机帧获取超时")

        cam = handle.camera
        if cam.PixelColorFilter.is_implemented():
            rgb = raw.convert("RGB")
            if rgb is None:
                raise RuntimeError(f"{handle.name} 帧转 RGB 失败")
            arr = rgb.get_numpy_array()
            if arr is None:
                raise RuntimeError(f"{handle.name} 帧转 numpy 失败")
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        arr = raw.get_numpy_array()
        if arr is None:
            raise RuntimeError(f"{handle.name} 帧转 numpy 失败")
        if arr.ndim == 2:
            return arr.copy()
        return arr


# ---------------------------------------------------------------------------
#  DualCamera 门面 —— 按平台派发后端
# ---------------------------------------------------------------------------

class DualCamera:
    """双相机采集控制器。

    Windows 走大恒 Galaxy SDK (gxipy)，其他平台走 Aravis GigE Vision。

    用法：
        with DualCamera() as cam:
            pair = cam.capture()
            cam.save(pair)
    """

    def __init__(
        self,
        config: CameraConfig | None = None,
        paths: DCPAMPaths | None = None,
    ):
        self.paths = paths or DCPAMPaths()
        self.config = config or load_config(self.paths.config_file).camera

        backend_cls = _DualCameraDaheng if sys.platform == "win32" else _DualCameraAravis
        self._backend = backend_cls(self.config, self.paths)

    # -- 生命周期 --

    def open(self) -> None:
        self._backend.open()

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> "DualCamera":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # -- 采集 & 保存 --

    def capture(self) -> ImagePair:
        return self._backend.capture()

    def save(self, pair: ImagePair) -> ImagePair:
        """保存图像对到项目 captures/{uid}/。"""
        capture_dir = self.paths.capture_dir(pair.uid)
        capture_dir.mkdir(parents=True, exist_ok=True)

        front_path = capture_dir / "front.png"
        rear_path = capture_dir / "rear.png"

        cv2.imwrite(str(front_path), pair.front)
        cv2.imwrite(str(rear_path), pair.rear)

        pair.front_path = front_path
        pair.rear_path = rear_path
        return pair
