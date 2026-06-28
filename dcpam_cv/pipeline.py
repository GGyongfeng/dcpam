from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import numpy as np
from rich.console import Console

from .config import load_config
from .optical_geometry import OpticalGeometry
from .path import DCPAMPaths
from .steps import back_project, extract_spots, mirror_transform, point_to_line_distance
from .types import LaserAxis, MeasurementResult

console = Console()


@contextmanager
def step(name: str) -> Generator[None, None, None]:
    """带 spinner 和计时的步骤上下文管理器。"""
    with console.status(f"  [cyan]{name}[/]", spinner="dots"):
        t0 = time.perf_counter()
        yield
    elapsed = (time.perf_counter() - t0) * 1000
    console.print(f"  [green]✓[/] {name}  [dim]{elapsed:.1f}ms[/]")


class DCPAMPipeline:
    """5 步设备坐标系测量 pipeline:
    拍照 → 光斑提取 → 反投影 → 实像点入设备系 → 设备系镜像 → 距离计算。
    """

    def __init__(self, paths: DCPAMPaths) -> None:
        config = load_config(paths.config_file)
        self.calib = config.calibration
        self.config = config.pipeline
        self.device = config.device
        self.optics = OpticalGeometry(self.calib, self.device)

    def measure(
        self,
        front_image: np.ndarray,
        rear_image: np.ndarray,
        uid: str,
        timestamp: datetime,
    ) -> MeasurementResult:
        """从前后相机图像计算目标点到激光轴线的距离（步骤 2-6）。"""
        with step("2/6 光斑提取"):
            spots = extract_spots(front_image, rear_image, self.config.spot_extraction)
        console.print(
            f"        front=({spots.front.u:.1f}, {spots.front.v:.1f})"
            f"  rear=({spots.rear.u:.1f}, {spots.rear.v:.1f})",
        )

        with step("3/6 反投影"):
            front_real_cam = back_project(spots.front, self.calib.front_camera, self.optics.front_image_real)
            rear_real_cam = back_project(spots.rear, self.calib.rear_camera, self.optics.rear_image_real)
        console.print(
            f"        front_C1=({front_real_cam.x:.3f}, {front_real_cam.y:.3f}, {front_real_cam.z:.3f})"
            f"  rear_C2=({rear_real_cam.x:.3f}, {rear_real_cam.y:.3f}, {rear_real_cam.z:.3f})",
        )

        with step("4/6 实像点入设备系"):
            front_real = self.optics.front_camera_to_device.point(front_real_cam)
            rear_real = self.optics.rear_camera_to_device.point(rear_real_cam)
        console.print(
            f"        front=({front_real.x:.3f}, {front_real.y:.3f}, {front_real.z:.3f})"
            f"  rear=({rear_real.x:.3f}, {rear_real.y:.3f}, {rear_real.z:.3f})",
        )

        with step("5/6 设备系镜像"):
            front_virtual = mirror_transform(front_real, self.optics.front_reflection)
            rear_virtual = mirror_transform(rear_real, self.optics.rear_reflection)
            axis = LaserAxis(front=front_virtual, rear=rear_virtual)

        with step("6/6 距离计算"):
            target = self.optics.target_point
            distance = point_to_line_distance(target, axis)

        return MeasurementResult(
            uid=uid,
            timestamp=timestamp,
            distance=distance,
            laser_axis=axis,
            target_point=target,
            spots=spots,
        )
