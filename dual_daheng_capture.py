from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np


def _configure_galaxy_python_paths() -> None:
    """Auto-add common Galaxy SDK Python and DLL paths for gxipy import."""
    sdk_roots = [
        Path("D:/Camera_Galaxy/GalaxySDK"),
        Path("C:/Program Files/Daheng Imaging/GalaxySDK"),
        Path("C:/Program Files/GalaxySDK"),
    ]

    for root in sdk_roots:
        py_path = root / "Development" / "Samples" / "Python"
        dll_path = root / "APIDll" / "Win64"
        gentl_path = root / "GenICam" / "bin" / "Win64_x64"

        if py_path.exists() and str(py_path) not in sys.path:
            sys.path.insert(0, str(py_path))

        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        prepend_parts: List[str] = []
        if dll_path.exists() and str(dll_path) not in path_parts:
            prepend_parts.append(str(dll_path))
        if gentl_path.exists() and str(gentl_path) not in path_parts:
            prepend_parts.append(str(gentl_path))

        if prepend_parts:
            os.environ["PATH"] = os.pathsep.join(prepend_parts + [os.environ.get("PATH", "")])


def _check_numpy_version() -> None:
    major = int(np.__version__.split(".")[0])
    if major >= 2:
        print("[ERROR] Detected NumPy >= 2, but current gxipy uses numpy.compat (removed in NumPy 2.x).")
        print("[ERROR] Please run: python -m pip install \"numpy<2\" --upgrade")
        sys.exit(1)


_check_numpy_version()
_configure_galaxy_python_paths()

try:
    import gxipy as gx
except ImportError as exc:
    print("[ERROR] gxipy is not available.")
    print("Install Daheng Galaxy SDK (full package), and ensure SDK Python path is accessible.")
    print("Expected SDK Python path example: D:/Camera_Galaxy/GalaxySDK/Development/Samples/Python")
    print(f"Import error: {exc}")
    sys.exit(1)


@dataclass
class CameraContext:
    camera: object
    name: str
    serial: str


class DualDahengController:
    def __init__(self, save_dir: Path) -> None:
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.device_manager = gx.DeviceManager()
        self.cameras: List[CameraContext] = []

    def open_two_cameras(self) -> None:
        dev_num, dev_info_list = self.device_manager.update_device_list()
        if dev_num < 2:
            raise RuntimeError(f"Need at least 2 cameras, found {dev_num}.")

        for index in range(2):
            cam = self.device_manager.open_device_by_index(index + 1)
            info = dev_info_list[index]
            serial = info.get("sn", f"cam{index + 1}")
            name = info.get("model_name", f"Camera{index + 1}")

            # Use continuous stream for live preview and instant save.
            cam.TriggerMode.set(gx.GxSwitchEntry.OFF)

            if cam.ExposureAuto.is_implemented() and cam.ExposureAuto.is_writable():
                cam.ExposureAuto.set(gx.GxAutoEntry.CONTINUOUS)
            if cam.GainAuto.is_implemented() and cam.GainAuto.is_writable():
                cam.GainAuto.set(gx.GxAutoEntry.CONTINUOUS)

            cam.stream_on()
            self.cameras.append(CameraContext(camera=cam, name=name, serial=serial))

    def close_all(self) -> None:
        for ctx in self.cameras:
            try:
                ctx.camera.stream_off()
            except Exception:
                pass
            try:
                ctx.camera.close_device()
            except Exception:
                pass

    @staticmethod
    def _to_bgr_frame(cam: object, raw_image: object) -> Optional[np.ndarray]:
        if raw_image is None:
            return None

        if cam.PixelColorFilter.is_implemented():
            rgb_image = raw_image.convert("RGB")
            if rgb_image is None:
                return None
            array = rgb_image.get_numpy_array()
            if array is None:
                return None
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)

        array = raw_image.get_numpy_array()
        if array is None:
            return None
        if array.ndim == 2:
            return cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
        return array

    def get_current_frames(self, timeout_ms: int = 1000) -> List[Optional[np.ndarray]]:
        frames: List[Optional[np.ndarray]] = []
        for ctx in self.cameras:
            raw = ctx.camera.data_stream[0].get_image(timeout=timeout_ms)
            frame = self._to_bgr_frame(ctx.camera, raw)
            frames.append(frame)
        return frames

    def save_pair(self, frames: List[Optional[np.ndarray]]) -> List[Path]:
        if len(frames) != 2:
            raise RuntimeError("Expected exactly 2 frames.")
        if any(f is None for f in frames):
            raise RuntimeError("At least one frame is empty, cannot save.")

        ts = time.strftime("%Y%m%d_%H%M%S")
        saved_paths: List[Path] = []

        for i, frame in enumerate(frames, start=1):
            ctx = self.cameras[i - 1]
            file_name = f"{ts}_cam{i}_{ctx.serial}.png"
            out_path = self.save_dir / file_name
            ok = cv2.imwrite(str(out_path), frame)
            if not ok:
                raise RuntimeError(f"Failed to write image: {out_path}")
            saved_paths.append(out_path)

        return saved_paths


def main() -> None:
    save_dir = Path(__file__).resolve().parent / "pictures"
    controller = DualDahengController(save_dir)

    try:
        controller.open_two_cameras()
        print("[INFO] Two cameras opened.")
        print("[INFO] Controls: S=save both cameras, Q=quit")

        last_frames: List[Optional[np.ndarray]] = [None, None]

        while True:
            frames = controller.get_current_frames(timeout_ms=1000)
            last_frames = frames

            for idx, frame in enumerate(frames, start=1):
                title = f"Camera {idx}"
                if frame is None:
                    canvas = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(
                        canvas,
                        "No frame",
                        (180, 180),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 0, 255),
                        2,
                    )
                    cv2.imshow(title, canvas)
                else:
                    cv2.imshow(title, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("s"), ord("S")):
                try:
                    saved = controller.save_pair(last_frames)
                    print("[INFO] Saved:")
                    for path in saved:
                        print(f"  - {path}")
                except RuntimeError as err:
                    print(f"[WARN] {err}")

    except Exception as err:
        print(f"[ERROR] {err}")
    finally:
        controller.close_all()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
