"""把 COLMAP 外参结果转换为 calibration.toml 使用的平面表示。

输入是脚本内记录的接收屏/反射屏 COLMAP 位姿；输出是可写入
calibration.toml 的 planes 配置，包括实际成像面和反射面。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
from pydantic import BaseModel


class ColmapPose(BaseModel):
    """COLMAP images.txt 风格的单张图片外参。"""
    qw: float
    qx: float
    qy: float
    qz: float
    tx: float
    ty: float
    tz: float


class Plane(BaseModel):
    """相机坐标系下的平面。"""
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    d: float


class PlaneConverter:
    """把 COLMAP 标定板外参转换为算法直接使用的平面。"""

    def __init__(self, translation_scale: float, image_z_offset_mm: float) -> None:
        self.translation_scale = translation_scale
        self.image_z_offset_mm = image_z_offset_mm

    def board_plane(self, pose: ColmapPose) -> Plane:
        """标定板 z=0 平面在相机坐标系下的表示。"""
        rotation = _rotation_from_colmap_quaternion(pose)
        normal = _unit(rotation[:, 2])
        point = np.array([pose.tx, pose.ty, pose.tz], dtype=np.float64) * self.translation_scale
        return _plane_from_point_normal(point, normal)

    def image_plane(self, pose: ColmapPose) -> Plane:
        """成像面：标定板平面沿相机 +Z 方向偏移 2 mm。"""
        board = self.board_plane(pose)
        point = np.array(board.point, dtype=np.float64)
        point = point + np.array([0.0, 0.0, self.image_z_offset_mm], dtype=np.float64)
        normal = np.array(board.normal, dtype=np.float64)
        return _plane_from_point_normal(point, normal)


_POSES = {
    "front_image_real": ColmapPose(
        qw=0.99894211725101356,
        qx=0.041629173538092784,
        qy=0.0032670746694997057,
        qz=-0.0192609583277078,
        tx=0.089568958305045965,
        ty=1.169589814845861,
        tz=0.32334314027346434,
    ),
    "rear_image_real": ColmapPose(
        qw=0.99897717621314275,
        qx=-0.043336816375192572,
        qy=0.007474341138556574,
        qz=0.010519314436925029,
        tx=0.8404100092877268,
        ty=1.1051767421873566,
        tz=0.20862615865511441,
    ),
    "front_reflection": ColmapPose(
        qw=0.97364224661064569,
        qx=-0.017773449519223234,
        qy=0.22349795803090025,
        qz=0.041875325230739543,
        tx=-4.7857560276513356,
        ty=-0.81876951358304295,
        tz=1.5090820639262519,
    ),
    "rear_reflection": ColmapPose(
        qw=0.96626197672734082,
        qx=-0.10585653485599716,
        qy=0.23332153068748793,
        qz=0.026329634955708021,
        tx=-4.1314707067044427,
        ty=-0.28809156217078657,
        tz=1.1094171744869852,
    ),
}


def _rotation_from_colmap_quaternion(pose: ColmapPose) -> np.ndarray:
    qw, qx, qy, qz = _unit(np.array([pose.qw, pose.qx, pose.qy, pose.qz], dtype=np.float64))
    return np.array(
        [
            [1.0 - 2.0 * qy * qy - 2.0 * qz * qz, 2.0 * qx * qy - 2.0 * qz * qw, 2.0 * qx * qz + 2.0 * qy * qw],
            [2.0 * qx * qy + 2.0 * qz * qw, 1.0 - 2.0 * qx * qx - 2.0 * qz * qz, 2.0 * qy * qz - 2.0 * qx * qw],
            [2.0 * qx * qz - 2.0 * qy * qw, 2.0 * qy * qz + 2.0 * qx * qw, 1.0 - 2.0 * qx * qx - 2.0 * qy * qy],
        ],
        dtype=np.float64,
    )


def _plane_from_point_normal(point: np.ndarray, normal: np.ndarray) -> Plane:
    normal = _unit(normal)
    d = -float(normal @ point)
    return Plane(point=_tuple(point), normal=_tuple(normal), d=d)


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("零向量不能归一化")
    return vector / norm


def _tuple(vector: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(value) for value in vector)


def _format_planes(planes: dict[str, Plane]) -> str:
    blocks = ["[planes]"]
    for name, plane in planes.items():
        blocks.append("")
        blocks.append(f"[planes.{name}]")
        blocks.append(f"point = {_format_array(plane.point)}")
        blocks.append(f"normal = {_format_array(plane.normal)}")
        blocks.append(f"d = {_format_float(plane.d)}")
    return "\n".join(blocks) + "\n"


def _format_array(values: tuple[float, float, float]) -> str:
    return "[" + ", ".join(_format_float(value) for value in values) + "]"


def _format_float(value: float) -> str:
    return f"{value:.12g}"


def _replace_planes_block(text: str, planes_toml: str) -> str:
    stripped = re.sub(r"\n?\[planes\][\s\S]*$", "", text).rstrip()
    return f"{stripped}\n\n{planes_toml}"


def main() -> None:
    parser = argparse.ArgumentParser(description="把 COLMAP 平面外参转换为 calibration.toml 平面配置")
    parser.add_argument("--output", type=Path, default=None, help="写入目标 TOML；省略时只打印")
    parser.add_argument("--translation-scale", type=float, default=10.0, help="COLMAP 平移到 mm 的缩放")
    parser.add_argument("--image-z-offset-mm", type=float, default=2.0, help="成像面相对标定板沿相机 +Z 的偏移")
    args = parser.parse_args()

    converter = PlaneConverter(
        translation_scale=args.translation_scale,
        image_z_offset_mm=args.image_z_offset_mm,
    )
    planes = {
        "front_image_real": converter.image_plane(_POSES["front_image_real"]),
        "rear_image_real": converter.image_plane(_POSES["rear_image_real"]),
        "front_reflection": converter.board_plane(_POSES["front_reflection"]),
        "rear_reflection": converter.board_plane(_POSES["rear_reflection"]),
    }
    planes_toml = _format_planes(planes)
    if args.output is None:
        print(planes_toml, end="")
        return

    existing = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
    args.output.write_text(_replace_planes_block(existing, planes_toml), encoding="utf-8")
    print(f"已写入平面配置: {args.output}")


if __name__ == "__main__":
    main()
