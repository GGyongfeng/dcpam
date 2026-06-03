"""补全光斑测量总表中的 V2 三维虚像点。

默认读取 dataset/spot-measurements.csv，保留 V1 圆心记录，并为 V2
记录写入实像点、虚像点和统一到 C1 坐标系后的三维点。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from dcpam_cv.config import CalibrationConfig, load_calibration
from dcpam_cv.path import DCPAMPaths
from dcpam_cv.steps.back_projection import back_project
from dcpam_cv.steps.coordinate_transform import rear_to_front
from dcpam_cv.steps.mirror_transform import mirror_transform
from dcpam_cv.types import Point2D, Point3D


class SpotCenterRow(BaseModel):
    """圆心 CSV 中的一组前后相机像素坐标。"""
    name: str
    front_u: float
    front_v: float
    rear_u: float
    rear_v: float


class SpotMeasurementRecord(BaseModel):
    """圆心、实像点、虚像点和坐标系统一后的完整记录。"""
    name: str
    front_u: float
    front_v: float
    rear_u: float
    rear_v: float
    front_real_x_cf: float | None = None
    front_real_y_cf: float | None = None
    front_real_z_cf: float | None = None
    rear_real_x_cr: float | None = None
    rear_real_y_cr: float | None = None
    rear_real_z_cr: float | None = None
    front_virtual_x_cf: float | None = None
    front_virtual_y_cf: float | None = None
    front_virtual_z_cf: float | None = None
    rear_virtual_x_cr: float | None = None
    rear_virtual_y_cr: float | None = None
    rear_virtual_z_cr: float | None = None
    rear_virtual_x_cf: float | None = None
    rear_virtual_y_cf: float | None = None
    rear_virtual_z_cf: float | None = None


class SpotCenterProjector:
    """将圆心像素点转换为统一 C1 坐标系下的虚像点。"""

    def __init__(self, calibration: CalibrationConfig) -> None:
        self.calibration = calibration

    def project_rows(self, rows: list[SpotCenterRow]) -> list[SpotMeasurementRecord]:
        """批量处理圆心记录。"""
        return [self._project_row(row) for row in rows]

    def _project_row(self, row: SpotCenterRow) -> SpotMeasurementRecord:
        front_pixel = Point2D(u=row.front_u, v=row.front_v)
        rear_pixel = Point2D(u=row.rear_u, v=row.rear_v)

        front_real = back_project(
            front_pixel,
            self.calibration.front_camera,
            self.calibration.planes.front_image_real,
        )
        rear_real = back_project(
            rear_pixel,
            self.calibration.rear_camera,
            self.calibration.planes.rear_image_real,
        )
        front_virtual = mirror_transform(front_real, self.calibration.planes.front_reflection)
        rear_virtual_cr = mirror_transform(rear_real, self.calibration.planes.rear_reflection)
        rear_virtual_cf = rear_to_front(rear_virtual_cr, self.calibration.transform)

        return SpotMeasurementRecord(
            name=row.name,
            front_u=row.front_u,
            front_v=row.front_v,
            rear_u=row.rear_u,
            rear_v=row.rear_v,
            front_real_x_cf=front_real.x,
            front_real_y_cf=front_real.y,
            front_real_z_cf=front_real.z,
            rear_real_x_cr=rear_real.x,
            rear_real_y_cr=rear_real.y,
            rear_real_z_cr=rear_real.z,
            front_virtual_x_cf=front_virtual.x,
            front_virtual_y_cf=front_virtual.y,
            front_virtual_z_cf=front_virtual.z,
            rear_virtual_x_cr=rear_virtual_cr.x,
            rear_virtual_y_cr=rear_virtual_cr.y,
            rear_virtual_z_cr=rear_virtual_cr.z,
            rear_virtual_x_cf=rear_virtual_cf.x,
            rear_virtual_y_cf=rear_virtual_cf.y,
            rear_virtual_z_cf=rear_virtual_cf.z,
        )


def _read_rows(path: Path, version: str | None = None) -> list[SpotCenterRow]:
    with path.open(newline="", encoding="utf-8") as file:
        rows: list[SpotCenterRow] = []
        for row in csv.DictReader(file):
            rows.append(_center_row_from_csv(row, version))
        return rows


def _read_measurements(path: Path) -> list[SpotMeasurementRecord]:
    with path.open(newline="", encoding="utf-8") as file:
        return [
            SpotMeasurementRecord(**_measurement_row_from_csv(row))
            for row in csv.DictReader(file)
        ]


def _write_records(path: Path, records: list[SpotMeasurementRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(SpotMeasurementRecord.model_fields)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row(record))


def _project_v2_records(
    records: list[SpotMeasurementRecord],
    projector: SpotCenterProjector,
) -> list[SpotMeasurementRecord]:
    projected: list[SpotMeasurementRecord] = []
    for record in records:
        if "-V2-" not in record.name.upper():
            projected.append(record)
            continue
        projected.append(projector.project_rows([_center_row(record)])[0])
    return projected


def _center_row(record: SpotMeasurementRecord) -> SpotCenterRow:
    return SpotCenterRow(
        name=record.name,
        front_u=record.front_u,
        front_v=record.front_v,
        rear_u=record.rear_u,
        rear_v=record.rear_v,
    )


def _center_only_record(row: SpotCenterRow) -> SpotMeasurementRecord:
    return SpotMeasurementRecord(
        name=row.name,
        front_u=row.front_u,
        front_v=row.front_v,
        rear_u=row.rear_u,
        rear_v=row.rear_v,
    )


def _csv_row(record: SpotMeasurementRecord) -> dict[str, str | int | float]:
    row = record.model_dump()
    return {key: "" if value is None else value for key, value in row.items()}


def _none_for_blank(row: dict[str, str]) -> dict[str, str | None]:
    return {key: None if value == "" else value for key, value in row.items()}


def _center_row_from_csv(row: dict[str, str], version: str | None) -> SpotCenterRow:
    if "name" in row:
        return SpotCenterRow(
            name=row["name"],
            front_u=float(row["front_u"]),
            front_v=float(row["front_v"]),
            rear_u=float(row["rear_u"]),
            rear_v=float(row["rear_v"]),
        )
    dataset_version = version or row.get("dataset_version") or "v1"
    return SpotCenterRow(
        name=_sample_name(dataset_version, int(row["position_cm"]), int(row["pair_index"])),
        front_u=float(row["front_u"]),
        front_v=float(row["front_v"]),
        rear_u=float(row["rear_u"]),
        rear_v=float(row["rear_v"]),
    )


def _measurement_row_from_csv(row: dict[str, str]) -> dict[str, str | None]:
    clean = _none_for_blank(row)
    if clean.get("name") is not None:
        return clean
    dataset_version = str(clean["dataset_version"])
    position_cm = int(str(clean["position_cm"]))
    pair_index = int(str(clean["pair_index"]))
    clean["name"] = _sample_name(dataset_version, position_cm, pair_index)
    for key in ("dataset_version", "position_cm", "pair_index", "front_path", "rear_path"):
        clean.pop(key, None)
    return clean


def _sample_name(dataset_version: str, position_cm: int, pair_index: int) -> str:
    return f"L109D{position_cm}-{dataset_version.upper()}-{pair_index:02d}"


def _print_transform(calibration: CalibrationConfig) -> None:
    rotation = calibration.transform.rotation_matrix()
    translation = calibration.transform.translation_vector()
    print("R_rear_from_front:")
    print(np.array2string(rotation, precision=8, suppress_small=False))
    print("t_rear_from_front:")
    print(np.array2string(translation, precision=8, suppress_small=False))
    print(f"baseline_norm: {calibration.transform.baseline_norm:.8f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="补全光斑测量总表的 V2 三维点")
    parser.add_argument("--input", type=Path, default=Path("dataset/spot-measurements.csv"))
    parser.add_argument("--output", type=Path, default=Path("dataset/spot-measurements.csv"))
    parser.add_argument("--calibration", type=Path, default=DCPAMPaths().calibration_file)
    args = parser.parse_args()

    calibration = load_calibration(args.calibration)
    _print_transform(calibration)

    records = _project_v2_records(_read_measurements(args.input), SpotCenterProjector(calibration))
    _write_records(args.output, records)
    print(f"处理完成: {len(records)} 组")
    print(f"输出文件: {args.output}")


if __name__ == "__main__":
    main()
