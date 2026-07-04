"""生成光斑测量总表 dataset/spot-measurements.csv。

从圆心 CSV 读取前后相机像素点，在各自相机坐标系下反投影到 PnP 实像面，
再用取景框 PnP 与设备实像面的对齐关系把实像点转入设备坐标系。镜像反射、
激光线、靶点距离全部在设备坐标系中完成。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from pydantic import BaseModel

from dcpam_cv.config import AppConfig, load_config
from dcpam_cv.optical_geometry import OpticalGeometry
from dcpam_cv.path import DCPAMPaths
from dcpam_cv.steps.back_projection import back_project
from dcpam_cv.steps.distance import point_to_line_distance
from dcpam_cv.steps.mirror_transform import mirror_transform
from dcpam_cv.types import LaserAxis, Point2D


class SpotCenterRow(BaseModel):
    """圆心 CSV 中的一组前后相机像素坐标。"""

    name: str
    front_u: float
    front_v: float
    rear_u: float
    rear_v: float


class SpotMeasurementRecord(BaseModel):
    """写入光斑测量总表的可追踪结果。"""

    name: str
    spot_input_vector: str
    front_real_point_c1_mm: str
    rear_real_point_c2_mm: str
    front_real_point_device_mm: str
    rear_real_point_device_mm: str
    front_virtual_point_device_mm: str
    rear_virtual_point_device_mm: str
    target_point_device_mm: str
    laser_line_device_mm: str
    distance_mm: float


class SpotMeasurementProjector:
    """在设备坐标系中完成镜像和距离计算的光斑测量 pipeline。"""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.optics = OpticalGeometry(config.calibration, config.geometry)

    def project_rows(self, rows: list[SpotCenterRow]) -> list[SpotMeasurementRecord]:
        return [self._project_row(row) for row in rows]

    def _project_row(self, row: SpotCenterRow) -> SpotMeasurementRecord:
        front_pixel = Point2D(u=row.front_u, v=row.front_v)
        rear_pixel = Point2D(u=row.rear_u, v=row.rear_v)

        front_real_c1 = back_project(
            front_pixel,
            self.config.calibration.front_camera,
            self.optics.front_image_real,
        )
        rear_real_c2 = back_project(
            rear_pixel,
            self.config.calibration.rear_camera,
            self.optics.rear_image_real,
        )
        front_real_device = self.optics.front_camera_to_device.point(front_real_c1)
        rear_real_device = self.optics.rear_camera_to_device.point(rear_real_c2)
        front_virtual_device = mirror_transform(front_real_device, self.optics.front_reflection)
        rear_virtual_device = mirror_transform(rear_real_device, self.optics.rear_reflection)
        distance = point_to_line_distance(
            self.optics.target_point,
            LaserAxis(front=front_virtual_device, rear=rear_virtual_device),
        )

        return SpotMeasurementRecord(
            name=row.name,
            spot_input_vector=_json_vector(
                [
                    row.front_u,
                    row.front_v,
                    row.rear_u,
                    row.rear_v,
                    _length_from_name(row.name),
                ],
            ),
            front_real_point_c1_mm=_json_vector(front_real_c1.to_array().tolist()),
            rear_real_point_c2_mm=_json_vector(rear_real_c2.to_array().tolist()),
            front_real_point_device_mm=_json_vector(front_real_device.to_array().tolist()),
            rear_real_point_device_mm=_json_vector(rear_real_device.to_array().tolist()),
            front_virtual_point_device_mm=_json_vector(front_virtual_device.to_array().tolist()),
            rear_virtual_point_device_mm=_json_vector(rear_virtual_device.to_array().tolist()),
            target_point_device_mm=_json_vector(self.optics.target_point.to_array().tolist()),
            laser_line_device_mm=_json_vector(
                [
                    front_virtual_device.to_array().tolist(),
                    rear_virtual_device.to_array().tolist(),
                ],
            ),
            distance_mm=distance,
        )


def _read_rows(path: Path) -> list[SpotCenterRow]:
    with path.open(newline="", encoding="utf-8") as file:
        return [_center_row_from_csv(row) for row in csv.DictReader(file)]


def _write_records(path: Path, records: list[SpotMeasurementRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(SpotMeasurementRecord.model_fields))
        writer.writeheader()
        for record in records:
            writer.writerow(record.model_dump())


def _center_row_from_csv(row: dict[str, str]) -> SpotCenterRow:
    if "spot_input_vector" in row:
        input_vector = json.loads(row["spot_input_vector"])
        return SpotCenterRow(
            name=row["name"],
            front_u=float(input_vector[0]),
            front_v=float(input_vector[1]),
            rear_u=float(input_vector[2]),
            rear_v=float(input_vector[3]),
        )
    return SpotCenterRow(
        name=row["name"],
        front_u=float(row["front_u"]),
        front_v=float(row["front_v"]),
        rear_u=float(row["rear_u"]),
        rear_v=float(row["rear_v"]),
    )


def _json_vector(values: list[float] | list[list[float]]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _length_from_name(name: str) -> float:
    match = re.match(r"L(\d+)D\d+", name)
    if match is None:
        raise ValueError(f"无法从样本名解析杆长: {name}")
    return float(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description="用设备坐标系 pipeline 生成光斑测量总表")
    parser.add_argument("--input", type=Path, default=Path("dataset/1-Spot-Center.csv"))
    parser.add_argument("--output", type=Path, default=Path("dataset/spot-measurements.csv"))
    parser.add_argument("--config", type=Path, default=DCPAMPaths().config_file)
    args = parser.parse_args()

    config = load_config(args.config)
    records = SpotMeasurementProjector(config).project_rows(_read_rows(args.input))
    _write_records(args.output, records)
    print(f"处理完成: {len(records)} 组")
    print(f"输出文件: {args.output}")


if __name__ == "__main__":
    main()
