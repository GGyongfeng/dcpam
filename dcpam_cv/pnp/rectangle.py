"""从取景框图片中检测内层四边形，并按角色去离群、求平均。

输入：一个目录，下含 front/ 和 rear/ 两个子目录，每个里面是 bmp 图片。
产物：每个角色目录下 rectangle_detection/ 里的内层四边形 csv、
      平均四边形 csv、偏差 csv 以及每张图的可视化 jpg。
"""
from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from ..types import ImageQuadrilateral, Point2D as ImagePoint2D


INNER_THRESHOLD = 20.0
SIDE_BAND_RATIO = 0.09
CORNER_TRIM_RATIO = 0.18


class Point2D(BaseModel):
    x: float
    y: float


class Line2D(BaseModel):
    """二维直线: ax + by + c = 0。"""
    a: float
    b: float
    c: float


class InnerQuadrilateral(BaseModel):
    """内层取景框四边形。"""
    top_left: Point2D
    top_right: Point2D
    bottom_right: Point2D
    bottom_left: Point2D

    @property
    def center(self) -> Point2D:
        points = self.points_array()
        center = points.mean(axis=0)
        return Point2D(x=float(center[0]), y=float(center[1]))

    def points_array(self) -> np.ndarray:
        return np.array(
            [
                [self.top_left.x, self.top_left.y],
                [self.top_right.x, self.top_right.y],
                [self.bottom_right.x, self.bottom_right.y],
                [self.bottom_left.x, self.bottom_left.y],
            ],
            dtype=np.float64,
        )

    def to_image_quadrilateral(self) -> ImageQuadrilateral:
        return ImageQuadrilateral(
            top_left=ImagePoint2D(u=self.top_left.x, v=self.top_left.y),
            top_right=ImagePoint2D(u=self.top_right.x, v=self.top_right.y),
            bottom_right=ImagePoint2D(u=self.bottom_right.x, v=self.bottom_right.y),
            bottom_left=ImagePoint2D(u=self.bottom_left.x, v=self.bottom_left.y),
        )


class InnerQuadrilateralRecord(BaseModel):
    image_path: str
    top_left_x: float
    top_left_y: float
    top_right_x: float
    top_right_y: float
    bottom_right_x: float
    bottom_right_y: float
    bottom_left_x: float
    bottom_left_y: float
    center_x: float
    center_y: float


class InnerQuadrilateralDeviation(BaseModel):
    image_path: str
    corner_rms_px: float
    center_distance_px: float
    included_in_average: bool


class FrameDetection(BaseModel):
    image_path: Path
    role: str
    inner: InnerQuadrilateral


class FrameRectangleAnnotator:
    """检测每张取景框图片的内层四边形，并按角色汇总平均。"""

    def __init__(self, frame_dir: Path, work_scale: float = 0.25, outlier_std_factor: float = 1.0) -> None:
        self.frame_dir = frame_dir
        self.work_scale = work_scale
        self.outlier_std_factor = outlier_std_factor

    def run(self) -> dict[str, InnerQuadrilateral]:
        averages: dict[str, InnerQuadrilateral] = {}
        for role in ("front", "rear"):
            detections = self._detect_role(self.frame_dir / role, role)
            output_dir = self.frame_dir / role / "rectangle_detection"
            output_dir.mkdir(parents=True, exist_ok=True)
            self._remove_stale_outputs(output_dir)

            included, deviations = self._filter_outliers(detections)
            average = self._average_inner(included)
            self._write_records(output_dir, detections, average, deviations)
            for detection in detections:
                image = _read_gray(detection.image_path)
                self._write_detection_image(output_dir, image, detection, average)
            averages[role] = average
        return averages

    def _detect_role(self, role_dir: Path, role: str) -> list[FrameDetection]:
        detections: list[FrameDetection] = []
        for image_path in sorted(role_dir.glob("*.bmp")):
            image = _read_gray(image_path)
            detections.append(self._detect(image_path, role, image))
        return detections

    def _detect(self, image_path: Path, role: str, image: np.ndarray) -> FrameDetection:
        work = cv2.resize(image, None, fx=self.work_scale, fy=self.work_scale, interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(work, (9, 9), 0)
        contour = _inner_contour(blurred)
        quadrilateral = _fit_inner_quadrilateral(contour)
        return FrameDetection(
            image_path=image_path,
            role=role,
            inner=_scale_quadrilateral(quadrilateral, 1.0 / self.work_scale),
        )

    def _average_inner(self, detections: list[FrameDetection]) -> InnerQuadrilateral:
        points = np.array([d.inner.points_array() for d in detections], dtype=np.float64)
        return _quadrilateral_from_array(points.mean(axis=0))

    def _filter_outliers(
        self,
        detections: list[FrameDetection],
    ) -> tuple[list[FrameDetection], list[InnerQuadrilateralDeviation]]:
        rough_average = self._average_inner(detections)
        rms_values = np.array(
            [_corner_rms(d.inner, rough_average) for d in detections],
            dtype=np.float64,
        )
        threshold = float(rms_values.mean() + rms_values.std(ddof=0) * self.outlier_std_factor)

        included: list[FrameDetection] = []
        deviations: list[InnerQuadrilateralDeviation] = []
        for detection, rms in zip(detections, rms_values, strict=True):
            keep = bool(rms <= threshold)
            if keep:
                included.append(detection)
            deviations.append(
                InnerQuadrilateralDeviation(
                    image_path=str(detection.image_path),
                    corner_rms_px=float(rms),
                    center_distance_px=_center_distance(detection.inner, rough_average),
                    included_in_average=keep,
                ),
            )
        return included or detections, deviations

    def _write_detection_image(
        self,
        output_dir: Path,
        image: np.ndarray,
        detection: FrameDetection,
        average: InnerQuadrilateral,
    ) -> None:
        display_scale = 0.28
        small = cv2.resize(image, None, fx=display_scale, fy=display_scale, interpolation=cv2.INTER_AREA)
        overlay = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        _draw_quadrilateral(overlay, detection.inner, display_scale, (0, 255, 0))
        _draw_center(overlay, detection.inner.center, display_scale, (0, 255, 0))
        _draw_quadrilateral(overlay, average, display_scale, (0, 220, 255))
        _draw_center(overlay, average.center, display_scale, (0, 220, 255))
        cv2.imwrite(
            str(output_dir / f"{detection.image_path.stem}_inner.jpg"),
            overlay,
            [cv2.IMWRITE_JPEG_QUALITY, 82],
        )

    def _write_records(
        self,
        output_dir: Path,
        detections: list[FrameDetection],
        average: InnerQuadrilateral,
        deviations: list[InnerQuadrilateralDeviation],
    ) -> None:
        _write_csv(
            output_dir / "inner_quadrilaterals.csv",
            InnerQuadrilateralRecord,
            (_record(d.image_path, d.inner) for d in detections),
        )
        _write_csv(
            output_dir / "average_inner_quadrilateral.csv",
            InnerQuadrilateralRecord,
            [_record(Path("average"), average)],
        )
        _write_csv(
            output_dir / "inner_quadrilateral_deviations.csv",
            InnerQuadrilateralDeviation,
            deviations,
        )

    def _remove_stale_outputs(self, output_dir: Path) -> None:
        stale = (
            "*_outer.jpg",
            "average_rectangles.csv",
            "inner_rectangles.csv",
            "average_inner_rectangle.csv",
        )
        for pattern in stale:
            for path in output_dir.glob(pattern):
                path.unlink()


def _inner_contour(image: np.ndarray) -> np.ndarray:
    mask = (image > INNER_THRESHOLD).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError("未检测到内层取景框轮廓")
    return max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)


def _fit_inner_quadrilateral(contour: np.ndarray) -> InnerQuadrilateral:
    axes_center, x_axis, y_axis = _local_axes(contour)
    local = _to_local(contour, axes_center, x_axis, y_axis)
    sides = _split_side_points(contour, local)
    lines = {name: _fit_line(points) for name, points in sides.items()}
    return InnerQuadrilateral(
        top_left=_intersection(lines["top"], lines["left"]),
        top_right=_intersection(lines["top"], lines["right"]),
        bottom_right=_intersection(lines["bottom"], lines["right"]),
        bottom_left=_intersection(lines["bottom"], lines["left"]),
    )


def _local_axes(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rect = cv2.minAreaRect(points.astype(np.float32).reshape(-1, 1, 2))
    box = cv2.boxPoints(rect).astype(np.float64)
    ordered = _order_points(box)
    x_axis = _unit(ordered[1] - ordered[0])
    y_axis = _unit(ordered[3] - ordered[0])
    return ordered.mean(axis=0), x_axis, y_axis


def _to_local(points: np.ndarray, center: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray) -> np.ndarray:
    shifted = points - center
    return np.column_stack([shifted @ x_axis, shifted @ y_axis])


def _split_side_points(contour: np.ndarray, local: np.ndarray) -> dict[str, np.ndarray]:
    min_x, min_y = local.min(axis=0)
    max_x, max_y = local.max(axis=0)
    width = max_x - min_x
    height = max_y - min_y
    return {
        "top": _side_points(contour, local[:, 1] <= min_y + height * SIDE_BAND_RATIO, local[:, 0], width),
        "bottom": _side_points(contour, local[:, 1] >= max_y - height * SIDE_BAND_RATIO, local[:, 0], width),
        "left": _side_points(contour, local[:, 0] <= min_x + width * SIDE_BAND_RATIO, local[:, 1], height),
        "right": _side_points(contour, local[:, 0] >= max_x - width * SIDE_BAND_RATIO, local[:, 1], height),
    }


def _side_points(
    contour: np.ndarray,
    side_mask: np.ndarray,
    along_axis: np.ndarray,
    side_length: float,
) -> np.ndarray:
    low = np.percentile(along_axis, CORNER_TRIM_RATIO * 100.0)
    high = np.percentile(along_axis, (1.0 - CORNER_TRIM_RATIO) * 100.0)
    mask = side_mask & (along_axis >= low) & (along_axis <= high)
    if int(mask.sum()) >= 20:
        return contour[mask]
    relaxed = side_mask & (along_axis >= low - side_length * 0.08) & (along_axis <= high + side_length * 0.08)
    if int(relaxed.sum()) >= 20:
        return contour[relaxed]
    return contour[side_mask]


def _fit_line(points: np.ndarray) -> Line2D:
    if len(points) < 2:
        raise ValueError("拟合直线至少需要两个点")
    vx, vy, x0, y0 = cv2.fitLine(points.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).reshape(4)
    a = -float(vy)
    b = float(vx)
    norm = float(np.hypot(a, b))
    if norm == 0.0:
        raise ValueError("拟合得到无效直线")
    a /= norm
    b /= norm
    c = -(a * float(x0) + b * float(y0))
    return Line2D(a=a, b=b, c=c)


def _intersection(first: Line2D, second: Line2D) -> Point2D:
    matrix = np.array([[first.a, first.b], [second.a, second.b]], dtype=np.float64)
    vector = -np.array([first.c, second.c], dtype=np.float64)
    det = float(np.linalg.det(matrix))
    if abs(det) < 1e-8:
        raise ValueError("两条直线接近平行，无法求交点")
    point = np.linalg.solve(matrix, vector)
    return Point2D(x=float(point[0]), y=float(point[1]))


def _scale_quadrilateral(quadrilateral: InnerQuadrilateral, scale: float) -> InnerQuadrilateral:
    return _quadrilateral_from_array(quadrilateral.points_array() * scale)


def _quadrilateral_from_array(points: np.ndarray) -> InnerQuadrilateral:
    return InnerQuadrilateral(
        top_left=Point2D(x=float(points[0, 0]), y=float(points[0, 1])),
        top_right=Point2D(x=float(points[1, 0]), y=float(points[1, 1])),
        bottom_right=Point2D(x=float(points[2, 0]), y=float(points[2, 1])),
        bottom_left=Point2D(x=float(points[3, 0]), y=float(points[3, 1])),
    )


def _order_points(points: np.ndarray) -> np.ndarray:
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    ordered = np.zeros((4, 2), dtype=np.float64)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("零向量不能归一化")
    return vector / norm


def _corner_rms(first: InnerQuadrilateral, second: InnerQuadrilateral) -> float:
    diff = first.points_array() - second.points_array()
    return float(np.sqrt(np.mean(np.sum(diff * diff, axis=1))))


def _center_distance(first: InnerQuadrilateral, second: InnerQuadrilateral) -> float:
    dx = first.center.x - second.center.x
    dy = first.center.y - second.center.y
    return float(np.hypot(dx, dy))


def _record(image_path: Path, quadrilateral: InnerQuadrilateral) -> InnerQuadrilateralRecord:
    center = quadrilateral.center
    return InnerQuadrilateralRecord(
        image_path=str(image_path),
        top_left_x=quadrilateral.top_left.x,
        top_left_y=quadrilateral.top_left.y,
        top_right_x=quadrilateral.top_right.x,
        top_right_y=quadrilateral.top_right.y,
        bottom_right_x=quadrilateral.bottom_right.x,
        bottom_right_y=quadrilateral.bottom_right.y,
        bottom_left_x=quadrilateral.bottom_left.x,
        bottom_left_y=quadrilateral.bottom_left.y,
        center_x=center.x,
        center_y=center.y,
    )


def _read_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"图片读取失败: {path}")
    return image


def _draw_quadrilateral(
    overlay: np.ndarray,
    quadrilateral: InnerQuadrilateral,
    scale: float,
    color: tuple[int, int, int],
) -> None:
    points = np.round(quadrilateral.points_array() * scale).astype(np.int32)
    cv2.polylines(overlay, [points], True, color, 2)


def _draw_center(
    overlay: np.ndarray,
    center: Point2D,
    scale: float,
    color: tuple[int, int, int],
) -> None:
    point = (int(round(center.x * scale)), int(round(center.y * scale)))
    cv2.drawMarker(overlay, point, color, cv2.MARKER_CROSS, 20, 2)
    cv2.circle(overlay, point, 4, color, -1)


def _write_csv(path: Path, model: type[BaseModel], rows) -> None:
    fieldnames = list(model.model_fields)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())
