from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

import cv2

from .defaults import DefaultConfigInitializer
from .path import DCPAMPaths
from .pipeline import DCPAMPipeline, console, step
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


def _capture_once(camera, pipeline: DCPAMPipeline, paths: DCPAMPaths, capture_only: bool = False) -> None:
    """单次拍照 + 测量 + 保存结果。"""
    with step("1/6 拍照"):
        pair = camera.capture()
        camera.save(pair)
    h, w = pair.front.shape[:2]
    capture_path = paths.capture_dir(pair.uid)
    console.print(
        f"        uid={pair.uid}  {w}x{h}\n"
        f"        {capture_path}/front.png\n"
        f"        {capture_path}/rear.png",
    )

    if capture_only:
        return

    _run_pipeline(pipeline, paths, pair.uid, pair.timestamp, str(pair.front_path), str(pair.rear_path))


def _mock_once(pipeline: DCPAMPipeline, paths: DCPAMPaths) -> None:
    """mock 模式：从 ~/.dcpam/mock/ 加载图片执行测量。"""
    mock_dir = paths.root / "mock"
    front_path = mock_dir / "front.png"
    rear_path = mock_dir / "rear.png"

    if not front_path.exists() or not rear_path.exists():
        console.print(f"  [bold red]✗[/] mock 图片不存在: {mock_dir}/front.png, rear.png")
        return

    uid = f"M_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    timestamp = datetime.now()

    console.print(f"  [cyan]Mock 模式[/] — 加载 {mock_dir}/")
    _run_pipeline(pipeline, paths, uid, timestamp, str(front_path), str(rear_path))


def _run_pipeline(
    pipeline: DCPAMPipeline,
    paths: DCPAMPaths,
    uid: str,
    timestamp: datetime,
    front_path: str,
    rear_path: str,
) -> None:
    """执行 2-6 步 pipeline 并保存结果。"""
    front_img = cv2.imread(front_path, cv2.IMREAD_GRAYSCALE)
    rear_img = cv2.imread(rear_path, cv2.IMREAD_GRAYSCALE)

    if front_img is None or rear_img is None:
        console.print("  [bold red]✗[/] 图像读取失败，跳过测量")
        return

    try:
        result = pipeline.measure(front_img, rear_img, uid, timestamp)

        result_dir = paths.capture_dir(uid)
        result_dir.mkdir(parents=True, exist_ok=True)
        result_path = result_dir / "result.json"
        result_path.write_text(json.dumps(result.to_record(), indent=2, ensure_ascii=False))

        console.print()
        console.print(f"  [bold green]Distance H = {result.distance:.4f} mm[/]")
        console.print(f"  [dim]Result: {result_path}[/]")
    except ValueError as e:
        console.print(f"  [bold red]✗[/] 测量失败: {e}")


def _interactive(camera, pipeline: DCPAMPipeline, paths: DCPAMPaths, capture_only: bool = False) -> None:
    """交互模式：ENTER 拍照，Q 退出。"""
    console.print("  Press [bold]ENTER[/] to capture, [bold]Q[/] to quit.\n")

    while True:
        user_input = input("> ").strip().lower()
        if user_input == "q":
            break
        if user_input != "":
            continue
        _capture_once(camera, pipeline, paths, capture_only)
        console.print()


def main() -> None:
    """dcpam CLI 入口。"""
    _ensure_aravis_libs()

    parser = argparse.ArgumentParser(description="DCPAM — Dual-Camera Point-to-Axis Measurement")
    parser.add_argument("-o", "--once", action="store_true", help="单次拍照后退出")
    parser.add_argument("-c", "--capture-only", action="store_true", help="仅拍照，跳过测量")
    parser.add_argument("-m", "--mock", action="store_true", help="mock 模式：从 ~/.dcpam/mock/ 加载图片")
    args = parser.parse_args()

    paths = DCPAMPaths()
    paths.ensure_dirs()
    DefaultConfigInitializer(paths).create_missing()

    if args.mock:
        pipeline = DCPAMPipeline(paths)
        _mock_once(pipeline, paths)
        return

    startup(paths)

    from .camera import DualCamera

    pipeline = DCPAMPipeline(paths)

    with DualCamera(paths=paths) as camera:
        if args.once:
            _capture_once(camera, pipeline, paths, args.capture_only)
        else:
            _interactive(camera, pipeline, paths, args.capture_only)

    console.print("  [dim]Cameras closed. Bye.[/]")
