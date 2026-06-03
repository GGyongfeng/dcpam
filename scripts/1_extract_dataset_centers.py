"""批量提取 dataset 中前后相机光斑圆心。

输入是 dataset/L109D*-vN/front 与 rear 图片；输出是版本化的
1-Spot-Center*.csv，作为后续三维反投影的像素坐标输入。
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from dcpam_cv.config import SpotExtractionConfig
from dcpam_cv.steps.spot_extraction import extract_spots


class ImagePairPaths(BaseModel):
    """一组前后相机图片路径。"""
    dataset_version: str
    position_cm: int
    pair_index: int
    front_path: Path
    rear_path: Path


class CenterRecord(BaseModel):
    """一组图片的圆心提取结果。"""
    dataset_version: str
    position_cm: int
    pair_index: int
    front_path: str
    front_u: float
    front_v: float
    rear_path: str
    rear_u: float
    rear_v: float


class DatasetGroup(BaseModel):
    """一个距离位置下的版本化数据目录。"""
    position_cm: int
    version: str


class DatasetCenterExtractor:
    """批量提取 dataset 中的前后相机光斑圆心。"""

    def __init__(self, dataset_dir: Path, output_path: Path, version: str) -> None:
        self.dataset_dir = dataset_dir
        self.output_path = output_path
        self.version = version
        self.config = SpotExtractionConfig()

    def run(self) -> list[CenterRecord]:
        """提取全部图片对并写入 CSV。"""
        records = [self._extract_pair(pair) for pair in self._iter_pairs()]
        self._write_csv(records)
        return records

    def _iter_pairs(self) -> list[ImagePairPaths]:
        pairs: list[ImagePairPaths] = []
        for group_dir in sorted(self.dataset_dir.iterdir(), key=_path_sort_key):
            if not group_dir.is_dir():
                continue
            group = _parse_group(group_dir.name)
            front_dir = group_dir / "front"
            rear_dir = group_dir / "rear"
            if group is None or group.version != self.version:
                continue
            if not front_dir.exists() or not rear_dir.exists():
                continue

            for front_path in sorted(front_dir.glob("*.bmp"), key=_path_sort_key):
                pair_index = int(front_path.stem)
                rear_path = rear_dir / front_path.name
                if not rear_path.exists():
                    raise FileNotFoundError(f"缺少后相机图片: {rear_path}")
                pairs.append(
                    ImagePairPaths(
                        dataset_version=group.version,
                        position_cm=group.position_cm,
                        pair_index=pair_index,
                        front_path=front_path,
                        rear_path=rear_path,
                    ),
                )
        return pairs

    def _extract_pair(self, pair: ImagePairPaths) -> CenterRecord:
        front_image = _read_gray(pair.front_path)
        rear_image = _read_gray(pair.rear_path)
        spots = extract_spots(front_image, rear_image, self.config)
        return CenterRecord(
            dataset_version=pair.dataset_version,
            position_cm=pair.position_cm,
            pair_index=pair.pair_index,
            front_path=str(pair.front_path),
            front_u=spots.front.u,
            front_v=spots.front.v,
            rear_path=str(pair.rear_path),
            rear_u=spots.rear.u,
            rear_v=spots.rear.v,
        )

    def _write_csv(self, records: list[CenterRecord]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(CenterRecord.model_fields)
        with self.output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.model_dump())


def _read_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"图片读取失败: {path}")
    return image


def _parse_group(name: str) -> DatasetGroup | None:
    match = re.search(r"D(\d+)(?:-(v\d+))?$", name)
    if match is None:
        return None
    return DatasetGroup(
        position_cm=int(match.group(1)),
        version=match.group(2) or "v1",
    )


def _path_sort_key(path: Path) -> tuple[str, int]:
    if path.stem.isdigit():
        return path.parent.name, int(path.stem)
    return path.name, -1


def main() -> None:
    parser = argparse.ArgumentParser(description="批量提取 dataset 前后相机光斑圆心")
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--version", default="v1", help="数据版本，例如 v1 或 v2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output = args.output or _default_output_path(args.dataset, args.version)
    extractor = DatasetCenterExtractor(args.dataset, output, args.version)
    records = extractor.run()
    print(f"提取完成: {len(records)} 组")
    print(f"输出文件: {output}")


def _default_output_path(dataset_dir: Path, version: str) -> Path:
    if version == "v1":
        return dataset_dir / "1-Spot-Center.csv"
    return dataset_dir / f"1-Spot-Center-{version}.csv"


if __name__ == "__main__":
    main()
