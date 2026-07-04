"""几何自标定：用各组重复测量的组内方差，反求 config.toml 的 [geometry] 真值。

原理：同一物理点重复测多次，理论上距离应一致；组内方差反映几何参数误差。
最小化「各组组内方差均值 + 真值正则」来求 geometry（反射镜/rear_to_front/靶点杆长）。

数据链（纯 numpy 重算，不重跑 PnP）：
    相机系 real 点 c1/c2  →（camera_to_frame 固定）→ 各取景框局部系
    → rear 经 rear_to_front 并入前框系(=设备系) → 反射镜镜像得虚像点
    → 点到激光线(前虚像→后虚像)的距离 = target 到该线的垂距 → 每组求方差。

用法：
    uv run --with scipy python exp/geometry-selfcal/geometry_selfcal.py \
        --input dataset/samples/spot-measurements.csv --config config.toml
产物：exp/geometry-selfcal/result.toml（优化出的 [geometry]，供人工 review 后合入）。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    """一次测量：两相机系下的 real 点 + 所属组。"""
    group: str
    c1: np.ndarray   # 前相机系 real 点 (3,)
    c2: np.ndarray   # 后相机系 real 点 (3,)


def load_samples(csv_path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with csv_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            group = re.sub(r"-\d+$", "", row["name"])
            samples.append(
                Sample(
                    group=group,
                    c1=np.asarray(json.loads(row["front_real_point_c1_mm"]), dtype=np.float64),
                    c2=np.asarray(json.loads(row["rear_real_point_c2_mm"]), dtype=np.float64),
                )
            )
    return samples


def load_calibration_transforms(config_path: Path) -> tuple[tuple, tuple]:
    """读固定的 camera_to_frame（前/后），返回 ((Rf,tf),(Rr,tr))。"""
    calib = tomllib.load(config_path.open("rb"))["calibration"]

    def rt(cfg: dict) -> tuple[np.ndarray, np.ndarray]:
        return (np.array(cfg["rotation"], dtype=np.float64),
                np.array(cfg["translation"], dtype=np.float64))

    return rt(calib["front_camera_to_frame"]), rt(calib["rear_camera_to_frame"])


# ---------------------------------------------------------------------------
# 前向几何（纯 numpy，与 dcpam_cv pipeline 数学一致）
# ---------------------------------------------------------------------------

def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _mirror(point: np.ndarray, plane_point: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """点关于 (plane_point, normal) 平面镜像：p - 2(n·(p-mp))n。"""
    n = _unit(normal)
    signed = float(n @ point - n @ plane_point)
    return point - 2.0 * signed * n


def _point_to_line_distance(target: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """target 到过 a、b 的直线的垂距 |L×w|/|L|。"""
    L = b - a
    return float(np.linalg.norm(np.cross(L, target - a)) / np.linalg.norm(L))


@dataclass
class Geometry:
    """被优化的几何量，与 config.toml [geometry] 对应。"""
    front_reflection_point: np.ndarray
    front_reflection_normal: np.ndarray
    rear_reflection_point: np.ndarray
    rear_reflection_normal: np.ndarray
    rear_to_front_R: np.ndarray       # 3x3
    rear_to_front_t: np.ndarray       # (3,)
    root: np.ndarray                  # 靶点杆根 (3,)
    length_mm: float

    def target(self) -> np.ndarray:
        return np.array([self.root[0], self.root[1], self.root[2] - self.length_mm])


class ForwardModel:
    """把相机系 real 点前推到 distance；供 loss 反复调用。"""

    def __init__(self, samples: list[Sample], calib: tuple[tuple, tuple]) -> None:
        self.samples = samples
        (self.Rf, self.tf), (self.Rr, self.tr) = calib
        # 预算：front-device 点固定（前框系=设备系）；rear-frame 点固定，只差 rear_to_front。
        self.front_device = [self.Rf @ s.c1 + self.tf for s in samples]
        self.rear_frame = [self.Rr @ s.c2 + self.tr for s in samples]
        self.groups = [s.group for s in samples]

    def distances(self, geo: Geometry) -> dict[str, list[float]]:
        target = geo.target()
        out: dict[str, list[float]] = {}
        for fd, rframe, g in zip(self.front_device, self.rear_frame, self.groups):
            rd = geo.rear_to_front_R @ rframe + geo.rear_to_front_t
            f_virt = _mirror(fd, geo.front_reflection_point, geo.front_reflection_normal)
            r_virt = _mirror(rd, geo.rear_reflection_point, geo.rear_reflection_normal)
            out.setdefault(g, []).append(_point_to_line_distance(target, f_virt, r_virt))
        return out


def group_sigmas_um(dists: dict[str, list[float]]) -> dict[str, float]:
    return {g: st.pstdev(v) * 1000.0 if len(v) >= 2 else 0.0 for g, v in dists.items()}


# ---------------------------------------------------------------------------
# 从 config 读当前 geometry（作 baseline / 优化起点）
# ---------------------------------------------------------------------------

def load_geometry(config_path: Path) -> Geometry:
    geo = tomllib.load(config_path.open("rb"))["geometry"]
    rtf = geo["rear_to_front"]
    return Geometry(
        front_reflection_point=np.array(geo["front_reflection"]["point"], dtype=np.float64),
        front_reflection_normal=np.array(geo["front_reflection"]["normal"], dtype=np.float64),
        rear_reflection_point=np.array(geo["rear_reflection"]["point"], dtype=np.float64),
        rear_reflection_normal=np.array(geo["rear_reflection"]["normal"], dtype=np.float64),
        rear_to_front_R=np.array(rtf["rotation"], dtype=np.float64),
        rear_to_front_t=np.array(rtf["translation"], dtype=np.float64),
        root=np.array(geo["probe_rod"]["root"], dtype=np.float64),
        length_mm=float(geo["probe_rod"]["length_mm"]),
    )


# ---------------------------------------------------------------------------
# 主流程（第一步：仅 baseline 一致性验证）
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 参数化：几何 ↔ 20 维向量（供优化器操作）
# ---------------------------------------------------------------------------
# 布局：[rtf_rvec(3), rtf_t(3), fp(3), f_ang(2), rp(3), r_ang(2), root(3), len(1)]
#   normal 用球坐标 (theta,phi) 保证单位长度；rear_to_front 旋转用旋转向量 rvec。

_LAYOUT = [("rtf_rvec", 3), ("rtf_t", 3), ("fp", 3), ("f_ang", 2),
           ("rp", 3), ("r_ang", 2), ("root", 3), ("len", 1)]


def _rodrigues(rvec: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def _rvec_of(R: np.ndarray) -> np.ndarray:
    angle = float(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
    if angle < 1e-9:
        return np.zeros(3)
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return axis / (2 * np.sin(angle)) * angle


def _normal_to_ang(n: np.ndarray) -> np.ndarray:
    n = _unit(n)
    return np.array([np.arccos(np.clip(n[2], -1, 1)), np.arctan2(n[1], n[0])])


def _ang_to_normal(ang: np.ndarray) -> np.ndarray:
    theta, phi = ang
    return np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])


def geometry_to_vector(geo: Geometry) -> np.ndarray:
    return np.concatenate([
        _rvec_of(geo.rear_to_front_R), geo.rear_to_front_t,
        geo.front_reflection_point, _normal_to_ang(geo.front_reflection_normal),
        geo.rear_reflection_point, _normal_to_ang(geo.rear_reflection_normal),
        geo.root, [geo.length_mm],
    ])


def vector_to_geometry(v: np.ndarray) -> Geometry:
    i, parts = 0, {}
    for name, n in _LAYOUT:
        parts[name] = v[i:i + n]
        i += n
    return Geometry(
        front_reflection_point=parts["fp"],
        front_reflection_normal=_ang_to_normal(parts["f_ang"]),
        rear_reflection_point=parts["rp"],
        rear_reflection_normal=_ang_to_normal(parts["r_ang"]),
        rear_to_front_R=_rodrigues(parts["rtf_rvec"]),
        rear_to_front_t=parts["rtf_t"],
        root=parts["root"],
        length_mm=float(parts["len"][0]),
    )


# ---------------------------------------------------------------------------
# 物理真值锚 + 目标函数
# ---------------------------------------------------------------------------
# 真值来自 docs/device-physical-spec.md：镜面 45°→normal=[√2/2,0,√2/2]；
# rear_to_front 旋转≈I、平移 x≈80mm；root≈[41,0,-132]；杆长 586.051；镜 point 前[0,0,23]后[80,0,23]。
_S2 = np.sqrt(2) / 2
_TRUE_GEO = Geometry(
    front_reflection_point=np.array([0.0, 0.0, 23.0]),
    front_reflection_normal=np.array([_S2, 0.0, _S2]),
    rear_reflection_point=np.array([80.0, 0.0, 23.0]),
    rear_reflection_normal=np.array([_S2, 0.0, _S2]),
    rear_to_front_R=np.eye(3),
    rear_to_front_t=np.array([80.0, 0.0, 0.0]),
    root=np.array([41.0, 0.0, -132.0]),
    length_mm=586.051,
)
# 各参数正则尺度（允许的合理偏移量级；越小=约束越紧）。
_REG_SCALE = np.array([
    0.05, 0.05, 0.05,   # rtf_rvec (rad)：两屏近平行
    3.0, 3.0, 3.0,      # rtf_t (mm)
    5.0, 5.0, 5.0,      # 前镜 point (mm)
    0.05, 0.05,         # 前镜 normal 角 (rad)
    5.0, 5.0, 5.0,      # 后镜 point (mm)
    0.05, 0.05,         # 后镜 normal 角 (rad)
    10.0, 10.0, 10.0,   # root (mm)
    10.0,               # 杆长 (mm)
])
_TRUE_VEC = geometry_to_vector(_TRUE_GEO)


def make_loss(model: ForwardModel, lam: float):
    """loss(v)=组内方差均值(mm²) + lam·Σ((v-true)/scale)²。"""
    def loss(v: np.ndarray) -> float:
        dists = model.distances(vector_to_geometry(v))
        var_mean = float(np.mean([np.var(d) for d in dists.values() if len(d) >= 2]))
        reg = float(np.sum(((v - _TRUE_VEC) / _REG_SCALE) ** 2))
        return var_mean + lam * reg
    return loss


def sigma_and_reg(model: ForwardModel, v: np.ndarray, lam: float) -> tuple[float, float]:
    sig = st.mean(group_sigmas_um(model.distances(vector_to_geometry(v))).values())
    reg = lam * float(np.sum(((v - _TRUE_VEC) / _REG_SCALE) ** 2))
    return sig, reg


# ---------------------------------------------------------------------------
# 优化：MC 粗搜 + scipy 精修（分阶段放开变量）
# ---------------------------------------------------------------------------
# 分阶段：先放开靶点 root+杆长+rear_to_front（最不确定），锁镜面在真值；再放开镜面。
_STAGE1_IDX = list(range(0, 6)) + list(range(16, 20))   # rtf_rvec+t, root, len
_STAGE2_IDX = list(range(0, 20))                         # 全部


def _mc_search(loss, x0: np.ndarray, free_idx: list[int], n: int, rng) -> np.ndarray:
    """在 x0 附近、free_idx 维度上按 _REG_SCALE 采样 n 次，取 loss 最小。"""
    best_x, best_l = x0.copy(), loss(x0)
    for _ in range(n):
        cand = x0.copy()
        for i in free_idx:
            cand[i] = x0[i] + rng.normal(0, _REG_SCALE[i])
        l = loss(cand)
        if l < best_l:
            best_x, best_l = cand, l
    return best_x


def optimize(model: ForwardModel, x0: np.ndarray, lam: float, seed_offset: int = 0):
    from scipy.optimize import minimize
    loss = make_loss(model, lam)
    # 无 Math.random：用固定种子 + 每阶段偏移保证可复现
    x = x0.copy()
    for stage, free_idx, n_mc in [(1, _STAGE1_IDX, 4000), (2, _STAGE2_IDX, 4000)]:
        rng = np.random.default_rng(1234 + seed_offset + stage)
        x = _mc_search(loss, x, free_idx, n_mc, rng)
        # scipy 只在 free_idx 维度上优化：把其它维固定
        mask = np.zeros(len(x), dtype=bool)
        mask[free_idx] = True

        def sub_loss(free_vals, _x=x, _mask=mask):
            full = _x.copy()
            full[_mask] = free_vals
            return loss(full)

        res = minimize(sub_loss, x[mask], method="Nelder-Mead",
                       options={"maxiter": 8000, "xatol": 1e-4, "fatol": 1e-9})
        x[mask] = res.x
    return x


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="几何自标定")
    parser.add_argument("--input", type=Path, default=Path("dataset/samples/spot-measurements.csv"))
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--lam", type=float, default=1.0, help="真值正则权重")
    parser.add_argument("--out", type=Path, default=Path("exp/geometry-selfcal/result.toml"))
    args = parser.parse_args()

    samples = load_samples(args.input)
    calib = load_calibration_transforms(args.config)
    model = ForwardModel(samples, calib)
    geo0 = load_geometry(args.config)
    x0 = geometry_to_vector(geo0)

    base_sig = group_sigmas_um(model.distances(geo0))
    print("=== baseline 组内 σ ===")
    for g in sorted(base_sig):
        print(f"  {g:16} {base_sig[g]:7.1f} μm")
    print(f"  平均 σ = {st.mean(base_sig.values()):.1f} μm\n")

    print(f"优化中（λ={args.lam}）…")
    x_opt = optimize(model, x0, args.lam)
    geo_opt = vector_to_geometry(x_opt)

    opt_sig = group_sigmas_um(model.distances(geo_opt))
    print("\n=== 优化后 组内 σ ===")
    for g in sorted(opt_sig):
        d = opt_sig[g] - base_sig[g]
        print(f"  {g:16} {opt_sig[g]:7.1f} μm   ({'↓' if d < 0 else '↑'}{abs(d):.1f})")
    print(f"  平均 σ = {st.mean(opt_sig.values()):.1f} μm  (baseline {st.mean(base_sig.values()):.1f})")

    s_before, r_before = sigma_and_reg(model, x0, args.lam)
    s_after, r_after = sigma_and_reg(model, x_opt, args.lam)
    print(f"\nloss 拆分：σ项 {s_before:.1f}→{s_after:.1f} μm；正则项 {r_before:.4f}→{r_after:.4f}")

    _print_param_deviations(geo0, geo_opt)
    _write_result_toml(args.out, geo_opt)
    print(f"\n已写出候选 geometry → {args.out}（请人工 review 合理性后再手动合入 config.toml）")


def _print_param_deviations(geo0: Geometry, geo: Geometry) -> None:
    """打印优化后各参数值 + 偏离物理真值多少（防过拟合的人工判据）。"""
    print("\n=== 参数偏离物理真值（人工核）===")
    f_ang = np.degrees(np.arccos(np.clip(_unit(geo.front_reflection_normal)[2], -1, 1)))
    r_ang = np.degrees(np.arccos(np.clip(_unit(geo.rear_reflection_normal)[2], -1, 1)))
    rvec = _rvec_of(geo.rear_to_front_R)
    print(f"  前镜法线倾角 {f_ang:.2f}° (真值 45°)   后镜 {r_ang:.2f}° (45°)")
    print(f"  前镜 point {np.round(geo.front_reflection_point,2)} (真值 [0,0,23])")
    print(f"  后镜 point {np.round(geo.rear_reflection_point,2)} (真值 [80,0,23])")
    print(f"  rear_to_front 旋转角 {np.degrees(np.linalg.norm(rvec)):.3f}° (真值 0)   "
          f"平移 {np.round(geo.rear_to_front_t,2)} (真值 [80,0,0])")
    print(f"  靶点 root {np.round(geo.root,2)} (真值 [41,0,-132])   杆长 {geo.length_mm:.3f} (586.051)")


def _fmt_mat(R: np.ndarray) -> str:
    rows = ",\n".join("    [" + ", ".join(f"{v:.10f}" for v in row) + "]" for row in R)
    return "[\n" + rows + ",\n]"


def _fmt_vec(v) -> str:
    return "[" + ", ".join(f"{float(x):.6f}" for x in v) + "]"


def _write_result_toml(path: Path, geo: Geometry) -> None:
    text = f"""# 几何自标定输出（exp/geometry-selfcal/geometry_selfcal.py）。
# 请人工核对合理性后，手动合入 config.toml 的 [geometry]。

[geometry.front_reflection]
point = {_fmt_vec(geo.front_reflection_point)}
normal = {_fmt_vec(_unit(geo.front_reflection_normal))}

[geometry.rear_reflection]
point = {_fmt_vec(geo.rear_reflection_point)}
normal = {_fmt_vec(_unit(geo.rear_reflection_normal))}

[geometry.probe_rod]
root = {_fmt_vec(geo.root)}
length_mm = {geo.length_mm:.6f}

[geometry.rear_to_front]
rotation = {_fmt_mat(geo.rear_to_front_R)}
translation = {_fmt_vec(geo.rear_to_front_t)}
"""
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

