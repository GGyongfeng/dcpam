"""取景框 PnP 位姿求解。"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel

from ..config import CameraIntrinsics
from ..types import ImageQuadrilateral, Point3D, Pose3D


class FramePoseEstimate(BaseModel):
    """取景框坐标系到相机坐标系的 PnP 估计结果。"""
    pose: Pose3D
    reprojection_error_px: float


class FramePoseEstimator:
    """根据矩形真实尺寸和图像四角点估计取景框位姿。"""

    def __init__(self, width_mm: float, height_mm: float) -> None:
        self.width_mm = width_mm
        self.height_mm = height_mm

    def estimate(
        self,
        corners: ImageQuadrilateral,
        intrinsics: CameraIntrinsics,
    ) -> FramePoseEstimate:
        """使用平面 PnP 求解 P_camera = R @ P_frame + t。"""
        object_points = self._object_points()
        image_points = corners.to_array()
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

    def _object_points(self) -> np.ndarray:
        """以矩形中心为原点，X 向右、Y 向下，按图像角点顺序返回 3D 点。"""
        half_width = self.width_mm / 2.0
        half_height = self.height_mm / 2.0
        return np.array(
            [
                [-half_width, -half_height, 0.0],
                [half_width, -half_height, 0.0],
                [half_width, half_height, 0.0],
                [-half_width, half_height, 0.0],
            ],
            dtype=np.float64,
        )

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
            raise ValueError("取景框 PnP 位姿求解失败")
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
