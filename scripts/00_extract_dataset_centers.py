"""批量提取 dataset 中前后相机光斑圆心。

输入是 dataset/L{测杆长度}D{距离}/front 与 rear 图片。
输出是包含样本 name 的圆心 CSV，作为后续三维反投影的像素坐标输入。
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from dcpam.config import SpotExtractionConfig
from dcpam.steps.spot_extraction import extract_spots


class ImagePairPaths(BaseModel):
    """一组前后相机图片路径。"""
    name: str
    pair_index: int
    front_path: Path
    rear_path: Path


class CenterRecord(BaseModel):
    """一组图片的圆心提取结果。"""
    name: str
    front_path: str
    front_u: float
    front_v: float
    rear_path: str
    rear_u: float
    rear_v: float


class DatasetGroup(BaseModel):
    """一个距离位置下的数据目录。"""
    folder_name: str
    length_mm: int
    position_cm: int


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
        for group_dir in sorted(self.dataset_dir.iterdir(), key=lambda p: p.name):
            if not group_dir.is_dir():
                continue
            group = _parse_group(group_dir.name)
            if group is None:
                continue
            front_dir = _resolve_subdir(group_dir, ("front",))
            rear_dir = _resolve_subdir(group_dir, ("rear", "roar"))
            if front_dir is None or rear_dir is None:
                continue

            for front_path in sorted(front_dir.glob("*.bmp"), key=_path_sort_key):
                pair_index = _extract_pair_index(front_path.stem)
                if pair_index is None:
                    continue
                rear_path = _match_rear_path(rear_dir, pair_index)
                if rear_path is None:
                    raise FileNotFoundError(f"缺少后相机图片: {rear_dir} #{pair_index}")
                pairs.append(
                    ImagePairPaths(
                        name=_sample_name(group, pair_index),
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
            name=pair.name,
            front_path=str(pair.front_path),
            front_u=spots.front.u,
            front_v=spots.front.v,
            rear_path=str(pair.rear_path),
            rear_u=spots.rear.u,
            rear_v=spots.rear.v,
        )

    def _matches_version(self, group: DatasetGroup) -> bool:
        return True

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
    match = re.fullmatch(r"L(\d+)D(\d+)(?:-[A-Za-z0-9_]+)?", name)
    if match is None:
        return None
    length_mm = int(match.group(1))
    position_cm = int(match.group(2))
    return DatasetGroup(
        folder_name=name,
        length_mm=length_mm,
        position_cm=position_cm,
    )


def _sample_name(group: DatasetGroup, pair_index: int) -> str:
    return f"{group.folder_name}-{pair_index:02d}"


def _path_sort_key(path: Path) -> tuple[str, int]:
    index = _extract_pair_index(path.stem)
    if index is not None:
        return path.parent.name, index
    return path.name, -1


def _extract_pair_index(stem: str) -> int | None:
    """从 stem 里抓出"对编号"：

    - 纯数字 "1" / "12"               -> 1 / 12
    - "<数字>_F (12)" / "<数字>_R (12)" -> 12（采集软件常见命名）
    - 否则匹配第一个独立的数字串
    """
    if stem.isdigit():
        return int(stem)
    match = re.search(r"\((\d+)\)", stem)
    if match is not None:
        return int(match.group(1))
    match = re.search(r"(\d+)", stem)
    if match is not None:
        return int(match.group(1))
    return None


def _match_rear_path(rear_dir: Path, pair_index: int) -> Path | None:
    """在 rear_dir 里找一张 pair_index 编号的 .bmp，命名不需要与 front 完全一致。"""
    direct = rear_dir / f"{pair_index}.bmp"
    if direct.exists():
        return direct
    for candidate in rear_dir.glob("*.bmp"):
        if _extract_pair_index(candidate.stem) == pair_index:
            return candidate
    return None


def _resolve_subdir(parent: Path, aliases: tuple[str, ...]) -> Path | None:
    """大小写不敏感地匹配子目录；aliases 还覆盖常见拼写错误（如 roar）。"""
    aliases_lower = {alias.lower() for alias in aliases}
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() in aliases_lower:
            return child
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="批量提取 dataset 前后相机光斑圆心")
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--version", default="all", help="保留兼容参数；当前默认处理全部数据目录")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output = args.output or _default_output_path(args.dataset, args.version)
    extractor = DatasetCenterExtractor(args.dataset, output, args.version)
    records = extractor.run()
    print(f"提取完成: {len(records)} 组")
    print(f"输出文件: {output}")


def _default_output_path(dataset_dir: Path, version: str) -> Path:
    return dataset_dir / "1-Spot-Center.csv"


if __name__ == "__main__":
    main()
