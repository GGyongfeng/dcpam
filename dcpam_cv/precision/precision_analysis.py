"""
精度分析脚本：分析测量误差对点到直线距离 h 的影响
"""

import numpy as np
import warnings
from typing import Dict

warnings.filterwarnings("ignore")


class PrecisionAnalyzer:
    """精度分析器"""

    def __init__(self, screen_distance: float = 10.0):
        """
        初始化精度分析器

        Args:
            screen_distance: 前后屏幕之间的距离 (cm)，默认 10.0 cm
        """
        # 前后屏幕位置（基于屏幕距离，对称分布）
        self.screen_distance = screen_distance
        self.X_F = screen_distance / 2  # P_f 的 x 坐标 (cm)
        self.X_B = -screen_distance / 2  # P_b 的 x 坐标 (cm)

        # 误差范围
        self.error_range = 0.0001  # 1 μm = 0.0001 cm

    def point_to_line_distance(
        self, p_t: np.ndarray, p_f: np.ndarray, p_b: np.ndarray
    ) -> float:
        """
        计算点 P_t 到直线 L (P_f-P_b) 的距离

        公式：h = ||(P_t - P_f) × (P_t - P_b)|| / ||P_f - P_b||

        Args:
            p_t: P_t 坐标 [x, y, z]
            p_f: P_f 坐标 [x, y, z]
            p_b: P_b 坐标 [x, y, z]

        Returns:
            h: 点到直线的距离 (cm)
        """
        # 向量 P_t - P_f 和 P_t - P_b
        v1 = p_t - p_f
        v2 = p_t - p_b

        # 叉积
        cross_product = np.cross(v1, v2)

        # 直线方向向量
        line_vec = p_f - p_b

        # 距离
        h = np.linalg.norm(cross_product) / np.linalg.norm(line_vec)

        return h

    def compute_h(
        self,
        x_t: float,
        y_t: float,
        z_t: float,
        y_f: float,
        z_f: float,
        y_b: float,
        z_b: float,
    ) -> float:
        """
        计算给定参数下的 h 值

        Args:
            x_t, y_t, z_t: P_t 坐标
            y_f, z_f: P_f 的 y, z 坐标
            y_b, z_b: P_b 的 y, z 坐标

        Returns:
            h: 点到直线距离
        """
        p_t = np.array([x_t, y_t, z_t])
        p_f = np.array([self.X_F, y_f, z_f])
        p_b = np.array([self.X_B, y_b, z_b])

        return self.point_to_line_distance(p_t, p_f, p_b)

    def compute_partial_derivatives(
        self,
        x_t: float,
        y_t: float,
        z_t: float,
        y_f: float,
        z_f: float,
        y_b: float,
        z_b: float,
        delta: float = 1e-8,
    ) -> Dict[str, float]:
        """
        计算 h 对各参数的偏导数（数值微分）

        Returns:
            偏导数字典：{'dh_dyf': ..., 'dh_dzf': ..., 'dh_dyb': ..., 'dh_dzb': ...}
        """
        h0 = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b, z_b)

        # ∂h/∂yf
        h_yf = self.compute_h(x_t, y_t, z_t, y_f + delta, z_f, y_b, z_b)
        dh_dyf = (h_yf - h0) / delta

        # ∂h/∂zf
        h_zf = self.compute_h(x_t, y_t, z_t, y_f, z_f + delta, y_b, z_b)
        dh_dzf = (h_zf - h0) / delta

        # ∂h/∂yb
        h_yb = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b + delta, z_b)
        dh_dyb = (h_yb - h0) / delta

        # ∂h/∂zb
        h_zb = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b, z_b + delta)
        dh_dzb = (h_zb - h0) / delta

        return {"dh_dyf": dh_dyf, "dh_dzf": dh_dzf, "dh_dyb": dh_dyb, "dh_dzb": dh_dzb}

    def analytical_error_propagation(
        self,
        x_t: float,
        y_t: float,
        z_t: float,
        y_f: float,
        z_f: float,
        y_b: float,
        z_b: float,
    ) -> Dict[str, float]:
        """
        误差传播解析解

        使用线性误差传播公式：
        σ_h² ≈ (∂h/∂yf)²·σ_yf² + (∂h/∂zf)²·σ_zf² + (∂h/∂yb)²·σ_yb² + (∂h/∂zb)²·σ_zb²

        Returns:
            结果字典，包含 sigma_h 和各参数的方差贡献
        """
        # 计算偏导数
        derivs = self.compute_partial_derivatives(x_t, y_t, z_t, y_f, z_f, y_b, z_b)

        # 各参数的测量误差（假设相同）
        sigma = self.error_range

        # 各参数对 h 的方差贡献
        var_yf = (derivs["dh_dyf"] * sigma) ** 2
        var_zf = (derivs["dh_dzf"] * sigma) ** 2
        var_yb = (derivs["dh_dyb"] * sigma) ** 2
        var_zb = (derivs["dh_dzb"] * sigma) ** 2

        # 总方差
        var_h = var_yf + var_zf + var_yb + var_zb
        sigma_h = np.sqrt(var_h)

        # 方差贡献百分比
        total_var = var_h if var_h > 0 else 1.0

        return {
            "sigma_h": sigma_h,
            "h_nominal": self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b, z_b),
            "derivatives": derivs,
            "variance_contributions": {
                "yf": var_yf / total_var * 100,
                "zf": var_zf / total_var * 100,
                "yb": var_yb / total_var * 100,
                "zb": var_zb / total_var * 100,
            },
        }

    def monte_carlo_simulation(
        self,
        x_t: float,
        y_t: float,
        z_t: float,
        y_f: float,
        z_f: float,
        y_b: float,
        z_b: float,
        n_samples: int = 10000,
    ) -> Dict:
        """
        蒙特卡洛模拟分析

        在测量值 ±1μm 范围内随机采样，统计 h 的分布

        Args:
            n_samples: 采样次数

        Returns:
            统计结果字典
        """
        h_samples = np.zeros(n_samples)

        for i in range(n_samples):
            # 在误差范围内随机采样
            yf_sample = y_f + np.random.uniform(-self.error_range, self.error_range)
            zf_sample = z_f + np.random.uniform(-self.error_range, self.error_range)
            yb_sample = y_b + np.random.uniform(-self.error_range, self.error_range)
            zb_sample = z_b + np.random.uniform(-self.error_range, self.error_range)

            # 计算 h
            h_samples[i] = self.compute_h(
                x_t, y_t, z_t, yf_sample, zf_sample, yb_sample, zb_sample
            )

        # 统计分析
        return {
            "h_samples": h_samples,
            "h_mean": np.mean(h_samples),
            "h_std": np.std(h_samples),
            "h_median": np.median(h_samples),
            "h_95_ci": np.percentile(h_samples, [2.5, 97.5]),
            "h_min": np.min(h_samples),
            "h_max": np.max(h_samples),
        }

    def sensitivity_analysis(
        self,
        x_t: float,
        y_t: float,
        z_t: float,
        y_f: float,
        z_f: float,
        y_b: float,
        z_b: float,
    ) -> Dict[str, float]:
        """
        敏感性分析：单独改变各参数 ±1μm，观察 Δh

        Returns:
            各参数的 Δh 绝对值
        """
        h0 = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b, z_b)

        delta = self.error_range

        # 分别扰动各参数
        h_yf_plus = self.compute_h(x_t, y_t, z_t, y_f + delta, z_f, y_b, z_b)
        h_zf_plus = self.compute_h(x_t, y_t, z_t, y_f, z_f + delta, y_b, z_b)
        h_yb_plus = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b + delta, z_b)
        h_zb_plus = self.compute_h(x_t, y_t, z_t, y_f, z_f, y_b, z_b + delta)

        return {
            "yf": abs(h_yf_plus - h0),
            "zf": abs(h_zf_plus - h0),
            "yb": abs(h_yb_plus - h0),
            "zb": abs(h_zb_plus - h0),
        }
