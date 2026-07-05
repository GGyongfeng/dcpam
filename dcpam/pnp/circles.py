"""从成像面标定图提取贴在其上的 5 个黑圆点圆心。

每个成像面用不同光照重复拍摄多张（背光/正光/无光/强光），以增强标定鲁棒性。
检测流程：先把灰度拉满动态范围（消除不同图的整体亮度差异），再用
SimpleBlobDetector 多阈值扫描找暗圆斑。每张图应恰好检出 5 个圆心。

同一成像面的多张图是同一姿态重复拍摄，故检出的圆心按绕质心极角排序后
逐点跨图求平均，得到一组低噪声的像素坐标，供 PnP 使用。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from ..types import Point2D


EXPECTED_COUNT = 5


class CircleCenters(BaseModel):
    """一张标定图检出的圆心（已按绕质心极角规范排序）。"""
    image_path: str
    centers: list[Point2D]


class CircleCenterDetector:
    """标定图黑圆圆心检测：单图检出 + 多图平均。"""

    def __init__(self, expected_count: int = EXPECTED_COUNT) -> None:
        self.expected_count = expected_count
        self._detector = _build_detector()

    def detect_image(self, image: np.ndarray, image_path: str = "") -> np.ndarray:
        """单图检出圆心，规范排序后返回 (N, 2) 像素坐标。

        检出数量与 expected_count 不符时抛 ValueError（含图名）。
        """
        normalized = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        keypoints = self._detector.detect(normalized)
        if len(keypoints) != self.expected_count:
            raise ValueError(
                f"圆心检测数量异常: {image_path} 检出 {len(keypoints)} 个，"
                f"期望 {self.expected_count} 个",
            )
        points = np.array([[kp.pt[0], kp.pt[1]] for kp in keypoints], dtype=np.float64)
        return _canonical_order(points)

    def detect_role(self, role_dir: Path) -> np.ndarray:
        """遍历 role_dir 下所有 .bmp，逐图检出圆心并跨图求平均。

        返回 (N, 2) 平均像素坐标，并打印每点的跨图标准差作为质量指标。
        """
        stacks: list[np.ndarray] = []
        for image_path in sorted(role_dir.glob("*.bmp")):
            image = _read_gray(image_path)
            stacks.append(self.detect_image(image, str(image_path)))
        if not stacks:
            raise ValueError(f"目录下没有可用的标定图: {role_dir}")

        array = np.array(stacks)
        average = array.mean(axis=0)
        per_point_std = array.std(axis=0).mean(axis=1)
        print(
            f"[{role_dir.name}] 圆心检测: {len(stacks)} 图, "
            f"每点跨图 std={np.round(per_point_std, 2)} px",
        )
        return average


def _build_detector() -> cv2.SimpleBlobDetector:
    params = cv2.SimpleBlobDetector_Params()
    params.minThreshold = 10
    params.maxThreshold = 220
    params.thresholdStep = 10
    params.filterByColor = True
    params.blobColor = 0
    params.filterByArea = True
    params.minArea = 600
    params.maxArea = 60000
    params.filterByCircularity = True
    params.minCircularity = 0.6
    params.filterByConvexity = True
    params.minConvexity = 0.85
    params.filterByInertia = True
    params.minInertiaRatio = 0.4
    params.minDistBetweenBlobs = 40
    return cv2.SimpleBlobDetector_create(params)


def _canonical_order(points: np.ndarray) -> np.ndarray:
    """绕质心按极角排序，保证同姿态下多张图的点序一致。

    只要跨图排序稳定即可（与 object points 的对应由 PnP 排列择优解决）。
    """
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    order = np.argsort(angles)
    return points[order]


def _read_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"图片读取失败: {path}")
    return image
