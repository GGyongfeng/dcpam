"""Headless 单次采集：从双相机各抓一帧存到 pictures/。

用途：
- 验证 SDK / 相机 / 保存路径都通了
- 不用打开 cv2 窗口，适合远程/无 GUI 场景

在 Windows 上走 gxipy 后端，其他平台走 Aravis —— 由 dcpam.camera.DualCamera 内部派发。

用法：
    uv run python scripts/capture_once.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
from dcpam.camera import DualCamera  # noqa: E402
from dcpam.path import DCPAMPaths  # noqa: E402


def main() -> int:
    paths = DCPAMPaths()
    save_dir = paths.pictures_dir
    save_dir.mkdir(parents=True, exist_ok=True)

    try:
        with DualCamera(paths=paths) as cam:
            print("[ok] 双相机已打开，抓一对帧...")
            pair = cam.capture()
            print(f"[ok] front 帧 shape={pair.front.shape} dtype={pair.front.dtype}")
            print(f"[ok] rear  帧 shape={pair.rear.shape} dtype={pair.rear.dtype}")

            ts = pair.timestamp.strftime("%Y%m%d_%H%M%S")
            front_path = save_dir / f"{ts}_cam1_front.png"
            rear_path = save_dir / f"{ts}_cam2_rear.png"
            cv2.imwrite(str(front_path), pair.front)
            cv2.imwrite(str(rear_path), pair.rear)
            print("[ok] 已保存：")
            print(f"  - {front_path}")
            print(f"  - {rear_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
