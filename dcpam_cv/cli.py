from __future__ import annotations

import argparse
import os
import sys

from .path import DCPAMPaths


def _ensure_aravis_libs() -> None:
    """macOS: 确保 Aravis 动态库可被加载，必要时重启进程。"""
    if sys.platform != "darwin":
        return
    brew_lib = "/opt/homebrew/lib"
    key = "DYLD_FALLBACK_LIBRARY_PATH"
    current = os.environ.get(key, "")
    if brew_lib not in current:
        os.environ[key] = brew_lib + (":" + current if current else "")
        os.execv(sys.argv[0], sys.argv)


def _capture_once(camera) -> None:
    """单次拍照并保存。"""
    pair = camera.capture()
    camera.save(pair)

    ts = pair.timestamp.strftime("%H:%M:%S")
    print(f"  [{ts}] Captured pair (uid: {pair.uid})")
    print(f"  Saved: {pair.front_path}")
    print(f"  Saved: {pair.rear_path}")


def _interactive(camera) -> None:
    """交互模式：ENTER 拍照，Q 退出。"""
    print("  Ready. Press ENTER to capture, Q to quit.\n")

    while True:
        user_input = input("> ").strip().lower()
        if user_input == "q":
            break
        if user_input != "":
            continue
        _capture_once(camera)
        print()


def main() -> None:
    """dcpam CLI 入口。"""
    _ensure_aravis_libs()

    from .camera import DualCamera

    parser = argparse.ArgumentParser(description="DCPAM — Dual-Camera Point-to-Axis Measurement")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互模式：ENTER 拍照，Q 退出")
    args = parser.parse_args()

    paths = DCPAMPaths()
    paths.ensure_dirs()

    print("\n  DCPAM — Dual-Camera Point-to-Axis Measurement")
    print(f"  Config: {paths.root}/\n")

    with DualCamera(paths=paths) as camera:
        if args.interactive:
            _interactive(camera)
        else:
            _capture_once(camera)

    print("  Cameras closed. Bye.")
