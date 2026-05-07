from __future__ import annotations

import argparse
import json
import os
import sys

import cv2

from .path import DCPAMPaths
from .pipeline import DCPAMPipeline
from .startup import startup


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


def _capture_once(camera, pipeline: DCPAMPipeline, paths: DCPAMPaths) -> None:
    """单次拍照 + 测量 + 保存结果。"""
    pair = camera.capture()
    camera.save(pair)

    ts = pair.timestamp.strftime("%H:%M:%S")
    print(f"  [{ts}] Captured pair (uid: {pair.uid})")
    print(f"  Saved: {pair.front_path}")
    print(f"  Saved: {pair.rear_path}")

    front_img = cv2.imread(str(pair.front_path), cv2.IMREAD_GRAYSCALE)
    rear_img = cv2.imread(str(pair.rear_path), cv2.IMREAD_GRAYSCALE)

    if front_img is None or rear_img is None:
        print("  [WARN] 图像读取失败，跳过测量")
        return

    try:
        result = pipeline.measure(front_img, rear_img, pair.uid, pair.timestamp)

        result_path = paths.capture_dir(pair.uid) / "result.json"
        result_path.write_text(json.dumps(result.to_record(), indent=2, ensure_ascii=False))

        print(f"  [bold green]Distance H = {result.distance:.4f}[/]")
        print(f"  Result: {result_path}")
    except ValueError as e:
        print(f"  [WARN] 测量失败: {e}")


def _interactive(camera, pipeline: DCPAMPipeline, paths: DCPAMPaths) -> None:
    """交互模式：ENTER 拍照，Q 退出。"""
    print("  Press ENTER to capture, Q to quit.\n")

    while True:
        user_input = input("> ").strip().lower()
        if user_input == "q":
            break
        if user_input != "":
            continue
        _capture_once(camera, pipeline, paths)
        print()


def main() -> None:
    """dcpam CLI 入口。"""
    _ensure_aravis_libs()

    parser = argparse.ArgumentParser(description="DCPAM — Dual-Camera Point-to-Axis Measurement")
    parser.add_argument("-o", "--once", action="store_true", help="单次拍照后退出")
    args = parser.parse_args()

    paths = DCPAMPaths()
    paths.ensure_dirs()

    startup(paths)

    from .camera import DualCamera

    pipeline = DCPAMPipeline(paths)

    with DualCamera(paths=paths) as camera:
        if args.once:
            _capture_once(camera, pipeline, paths)
        else:
            _interactive(camera, pipeline, paths)

    print("  Cameras closed. Bye.")
