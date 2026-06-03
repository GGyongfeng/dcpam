"""从取景框图片中提取内层四边形中心并生成标注结果。

输入是 dataset/frame/front 与 rear 图片；输出每张图的内层四边形标注、
平均四边形、中心点和离群过滤统计，用于框形约束定位法验证。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel


INNER_THRESHOLD = 20.0
SIDE_BAND_RATIO = 0.09
CORNER_TRIM_RATIO = 0.18


class Point2D(BaseModel):
    """图像二维点。"""
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
        """按左上、右上、右下、左下返回点。"""
        return np.array(
            [
                [self.top_left.x, self.top_left.y],
                [self.top_right.x, self.top_right.y],
                [self.bottom_right.x, self.bottom_right.y],
                [self.bottom_left.x, self.bottom_left.y],
            ],
            dtype=np.float64,
        )


class InnerQuadrilateralRecord(BaseModel):
    """单张图片的内层四边形检测结果。"""
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
    """单张图片相对粗平均四边形的偏差。"""
    image_path: str
    corner_rms_px: float
    center_distance_px: float
    included_in_average: bool


class FrameDetection(BaseModel):
    """单张取景框图片的内层检测结果。"""
    image_path: Path
    role: str
    inner: InnerQuadrilateral


class FrameRectangleAnnotator:
    """提取并标注取景框内层四边形。"""

    def __init__(self, frame_dir: Path, work_scale: float, outlier_std_factor: float) -> None:
        self.frame_dir = frame_dir
        self.work_scale = work_scale
        self.outlier_std_factor = outlier_std_factor

    def run(self) -> list[FrameDetection]:
        """检测所有图片并保存内层四边形标注图。"""
        detections: list[FrameDetection] = []

        for role in ("front", "rear"):
            detections.extend(self._detect_role(self.frame_dir / role, role))

        for role in ("front", "rear"):
            role_detections = [item for item in detections if item.role == role]
            output_dir = self.frame_dir / role / "rectangle_detection"
            output_dir.mkdir(parents=True, exist_ok=True)
            self._remove_stale_outputs(output_dir)

            included, deviations = self._filter_outliers(role_detections)
            average = self._average_inner(included)
            self._write_records(output_dir, role_detections, average, deviations)
            for detection in role_detections:
                image = _read_gray(detection.image_path)
                self._write_detection_image(output_dir, image, detection, average)
        return detections

    def _detect_role(self, role_dir: Path, role: str) -> list[FrameDetection]:
        detections: list[FrameDetection] = []
        for image_path in sorted(role_dir.glob("*.bmp")):
            image = _read_gray(image_path)
            detections.append(self._detect(image_path, role, image))
        return detections

    def _detect(self, image_path: Path, role: str, image: np.ndarray) -> FrameDetection:
        work = cv2.resize(
            image,
            None,
            fx=self.work_scale,
            fy=self.work_scale,
            interpolation=cv2.INTER_AREA,
        )
        blurred = cv2.GaussianBlur(work, (9, 9), 0)
        contour = self._inner_contour(blurred)
        quadrilateral = self._fit_inner_quadrilateral(contour)
        return FrameDetection(
            image_path=image_path,
            role=role,
            inner=_scale_quadrilateral(quadrilateral, 1.0 / self.work_scale),
        )

    def _inner_contour(self, image: np.ndarray) -> np.ndarray:
        mask = (image > INNER_THRESHOLD).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            raise ValueError("未检测到内层取景框轮廓")
        return max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)

    def _fit_inner_quadrilateral(self, contour: np.ndarray) -> InnerQuadrilateral:
        axes = _local_axes(contour)
        local = _to_local(contour, axes)
        sides = _split_side_points(contour, local)
        lines = {name: _fit_line(points) for name, points in sides.items()}
        return InnerQuadrilateral(
            top_left=_intersection(lines["top"], lines["left"]),
            top_right=_intersection(lines["top"], lines["right"]),
            bottom_right=_intersection(lines["bottom"], lines["right"]),
            bottom_left=_intersection(lines["bottom"], lines["left"]),
        )

    def _average_inner(self, detections: list[FrameDetection]) -> InnerQuadrilateral:
        points = np.array(
            [detection.inner.points_array() for detection in detections],
            dtype=np.float64,
        )
        return _quadrilateral_from_array(points.mean(axis=0))

    def _filter_outliers(
        self,
        detections: list[FrameDetection],
    ) -> tuple[list[FrameDetection], list[InnerQuadrilateralDeviation]]:
        rough_average = self._average_inner(detections)
        rms_values = np.array(
            [_corner_rms(detection.inner, rough_average) for detection in detections],
            dtype=np.float64,
        )
        threshold = float(rms_values.mean() + rms_values.std(ddof=0) * self.outlier_std_factor)

        included: list[FrameDetection] = []
        deviations: list[InnerQuadrilateralDeviation] = []
        for detection, rms in zip(detections, rms_values, strict=True):
            included_in_average = bool(rms <= threshold)
            if included_in_average:
                included.append(detection)
            deviations.append(
                InnerQuadrilateralDeviation(
                    image_path=str(detection.image_path),
                    corner_rms_px=float(rms),
                    center_distance_px=_center_distance(detection.inner, rough_average),
                    included_in_average=included_in_average,
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
        overlay = self._draw_inner_image(image, detection.inner, average)
        cv2.imwrite(
            str(output_dir / f"{detection.image_path.stem}_inner.jpg"),
            overlay,
            [cv2.IMWRITE_JPEG_QUALITY, 82],
        )

    def _draw_inner_image(
        self,
        image: np.ndarray,
        detected: InnerQuadrilateral,
        average: InnerQuadrilateral,
    ) -> np.ndarray:
        display_scale = 0.28
        small = cv2.resize(image, None, fx=display_scale, fy=display_scale, interpolation=cv2.INTER_AREA)
        overlay = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        self._draw_quadrilateral(overlay, detected, display_scale, (0, 255, 0))
        self._draw_center(overlay, detected.center, display_scale, (0, 255, 0))
        self._draw_quadrilateral(overlay, average, display_scale, (0, 220, 255))
        self._draw_center(overlay, average.center, display_scale, (0, 220, 255))
        return overlay

    def _draw_quadrilateral(
        self,
        overlay: np.ndarray,
        quadrilateral: InnerQuadrilateral,
        scale: float,
        color: tuple[int, int, int],
    ) -> None:
        points = np.round(quadrilateral.points_array() * scale).astype(np.int32)
        cv2.polylines(overlay, [points], True, color, 2)

    def _draw_center(
        self,
        overlay: np.ndarray,
        center: Point2D,
        scale: float,
        color: tuple[int, int, int],
    ) -> None:
        point = (int(round(center.x * scale)), int(round(center.y * scale)))
        cv2.drawMarker(overlay, point, color, cv2.MARKER_CROSS, 20, 2)
        cv2.circle(overlay, point, 4, color, -1)

    def _write_records(
        self,
        output_dir: Path,
        detections: list[FrameDetection],
        average: InnerQuadrilateral,
        deviations: list[InnerQuadrilateralDeviation],
    ) -> None:
        self._write_detection_records(output_dir / "inner_quadrilaterals.csv", detections)
        self._write_average_record(output_dir / "average_inner_quadrilateral.csv", average)
        self._write_deviation_records(output_dir / "inner_quadrilateral_deviations.csv", deviations)

    def _write_detection_records(self, path: Path, detections: list[FrameDetection]) -> None:
        fieldnames = list(InnerQuadrilateralRecord.model_fields)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for detection in detections:
                writer.writerow(_record(detection.image_path, detection.inner).model_dump())

    def _write_average_record(self, path: Path, average: InnerQuadrilateral) -> None:
        fieldnames = list(InnerQuadrilateralRecord.model_fields)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(_record(Path("average"), average).model_dump())

    def _write_deviation_records(
        self,
        path: Path,
        deviations: list[InnerQuadrilateralDeviation],
    ) -> None:
        fieldnames = list(InnerQuadrilateralDeviation.model_fields)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for deviation in deviations:
                writer.writerow(deviation.model_dump())

    def _remove_stale_outputs(self, output_dir: Path) -> None:
        for pattern in (
            "*_outer.jpg",
            "average_rectangles.csv",
            "inner_rectangles.csv",
            "average_inner_rectangle.csv",
        ):
            for path in output_dir.glob(pattern):
                path.unlink()


class LocalAxes(BaseModel):
    """轮廓局部坐标轴。"""
    center: Point2D
    x_axis: Point2D
    y_axis: Point2D


def _local_axes(points: np.ndarray) -> LocalAxes:
    rect = cv2.minAreaRect(points.astype(np.float32).reshape(-1, 1, 2))
    box = cv2.boxPoints(rect).astype(np.float64)
    ordered = _order_points(box)
    x_axis = _unit(ordered[1] - ordered[0])
    y_axis = _unit(ordered[3] - ordered[0])
    center = ordered.mean(axis=0)
    return LocalAxes(
        center=Point2D(x=float(center[0]), y=float(center[1])),
        x_axis=Point2D(x=float(x_axis[0]), y=float(x_axis[1])),
        y_axis=Point2D(x=float(y_axis[0]), y=float(y_axis[1])),
    )


def _to_local(points: np.ndarray, axes: LocalAxes) -> np.ndarray:
    center = np.array([axes.center.x, axes.center.y], dtype=np.float64)
    x_axis = np.array([axes.x_axis.x, axes.x_axis.y], dtype=np.float64)
    y_axis = np.array([axes.y_axis.x, axes.y_axis.y], dtype=np.float64)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="标注取景框内层四边形和中心")
    parser.add_argument("--frame-dir", type=Path, default=Path("dataset/frame"))
    parser.add_argument("--work-scale", type=float, default=0.25)
    parser.add_argument("--outlier-std-factor", type=float, default=1.0)
    args = parser.parse_args()

    annotator = FrameRectangleAnnotator(args.frame_dir, args.work_scale, args.outlier_std_factor)
    detections = annotator.run()
    print(f"检测完成: {len(detections)} 张")
    print(f"输出目录: {args.frame_dir}")


if __name__ == "__main__":
    main()
