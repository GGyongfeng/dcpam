"""实验性脚本：由已知尺寸矩形图像估计取景框所在平面。

该脚本保留为早期探索版本；当前主流程使用 3_annotate_frame_rectangles.py
先稳定提取内层四边形中心，暂不直接依赖本脚本结果。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from dcpam_cv.config import CameraIntrinsics, PlaneConfig, load_config
from dcpam_cv.path import DCPAMPaths


RECT_WIDTH_MM = 22.0
RECT_HEIGHT_MM = 17.0
EXPECTED_ASPECT = RECT_WIDTH_MM / RECT_HEIGHT_MM
LAYER_NEAR = "near_layer"
LAYER_FAR = "far_layer"


class RectCandidate(BaseModel):
    """图像中的矩形候选框。"""
    left: float
    right: float
    top: float
    bottom: float
    score: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2.0, (self.top + self.bottom) / 2.0)

    def image_points(self) -> np.ndarray:
        """按左上、右上、右下、左下返回角点。"""
        return np.array(
            [
                [self.left, self.top],
                [self.right, self.top],
                [self.right, self.bottom],
                [self.left, self.bottom],
            ],
            dtype=np.float64,
        )

    def scaled(self, factor: float) -> RectCandidate:
        """按比例映射候选框坐标。"""
        return RectCandidate(
            left=self.left * factor,
            right=self.right * factor,
            top=self.top * factor,
            bottom=self.bottom * factor,
            score=self.score,
        )


class PlaneEstimate(BaseModel):
    """单张图片估计出的矩形平面。"""
    position_cm: int
    pair_index: int
    role: str
    layer: str
    image_path: str
    left: float
    right: float
    top: float
    bottom: float
    point_x: float
    point_y: float
    point_z: float
    normal_x: float
    normal_y: float
    normal_z: float
    d: float
    distance_to_image_plane_mm: float


class PlaneSummary(BaseModel):
    """同一相机同一层的平均平面。"""
    role: str
    layer: str
    count: int
    point_x: float
    point_y: float
    point_z: float
    normal_x: float
    normal_y: float
    normal_z: float
    d: float
    mean_distance_to_image_plane_mm: float
    std_distance_to_image_plane_mm: float


class RectanglePlaneEstimator:
    """从已知尺寸矩形图像反推矩形所在平面。"""

    def __init__(
        self,
        dataset_dir: Path,
        output_dir: Path,
        docs_dir: Path,
        work_scale: float,
    ) -> None:
        self.dataset_dir = dataset_dir
        self.output_dir = output_dir
        self.docs_dir = docs_dir
        self.work_scale = work_scale
        self.calibration = load_config(DCPAMPaths().config_file).calibration

    def run(self) -> None:
        """估计所有图片的近/远两层矩形平面并保存结果。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        estimates: list[PlaneEstimate] = []
        debug_images: dict[str, list[np.ndarray]] = {"front": [], "rear": []}

        for path in self._iter_images():
            role = path.parent.name
            intrinsics = self._intrinsics(role)
            image_plane = self._image_plane(role)
            image = _read_gray(path)
            candidates, edge_view = self._detect_rectangles(image)
            for layer, candidate in candidates:
                estimate = self._estimate_plane(path, role, layer, candidate, intrinsics, image_plane)
                estimates.append(estimate)
            if len(debug_images[role]) < 6:
                debug_images[role].append(self._draw_debug(path, image, candidates, edge_view))

        summaries = self._summarize(estimates)
        self._write_csv(self.output_dir / "2-Rectangle-Plane.csv", estimates, PlaneEstimate)
        self._write_csv(self.output_dir / "2-Rectangle-Plane-Summary.csv", summaries, PlaneSummary)
        self._write_montages(debug_images)

    def _iter_images(self) -> list[Path]:
        paths: list[Path] = []
        for group_dir in sorted(self.dataset_dir.glob("L109D*"), key=lambda p: p.name):
            for role in ("front", "rear"):
                paths.extend(sorted((group_dir / role).glob("*.bmp"), key=lambda p: int(p.stem)))
        return paths

    def _intrinsics(self, role: str) -> CameraIntrinsics:
        return self.calibration.front_camera if role == "front" else self.calibration.rear_camera

    def _image_plane(self, role: str) -> PlaneConfig:
        return self.calibration.planes.front_image_real if role == "front" else self.calibration.planes.rear_image_real

    def _detect_rectangles(self, image: np.ndarray) -> tuple[list[tuple[str, RectCandidate]], np.ndarray]:
        work = cv2.resize(image, None, fx=self.work_scale, fy=self.work_scale, interpolation=cv2.INTER_AREA)
        clean = self._remove_laser_spot(work)
        blurred = cv2.GaussianBlur(clean, _odd_kernel(41, self.work_scale), 0)
        grad_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=5)
        grad_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=5)
        profile_x = _smooth(np.abs(grad_x).sum(axis=0), _scaled_size(151, self.work_scale))
        profile_y = _smooth(np.abs(grad_y).sum(axis=1), _scaled_size(151, self.work_scale))

        candidates = self._rectangle_candidates(profile_x, profile_y, work.shape)
        near = max(candidates, key=lambda item: item.area)
        far = self._select_far_layer(candidates, near)
        edge_view = _edge_view(grad_x, grad_y)
        factor = 1.0 / self.work_scale
        return [(LAYER_NEAR, near.scaled(factor)), (LAYER_FAR, far.scaled(factor))], edge_view

    def _remove_laser_spot(self, image: np.ndarray) -> np.ndarray:
        mask = (image > 100).astype(np.uint8) * 255
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        spot_mask = np.zeros_like(image, dtype=np.uint8)
        for index in range(1, count):
            _, _, width, height, area = stats[index]
            if area > image.size * 0.0002 and width < image.shape[1] * 0.35 and height < image.shape[0] * 0.35:
                spot_mask[labels == index] = 255
        kernel_size = _odd_kernel(251, self.work_scale)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel_size)
        spot_mask = cv2.dilate(spot_mask, kernel)
        clean = image.copy()
        background = int(np.median(image[spot_mask == 0])) if np.any(spot_mask == 0) else int(np.median(image))
        clean[spot_mask > 0] = background
        return clean

    def _rectangle_candidates(
        self,
        profile_x: np.ndarray,
        profile_y: np.ndarray,
        image_shape: tuple[int, int],
    ) -> list[RectCandidate]:
        height, width = image_shape
        x_peaks = _profile_peaks(profile_x, count=18, min_separation=_scaled_size(80, self.work_scale))
        y_peaks = _profile_peaks(profile_y, count=18, min_separation=_scaled_size(80, self.work_scale))
        lefts = [peak.index for peak in x_peaks if peak.index < width * 0.58]
        rights = [peak.index for peak in x_peaks if peak.index > width * 0.42]
        tops = [peak.index for peak in y_peaks if peak.index < height * 0.58]
        bottoms = [peak.index for peak in y_peaks if peak.index > height * 0.42]

        candidates: list[RectCandidate] = []
        for left in lefts:
            for right in rights:
                rect_width = right - left
                if rect_width < width * 0.18:
                    continue
                for top in tops:
                    for bottom in bottoms:
                        rect_height = bottom - top
                        if rect_height < height * 0.18:
                            continue
                        aspect = rect_width / rect_height
                        aspect_error = abs(np.log(aspect / EXPECTED_ASPECT))
                        if aspect_error > 0.08:
                            continue
                        edge_score = profile_x[left] + profile_x[right] + profile_y[top] + profile_y[bottom]
                        score = float(edge_score / 1_000_000.0 - 8.0 * aspect_error)
                        candidates.append(
                            RectCandidate(
                                left=float(left),
                                right=float(right),
                                top=float(top),
                                bottom=float(bottom),
                                score=score,
                            ),
                        )
        if not candidates:
            raise ValueError("未找到符合 22x17 比例的矩形候选")
        return sorted(candidates, key=lambda item: item.score, reverse=True)[:40]

    def _select_far_layer(self, candidates: list[RectCandidate], near: RectCandidate) -> RectCandidate:
        near_center = np.array(near.center)
        filtered: list[RectCandidate] = []
        for candidate in candidates:
            if candidate.area >= near.area * 0.96:
                continue
            center_distance = float(np.linalg.norm(np.array(candidate.center) - near_center))
            if center_distance > max(near.width, near.height) * 0.25:
                continue
            filtered.append(candidate)
        if filtered:
            return max(filtered, key=lambda item: item.score)
        alternatives = [item for item in candidates if item != near]
        return max(alternatives, key=lambda item: item.score)

    def _estimate_plane(
        self,
        path: Path,
        role: str,
        layer: str,
        candidate: RectCandidate,
        intrinsics: CameraIntrinsics,
        image_plane: PlaneConfig,
    ) -> PlaneEstimate:
        object_points = np.array(
            [
                [-RECT_WIDTH_MM / 2.0, -RECT_HEIGHT_MM / 2.0, 0.0],
                [RECT_WIDTH_MM / 2.0, -RECT_HEIGHT_MM / 2.0, 0.0],
                [RECT_WIDTH_MM / 2.0, RECT_HEIGHT_MM / 2.0, 0.0],
                [-RECT_WIDTH_MM / 2.0, RECT_HEIGHT_MM / 2.0, 0.0],
            ],
            dtype=np.float64,
        )
        ok, rotation_vector, translation = cv2.solvePnP(
            object_points,
            candidate.image_points(),
            intrinsics.k_matrix(),
            np.array(intrinsics.distortion_coeffs, dtype=np.float64),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            raise ValueError(f"solvePnP 失败: {path}")
        rotation, _ = cv2.Rodrigues(rotation_vector)
        normal = _unit(rotation[:, 2])
        if normal[2] < 0:
            normal = -normal
        point = translation.reshape(3)
        d = -float(normal @ point)
        distance = _plane_distance(point, image_plane)
        position_cm = int(path.parents[1].name.removeprefix("L109D"))
        return PlaneEstimate(
            position_cm=position_cm,
            pair_index=int(path.stem),
            role=role,
            layer=layer,
            image_path=str(path),
            left=candidate.left,
            right=candidate.right,
            top=candidate.top,
            bottom=candidate.bottom,
            point_x=float(point[0]),
            point_y=float(point[1]),
            point_z=float(point[2]),
            normal_x=float(normal[0]),
            normal_y=float(normal[1]),
            normal_z=float(normal[2]),
            d=d,
            distance_to_image_plane_mm=distance,
        )

    def _summarize(self, estimates: list[PlaneEstimate]) -> list[PlaneSummary]:
        summaries: list[PlaneSummary] = []
        for role in ("front", "rear"):
            for layer in (LAYER_NEAR, LAYER_FAR):
                rows = [row for row in estimates if row.role == role and row.layer == layer]
                points = np.array([[row.point_x, row.point_y, row.point_z] for row in rows], dtype=np.float64)
                normals = np.array([[row.normal_x, row.normal_y, row.normal_z] for row in rows], dtype=np.float64)
                distances = np.array([row.distance_to_image_plane_mm for row in rows], dtype=np.float64)
                normal = _unit(normals.mean(axis=0))
                point = points.mean(axis=0)
                d = -float(normal @ point)
                summaries.append(
                    PlaneSummary(
                        role=role,
                        layer=layer,
                        count=len(rows),
                        point_x=float(point[0]),
                        point_y=float(point[1]),
                        point_z=float(point[2]),
                        normal_x=float(normal[0]),
                        normal_y=float(normal[1]),
                        normal_z=float(normal[2]),
                        d=d,
                        mean_distance_to_image_plane_mm=float(distances.mean()),
                        std_distance_to_image_plane_mm=float(distances.std(ddof=0)),
                    ),
                )
        return summaries

    def _draw_debug(
        self,
        path: Path,
        image: np.ndarray,
        candidates: list[tuple[str, RectCandidate]],
        edge_view: np.ndarray,
    ) -> np.ndarray:
        scale = 0.33
        small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        overlay = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        colors = {LAYER_NEAR: (0, 255, 0), LAYER_FAR: (0, 160, 255)}
        for layer, candidate in candidates:
            box = np.array(
                [
                    [candidate.left, candidate.top],
                    [candidate.right, candidate.top],
                    [candidate.right, candidate.bottom],
                    [candidate.left, candidate.bottom],
                ],
                dtype=np.float32,
            )
            box = np.round(box * scale).astype(np.int32)
            cv2.polylines(overlay, [box], True, colors[layer], 2)
            cv2.putText(overlay, layer, tuple(box[0] + np.array([6, 22])), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colors[layer], 2)
        edge_small = cv2.resize(edge_view, (overlay.shape[1], overlay.shape[0]), interpolation=cv2.INTER_AREA)
        panel = np.hstack([overlay, cv2.cvtColor(edge_small, cv2.COLOR_GRAY2BGR)])
        cv2.putText(panel, str(path), (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        return panel

    def _write_montages(self, debug_images: dict[str, list[np.ndarray]]) -> None:
        for role, images in debug_images.items():
            if not images:
                continue
            rows = []
            for index in range(0, len(images), 2):
                row_images = images[index:index + 2]
                if len(row_images) == 1:
                    row_images.append(np.zeros_like(row_images[0]))
                rows.append(np.hstack(row_images))
            montage = np.vstack(rows)
            output = self.docs_dir / f"{role}_rectangle_fit_montage.jpg"
            cv2.imwrite(str(output), montage, [cv2.IMWRITE_JPEG_QUALITY, 72])

    def _write_csv(self, path: Path, rows: list[BaseModel], model: type[BaseModel]) -> None:
        fieldnames = list(model.model_fields)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row.model_dump())


class ProfilePeak(BaseModel):
    """一维梯度投影峰值。"""
    index: int
    value: float


def _read_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"图片读取失败: {path}")
    return image


def _smooth(values: np.ndarray, kernel_size: int) -> np.ndarray:
    kernel = np.ones(kernel_size, dtype=np.float64) / kernel_size
    return np.convolve(values, kernel, mode="same")


def _scaled_size(size: int, scale: float) -> int:
    """按工作图缩放得到至少为 3 的整数尺寸。"""
    return max(3, int(round(size * scale)))


def _odd_kernel(size: int, scale: float) -> tuple[int, int]:
    """按工作图缩放得到 OpenCV 需要的奇数 kernel。"""
    value = _scaled_size(size, scale)
    if value % 2 == 0:
        value += 1
    return value, value


def _profile_peaks(profile: np.ndarray, count: int, min_separation: int) -> list[ProfilePeak]:
    values = profile.copy()
    peaks: list[ProfilePeak] = []
    for _ in range(count):
        index = int(values.argmax())
        peaks.append(ProfilePeak(index=index, value=float(profile[index])))
        values[max(0, index - min_separation): min(len(values), index + min_separation + 1)] = 0
    return peaks


def _edge_view(grad_x: np.ndarray, grad_y: np.ndarray) -> np.ndarray:
    magnitude = np.sqrt(grad_x * grad_x + grad_y * grad_y)
    return cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("零向量不能归一化")
    return vector / norm


def _plane_distance(point: np.ndarray, plane: PlaneConfig) -> float:
    normal = np.array(plane.normal, dtype=np.float64)
    return float(normal @ point + plane.d)


def main() -> None:
    parser = argparse.ArgumentParser(description="利用已知 22x17 mm 圆角矩形反推矩形所在平面")
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset"))
    parser.add_argument("--docs-dir", type=Path, default=Path("docs/rectangle_plane_fit"))
    parser.add_argument("--work-scale", type=float, default=0.35, help="矩形检测工作图缩放比例")
    args = parser.parse_args()

    estimator = RectanglePlaneEstimator(args.dataset, args.output_dir, args.docs_dir, args.work_scale)
    estimator.run()
    print(f"结果: {args.output_dir / '2-Rectangle-Plane.csv'}")
    print(f"汇总: {args.output_dir / '2-Rectangle-Plane-Summary.csv'}")
    print(f"调试图: {args.docs_dir}")


if __name__ == "__main__":
    main()
