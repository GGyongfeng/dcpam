"""反射镜位置/角度灵敏度分析（MC + 单变量扫描）。

从 spot-measurements.csv 读 real_device 坐标（设备坐标系下前/后相机看到的 real 点），
只重跑 mirror_transform → 点到激光线距离，测量镜面参数扰动如何影响每组的距离 σ。

两种模式：
  1) `single`：单变量扫描——每次只扰一个自由度（Δx / Δy / Δz / Δα_x / Δα_y × front/rear = 10 维），
     其它维 = 0，画 σ vs Δ 曲线，拟合斜率作为灵敏度。
  2) `mc`：10 维一起在 ±范围内均匀采样 N 次，得 σ 分布 + 每维单变量偏相关。

输出：JSON 结果 + 简单 markdown 摘要。可后续接进 3-Analysis.html。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class RealPair:
    """一组 pipeline 中的中间产物：设备坐标系下的前/后 real 点 + 靶点。"""
    name: str
    group: str
    front_real: np.ndarray  # (3,)
    rear_real: np.ndarray
    target: np.ndarray


def _load_pairs(csv_path: Path) -> list[RealPair]:
    rows: list[RealPair] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            g = re.match(r"(L586D\d+)", row["name"]).group(1)
            rows.append(RealPair(
                name=row["name"], group=g,
                front_real=np.asarray(json.loads(row["front_real_point_device_mm"]), dtype=np.float64),
                rear_real=np.asarray(json.loads(row["rear_real_point_device_mm"]), dtype=np.float64),
                target=np.asarray(json.loads(row["target_point_device_mm"]), dtype=np.float64),
            ))
    return rows


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _mirror(point: np.ndarray, mirror_point: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """把 point 关于 (mirror_point, normal) 平面做镜像。"""
    n = _unit(normal)
    d = -float(n @ mirror_point)
    signed = float(n @ point + d)
    return point - 2.0 * signed * n


def _point_to_line_distance(target: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """点 target 到过 a、b 的直线的距离。"""
    ab = b - a
    at = target - a
    cross = np.cross(ab, at)
    return float(np.linalg.norm(cross) / np.linalg.norm(ab))


def _distances(pairs: list[RealPair],
               front_pt: np.ndarray, front_n: np.ndarray,
               rear_pt: np.ndarray, rear_n: np.ndarray) -> dict[str, list[float]]:
    """给定一组镜面参数，返回每组的距离列表。"""
    out: dict[str, list[float]] = {}
    for p in pairs:
        f_virt = _mirror(p.front_real, front_pt, front_n)
        r_virt = _mirror(p.rear_real, rear_pt, rear_n)
        d = _point_to_line_distance(p.target, f_virt, r_virt)
        out.setdefault(p.group, []).append(d)
    return out


def _group_sigmas_um(dists: dict[str, list[float]]) -> dict[str, float]:
    return {g: st.stdev(v) * 1000.0 if len(v) >= 2 else 0.0 for g, v in dists.items()}


# ---- baseline & perturbation helpers ----

def _rotation_about_axis(axis: str, angle_deg: float) -> np.ndarray:
    """绕 x 或 y 轴的 3x3 旋转矩阵。"""
    a = np.deg2rad(angle_deg)
    c, s = np.cos(a), np.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    raise ValueError(axis)


def _apply_perturbation(base_pt: np.ndarray, base_n: np.ndarray,
                        d_pos: np.ndarray, d_rot_x_deg: float, d_rot_y_deg: float
                        ) -> tuple[np.ndarray, np.ndarray]:
    """把位置偏移和法向角度绕 x/y 的扰动应用到 (pt, normal) 上。"""
    new_pt = base_pt + d_pos
    n = base_n
    if d_rot_x_deg != 0.0:
        n = _rotation_about_axis("x", d_rot_x_deg) @ n
    if d_rot_y_deg != 0.0:
        n = _rotation_about_axis("y", d_rot_y_deg) @ n
    return new_pt, _unit(n)


# ---- default baseline (from defaults.py) ----
FRONT_PT_BASE = np.array([0.0, 0.0, 23.0])
REAR_PT_BASE  = np.array([80.0, 0.0, 23.0])
N_BASE        = np.array([np.sqrt(2)/2, 0.0, np.sqrt(2)/2])


def single_variate_scan(pairs: list[RealPair], deltas_pos_mm: list[float],
                        deltas_ang_deg: list[float]) -> dict:
    """10 个自由度分别扫描，其它保持 baseline。返回结构：
    {'front_x': [{'delta': +0.1, 'sigmas_by_group': {...}, 'sigma_mean': ...}, ...], ...}
    """
    results = {}
    dof_specs = [
        ("front_x", "front", "pos", 0),
        ("front_y", "front", "pos", 1),
        ("front_z", "front", "pos", 2),
        ("front_rot_x", "front", "rot", "x"),
        ("front_rot_y", "front", "rot", "y"),
        ("rear_x", "rear", "pos", 0),
        ("rear_y", "rear", "pos", 1),
        ("rear_z", "rear", "pos", 2),
        ("rear_rot_x", "rear", "rot", "x"),
        ("rear_rot_y", "rear", "rot", "y"),
    ]
    for dof, side, kind, axis in dof_specs:
        deltas = deltas_pos_mm if kind == "pos" else deltas_ang_deg
        rows = []
        for d in deltas:
            d_pos_f = np.zeros(3); d_rot_x_f = 0.0; d_rot_y_f = 0.0
            d_pos_r = np.zeros(3); d_rot_x_r = 0.0; d_rot_y_r = 0.0
            if side == "front":
                if kind == "pos": d_pos_f[axis] = d
                elif axis == "x": d_rot_x_f = d
                else: d_rot_y_f = d
            else:
                if kind == "pos": d_pos_r[axis] = d
                elif axis == "x": d_rot_x_r = d
                else: d_rot_y_r = d
            f_pt, f_n = _apply_perturbation(FRONT_PT_BASE, N_BASE, d_pos_f, d_rot_x_f, d_rot_y_f)
            r_pt, r_n = _apply_perturbation(REAR_PT_BASE, N_BASE, d_pos_r, d_rot_x_r, d_rot_y_r)
            dists = _distances(pairs, f_pt, f_n, r_pt, r_n)
            sigs = _group_sigmas_um(dists)
            rows.append({
                "delta": d,
                "sigmas_by_group": sigs,
                "sigma_mean": sum(sigs.values()) / len(sigs),
            })
        results[dof] = {"unit": "mm" if kind == "pos" else "deg", "rows": rows}
    return results


def mc_joint(pairs: list[RealPair], N: int, pos_range_mm: float, ang_range_deg: float,
             seed: int = 42) -> dict:
    """10 维联合均匀采样。返回每个样本的 σ_mean + 参数。"""
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(N):
        d_pos_f = rng.uniform(-pos_range_mm, pos_range_mm, 3)
        d_pos_r = rng.uniform(-pos_range_mm, pos_range_mm, 3)
        d_rot_f = rng.uniform(-ang_range_deg, ang_range_deg, 2)
        d_rot_r = rng.uniform(-ang_range_deg, ang_range_deg, 2)
        f_pt, f_n = _apply_perturbation(FRONT_PT_BASE, N_BASE, d_pos_f, d_rot_f[0], d_rot_f[1])
        r_pt, r_n = _apply_perturbation(REAR_PT_BASE, N_BASE, d_pos_r, d_rot_r[0], d_rot_r[1])
        dists = _distances(pairs, f_pt, f_n, r_pt, r_n)
        sigs = _group_sigmas_um(dists)
        samples.append({
            "params": {
                "front_x": float(d_pos_f[0]), "front_y": float(d_pos_f[1]), "front_z": float(d_pos_f[2]),
                "front_rot_x": float(d_rot_f[0]), "front_rot_y": float(d_rot_f[1]),
                "rear_x":  float(d_pos_r[0]), "rear_y":  float(d_pos_r[1]), "rear_z":  float(d_pos_r[2]),
                "rear_rot_x":  float(d_rot_r[0]), "rear_rot_y":  float(d_rot_r[1]),
            },
            "sigma_mean_um": sum(sigs.values()) / len(sigs),
        })
    return {"N": N, "pos_range_mm": pos_range_mm, "ang_range_deg": ang_range_deg, "samples": samples}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("dataset/data-0629/spot-measurements.csv"))
    ap.add_argument("--output", type=Path, default=Path("dataset/mirror_mc_result.json"))
    ap.add_argument("--mc-n", type=int, default=5000)
    ap.add_argument("--pos-range", type=float, default=2.0, help="MC 位置扰动半幅 mm")
    ap.add_argument("--ang-range", type=float, default=1.0, help="MC 角度扰动半幅 deg")
    args = ap.parse_args()

    pairs = _load_pairs(args.input)
    print(f"读入 {len(pairs)} 组数据，分为 {len({p.group for p in pairs})} 组")

    # baseline σ 校验
    base = _distances(pairs, FRONT_PT_BASE, N_BASE, REAR_PT_BASE, N_BASE)
    base_sigmas = _group_sigmas_um(base)
    print("baseline σ / μm：")
    for g, s in base_sigmas.items():
        print(f"  {g}: {s:.1f}")

    deltas_pos = [-2.0, -1.0, -0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5, 1.0, 2.0]
    deltas_ang = [-1.0, -0.5, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.5, 1.0]

    print("单变量扫描...")
    single = single_variate_scan(pairs, deltas_pos, deltas_ang)

    print(f"MC 采样 N={args.mc_n}...")
    mc = mc_joint(pairs, args.mc_n, args.pos_range, args.ang_range)

    out = {
        "input": str(args.input),
        "baseline_sigma_um": base_sigmas,
        "baseline_sigma_mean_um": sum(base_sigmas.values()) / len(base_sigmas),
        "single_variate": single,
        "mc": mc,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"输出: {args.output}")


if __name__ == "__main__":
    main()
