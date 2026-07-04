"""实验 A：成像面 +3mm × 反射面 +1mm 的 2×2 几何偏移对比。

物理动机（docs/device-physical-spec.md）：
- 成像面：PnP 标的是毛玻璃近相机面(Z=0)，但激光实际打在毛玻璃远相机面（散射面），
  厚 3mm → 成像面可能应沿法向向远离相机方向偏 +3mm。
- 反射面：反射镜厚约 1mm，当前算法用前表面（靠承接屏），可能应用后表面 → 沿法向偏 +1mm。

几何偏移不改圆心像素，故从现成 1-Spot-Center.csv 像素重跑反投影链，比各组内 σ。
用法：uv run python exp/plane-offset/plane_offsets.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import re
import statistics as st
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from dcpam_cv.config import load_config, AppConfig


def _load_projector_module():
    """20_project_spot_centers.py 模块名以数字开头，用 importlib 按路径加载。"""
    path = _ROOT / "scripts" / "20_project_spot_centers.py"
    spec = importlib.util.spec_from_file_location("project20", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IMAGING_OFFSET_MM = 3.0
REFLECTION_OFFSET_MM = 1.0


def _offset_frame_surface(fs, delta_mm: float):
    """成像面沿其法向偏移 delta_mm（相机系）：point += δ·n，d = -n·point 重算。"""
    n = np.array(fs.normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    point = np.array(fs.point, dtype=np.float64) + delta_mm * n
    return fs.model_copy(update={"point": tuple(point), "d": float(-n @ point)})


def _offset_reflection(refl, delta_mm: float):
    """反射面沿其法向偏移 delta_mm（设备系）：point += δ·n。"""
    n = np.array(refl.normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    point = np.array(refl.point, dtype=np.float64) + delta_mm * n
    return refl.model_copy(update={"point": tuple(point)})


def make_config(base: AppConfig, img_off: float, refl_off: float) -> AppConfig:
    calib = base.calibration
    fs = calib.frame_surfaces
    new_fs = fs.model_copy(update={
        "front_frame_pnp": _offset_frame_surface(fs.front_frame_pnp, img_off),
        "rear_frame_pnp": _offset_frame_surface(fs.rear_frame_pnp, img_off),
    })
    geo = base.geometry
    new_geo = geo.model_copy(update={
        "front_reflection": _offset_reflection(geo.front_reflection, refl_off),
        "rear_reflection": _offset_reflection(geo.rear_reflection, refl_off),
    })
    new_calib = calib.model_copy(update={"frame_surfaces": new_fs})
    return base.model_copy(update={"calibration": new_calib, "geometry": new_geo})


def _read_pixels(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _group_sigmas(records, rows) -> dict[str, float]:
    by_group: dict[str, list[float]] = collections.defaultdict(list)
    for rec, row in zip(records, rows):
        group = re.sub(r"-\d+$", "", row["name"])
        by_group[group].append(rec.distance_mm)
    return {g: st.pstdev(v) * 1000.0 for g, v in by_group.items() if len(v) >= 2}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("dataset/samples/1-Spot-Center.csv"))
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()

    from importlib import import_module
    proj_mod = _load_projector_module()

    base = load_config(args.config)
    rows = _read_pixels(args.input)

    print(f"{'成像面偏移':>12} {'反射面偏移':>12} {'平均σ/μm':>10}")
    results = {}
    for img_off in (0.0, IMAGING_OFFSET_MM):
        for refl_off in (0.0, REFLECTION_OFFSET_MM):
            cfg = make_config(base, img_off, refl_off)
            projector = proj_mod.SpotMeasurementProjector(cfg)
            center_rows = [proj_mod.SpotCenterRow(
                name=r["name"], front_u=float(r["front_u"]), front_v=float(r["front_v"]),
                rear_u=float(r["rear_u"]), rear_v=float(r["rear_v"])) for r in rows]
            records = projector.project_rows(center_rows)
            sig = st.mean(_group_sigmas(records, rows).values())
            results[(img_off, refl_off)] = sig
            tag = " ←当前" if (img_off, refl_off) == (0.0, 0.0) else ""
            print(f"{img_off:>10.0f}mm {refl_off:>10.0f}mm {sig:>10.1f}{tag}")

    best = min(results, key=results.get)
    print(f"\n最优组合：成像面+{best[0]:.0f}mm 反射面+{best[1]:.0f}mm → σ={results[best]:.1f}μm"
          f"（当前 {results[(0.0,0.0)]:.1f}μm）")
    return results


if __name__ == "__main__":
    main()
