from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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

_aravis = None


def _get_aravis():
    """延迟导入 Aravis，确保 DYLD 环境变量已设置。"""
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
#  DualCamera
# ---------------------------------------------------------------------------

@dataclass
class _CameraHandle:
    """内部：单个已打开的相机。"""
    camera: object
    stream: object
    serial: str
    name: str
    width: int
    height: int


class DualCamera:
    """双相机采集控制器（基于 Aravis GigE Vision）。

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
        self._front: _CameraHandle | None = None
        self._rear: _CameraHandle | None = None
        # 前后相机 grab 并行执行的线程池。每台相机各自有独立的 Aravis stream，
        # 互不共享状态，所以并发调用 _grab_frame 是安全的。
        self._executor: ThreadPoolExecutor | None = None

    # -- 生命周期 --

    def open(self) -> None:
        """打开双相机，应用硬件参数，开启数据流。"""
        arv = _get_aravis()
        arv.update_device_list()
        n = arv.get_n_devices()
        if n < 2:
            raise RuntimeError(f"需要至少 2 个相机，当前检测到 {n} 个")

        serials = {arv.get_device_serial_nbr(i): i for i in range(n)}

        self._front = self._open_one(serials, self.config.front, "front")
        self._rear = self._open_one(serials, self.config.rear, "rear")
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dcpam-cap")

    def close(self) -> None:
        """关闭数据流和设备。"""
        for handle in (self._front, self._rear):
            if handle is None:
                continue
            try:
                handle.stream.set_emit_signals(False)
            except Exception:
                pass
        self._front = None
        self._rear = None
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def __enter__(self) -> DualCamera:
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # -- 采集 & 保存 --

    def capture(self) -> ImagePair:
        """瞬时采集一对图像。前后相机的 _grab_frame 并行执行，把等新帧的时间从 2×fps^-1 降到 1×fps^-1。"""
        if self._front is None or self._rear is None or self._executor is None:
            raise RuntimeError("相机未打开，请先调用 open()")

        timestamp = datetime.now()
        uid = f"C_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        front_future = self._executor.submit(self._grab_frame, self._front)
        rear_future = self._executor.submit(self._grab_frame, self._rear)

        # 任一相机异常都会通过 .result() 抛出。
        front = front_future.result()
        rear = rear_future.result()

        return ImagePair(
            front=front,
            rear=rear,
            timestamp=timestamp,
            uid=uid,
        )

    def save(self, pair: ImagePair) -> ImagePair:
        """保存图像对到项目 captures/{uid}/，返回更新了路径的 ImagePair。"""
        capture_dir = self.paths.capture_dir(pair.uid)
        capture_dir.mkdir(parents=True, exist_ok=True)

        front_path = capture_dir / "front.png"
        rear_path = capture_dir / "rear.png"

        cv2.imwrite(str(front_path), pair.front)
        cv2.imwrite(str(rear_path), pair.rear)

        pair.front_path = front_path
        pair.rear_path = rear_path
        return pair

    # -- 内部方法 --

    def _open_one(
        self,
        serials: dict[str, int],
        hw: SingleCameraHardware,
        role: str,
    ) -> _CameraHandle:
        """按序列号打开一个相机；序列号为空时按索引 fallback。"""
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

        return _CameraHandle(
            camera=camera,
            stream=stream,
            serial=hw.serial or device_id,
            name=role,
            width=width,
            height=height,
        )

    def _apply_hardware(self, camera: Aravis.Camera, hw: SingleCameraHardware) -> None:
        """应用曝光/增益参数。"""
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

    def _grab_frame(self, handle: _CameraHandle) -> np.ndarray:
        """排空旧帧后等待最新帧，转为 numpy 数组。

        单色相机返回 (H, W) 灰度；Bayer/RGB 返回 (H, W, 3) BGR。
        """
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
