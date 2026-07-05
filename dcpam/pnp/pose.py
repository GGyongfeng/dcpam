"""成像面 PnP 位姿求解。

给定成像面上若干圆点的 3D 坐标（object points，在成像面设备局部坐标系下）
和它们在相机图里的像素坐标（image points），求解
P_camera = R @ P_object + t。
"""
from __future__ import annotations

import itertools

import cv2
import numpy as np
from pydantic import BaseModel

from ..config import CameraIntrinsics
from ..types import Point3D, Pose3D


class FramePoseEstimate(BaseModel):
    """成像面坐标系到相机坐标系的 PnP 估计结果。"""
    pose: Pose3D
    reprojection_error_px: float


class FramePoseEstimator:
    """通用平面 PnP 求解器（无状态）。"""

    def estimate(
        self,
        object_points: np.ndarray,
        image_points: np.ndarray,
        intrinsics: CameraIntrinsics,
    ) -> FramePoseEstimate:
        """在固定对应关系下求解 P_camera = R @ P_object + t。

        object_points: (N, 3)；image_points: (N, 2)，两者一一对应。
        """
        object_points = np.asarray(object_points, dtype=np.float64)
        image_points = np.asarray(image_points, dtype=np.float64)
        camera_matrix = intrinsics.k_matrix()
        distortion = np.array(intrinsics.distortion_coeffs, dtype=np.float64)

        rotation, translation = self._solve_pnp(
            object_points,
            image_points,
            camera_matrix,
            distortion,
        )
        error = _reprojection_error(
            object_points,
            image_points,
            rotation,
            translation,
            camera_matrix,
            distortion,
        )
        return FramePoseEstimate(
            pose=Pose3D(
                rotation=_matrix(rotation),
                translation=Point3D.from_array(translation.reshape(3)),
            ),
            reprojection_error_px=error,
        )

    def estimate_unordered(
        self,
        object_points: np.ndarray,
        image_points: np.ndarray,
        intrinsics: CameraIntrinsics,
    ) -> tuple[FramePoseEstimate, tuple[int, ...]]:
        """image_points 顺序未知时，枚举其全部排列，取重投影误差最小的解。

        object_points 顺序固定（左上, 右上, 中, 左下, 右下）；
        image_points 是图像检测得到、顺序未知的同样多个点。
        返回（最优估计, 采用的排列索引）。
        """
        object_points = np.asarray(object_points, dtype=np.float64)
        image_points = np.asarray(image_points, dtype=np.float64)
        if len(object_points) != len(image_points):
            raise ValueError("object_points 与 image_points 数量不一致")

        best: tuple[FramePoseEstimate, tuple[int, ...]] | None = None
        for permutation in itertools.permutations(range(len(image_points))):
            ordered = image_points[list(permutation)]
            try:
                estimate = self.estimate(object_points, ordered, intrinsics)
            except ValueError:
                continue
            if best is None or estimate.reprojection_error_px < best[0].reprojection_error_px:
                best = (estimate, permutation)
        if best is None:
            raise ValueError("成像面 PnP 位姿求解失败")
        return best

    def _solve_pnp(
        self,
        object_points: np.ndarray,
        image_points: np.ndarray,
        camera_matrix: np.ndarray,
        distortion: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """尝试多种 PnP 求解器，并按重投影误差选最优解。"""
        candidates = []
        candidates.extend(_solve_ippe(object_points, image_points, camera_matrix, distortion))
        candidates.extend(_solve_single(object_points, image_points, camera_matrix, distortion))
        if not candidates:
            raise ValueError("成像面 PnP 位姿求解失败")
        _, rotation, translation = min(candidates, key=lambda item: item[0])
        return rotation, translation


def _solve_ippe(
    object_points: np.ndarray,
    image_points: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    ok, rotations, translations, _ = cv2.solvePnPGeneric(
        object_points,
        image_points,
        camera_matrix,
        distortion,
        flags=cv2.SOLVEPNP_IPPE,
    )
    if not ok:
        return []
    return _valid_candidates(object_points, image_points, camera_matrix, distortion, rotations, translations)


def _solve_single(
    object_points: np.ndarray,
    image_points: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    candidates = []
    for flag in (cv2.SOLVEPNP_ITERATIVE, cv2.SOLVEPNP_SQPNP):
        ok, rotation, translation = cv2.solvePnP(
            object_points,
            image_points,
            camera_matrix,
            distortion,
            flags=flag,
        )
        if not ok:
            continue
        if float(translation.reshape(3)[2]) <= 0:
            continue
        error = _reprojection_error(object_points, image_points, rotation, translation, camera_matrix, distortion)
        candidates.append((error, rotation, translation))
    return candidates


def _valid_candidates(
    object_points: np.ndarray,
    image_points: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    rotations: tuple[np.ndarray, ...],
    translations: tuple[np.ndarray, ...],
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    candidates = []
    for rotation, translation in zip(rotations, translations, strict=True):
        if float(translation.reshape(3)[2]) <= 0:
            continue
        error = _reprojection_error(object_points, image_points, rotation, translation, camera_matrix, distortion)
        candidates.append((error, rotation, translation))
    return candidates


def _reprojection_error(
    object_points: np.ndarray,
    image_points: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> float:
    projected, _ = cv2.projectPoints(object_points, rotation, translation, camera_matrix, distortion)
    residual = projected.reshape(-1, 2) - image_points
    return float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))


def _matrix(rotation_vector: np.ndarray) -> list[list[float]]:
    rotation, _ = cv2.Rodrigues(rotation_vector)
    return rotation.astype(float).tolist()
