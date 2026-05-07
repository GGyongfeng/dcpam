from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import numpy as np
from rich.console import Console

from .config import load_calibration, load_pipeline_config
from .path import DCPAMPaths
from .steps import (
    back_project,
    extract_spots,
    mirror_transform,
    point_to_line_distance,
    rear_to_front,
)
from .types import LaserAxis, MeasurementResult, Point3D

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
    """6 步测量 pipeline: 拍照 → 光斑提取 → 反投影 → 镜面变换 → 坐标变换 → 距离计算。"""

    def __init__(self, paths: DCPAMPaths) -> None:
        self.calib = load_calibration(paths.calibration_file)
        self.config = load_pipeline_config(paths.pipeline_file)

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
            front_3d = back_project(spots.front, self.calib.front_camera, self.calib.geometry)
            rear_3d = back_project(spots.rear, self.calib.rear_camera, self.calib.geometry)
        console.print(
            f"        front=({front_3d.x:.3f}, {front_3d.y:.3f}, {front_3d.z:.3f})"
            f"  rear=({rear_3d.x:.3f}, {rear_3d.y:.3f}, {rear_3d.z:.3f})",
        )

        with step("4/6 镜面变换"):
            front_virtual = mirror_transform(front_3d, self.calib.geometry, scale=1.0)
            rear_virtual = mirror_transform(rear_3d, self.calib.geometry, scale=2.0)

        with step("5/6 坐标变换"):
            rear_in_c1 = rear_to_front(rear_virtual, self.calib.transform)
            axis = LaserAxis(front=front_virtual, rear=rear_in_c1)

        with step("6/6 距离计算"):
            target = self._target_point()
            distance = point_to_line_distance(target, axis)

        return MeasurementResult(
            uid=uid,
            timestamp=timestamp,
            distance=distance,
            laser_axis=axis,
            target_point=target,
            spots=spots,
        )

    def _target_point(self) -> Point3D:
        """从 ToolConfig 计算被测目标点坐标（暂为 mock）。"""
        mx, my, mz = self.config.tool.mount_position
        return Point3D(x=mx, y=my, z=mz + self.config.tool.bar_length)
