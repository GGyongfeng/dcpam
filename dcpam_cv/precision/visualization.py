"""
可视化模块：3D 模型、分布图、敏感性图
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict
import platform

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dcpam_cv.precision.precision_analysis import PrecisionAnalyzer


# 配置中文字体
def setup_chinese_font():
    """配置 matplotlib 支持中文显示"""
    system = platform.system()

    if system == "Darwin":  # macOS
        plt.rcParams["font.sans-serif"] = [
            "Arial Unicode MS",
            "PingFang SC",
            "STHeiti",
            "SimHei",
        ]
    elif system == "Windows":
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
    else:  # Linux
        plt.rcParams["font.sans-serif"] = [
            "WenQuanYi Micro Hei",
            "Droid Sans Fallback",
            "SimHei",
        ]

    plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题


# 初始化字体配置
setup_chinese_font()


def plot_3d_model(
    analyzer: "PrecisionAnalyzer",
    x_t: float,
    y_t: float,
    z_t: float,
    y_f: float,
    z_f: float,
    y_b: float,
    z_b: float,
    save_path: str = None,
):
    """
    绘制 3D 空间模型

    显示：
    - P_t, P_f, P_b 三个点
    - 直线 L (P_f-P_b)
    - 垂直距离 h
    - 两个接收屏
    """
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    # 点坐标
    p_t = np.array([x_t, y_t, z_t])
    p_f = np.array([analyzer.X_F, y_f, z_f])
    p_b = np.array([analyzer.X_B, y_b, z_b])

    # 绘制点
    ax.scatter(*p_t, color="red", s=100, marker="o", label="P_t (目标点)", zorder=5)
    ax.scatter(*p_f, color="blue", s=100, marker="s", label="P_f (前接收屏)", zorder=5)
    ax.scatter(*p_b, color="green", s=100, marker="^", label="P_b (后接收屏)", zorder=5)

    # 绘制直线 L (延长显示)
    direction = p_f - p_b
    t_vals = np.linspace(-0.5, 1.5, 100)
    line_points = p_b[:, np.newaxis] + direction[:, np.newaxis] * t_vals
    ax.plot(
        line_points[0],
        line_points[1],
        line_points[2],
        "b--",
        linewidth=2,
        label="直线 L (P_f-P_b)",
        alpha=0.6,
    )

    # 计算垂足（P_t 在直线 L 上的投影）
    t_proj = np.dot(p_t - p_b, direction) / np.dot(direction, direction)
    p_proj = p_b + t_proj * direction

    # 绘制垂直距离 h
    ax.plot(
        [p_t[0], p_proj[0]],
        [p_t[1], p_proj[1]],
        [p_t[2], p_proj[2]],
        "r-",
        linewidth=2,
        label="距离 h",
        alpha=0.8,
    )
    ax.scatter(*p_proj, color="orange", s=50, marker="x", zorder=5)

    # 绘制接收屏（简化为正方形）
    screen_size = 2.0  # 2cm × 2cm

    def draw_screen(x_pos, color, alpha=0.2):
        """绘制接收屏"""
        y_range = np.array([-screen_size / 2, screen_size / 2])
        z_range = np.array([-screen_size / 2, screen_size / 2])
        Y, Z = np.meshgrid(y_range, z_range)
        X = np.full_like(Y, x_pos)
        ax.plot_surface(X, Y, Z, color=color, alpha=alpha)

    draw_screen(analyzer.X_F, "blue", alpha=0.15)
    draw_screen(analyzer.X_B, "green", alpha=0.15)

    # 设置坐标轴
    ax.set_xlabel("X (cm)", fontsize=10)
    ax.set_ylabel("Y (cm)", fontsize=10)
    ax.set_zlabel("Z (cm)", fontsize=10)
    ax.set_title("3D 空间模型：点到直线距离", fontsize=12, fontweight="bold")

    # 设置坐标轴范围
    all_points = np.array([p_t, p_f, p_b])
    x_range = [all_points[:, 0].min() - 5, all_points[:, 0].max() + 5]
    y_range = [all_points[:, 1].min() - 2, all_points[:, 1].max() + 2]
    z_range = [all_points[:, 2].min() - 100, all_points[:, 2].max() + 100]

    ax.set_xlim(x_range)
    ax.set_ylim(y_range)
    ax.set_zlim(z_range)

    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"3D 模型已保存到: {save_path}")

    return fig


def plot_distribution(
    mc_results: Dict, analytical_results: Dict, save_path: str = None
):
    """
    绘制 h 值分布直方图

    显示：
    - 蒙特卡洛模拟的 h 分布
    - 均值、标准差
    - 95% 置信区间
    - 解析解估计的标准差（对比）
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    h_samples = mc_results["h_samples"]
    h_mean = mc_results["h_mean"]
    h_std = mc_results["h_std"]
    h_95_ci = mc_results["h_95_ci"]

    # 直方图
    n, bins, patches = ax.hist(
        h_samples,
        bins=50,
        density=True,
        alpha=0.7,
        color="steelblue",
        edgecolor="black",
        label="蒙特卡洛采样",
    )

    # 拟合正态分布
    from scipy import stats

    x_fit = np.linspace(h_samples.min(), h_samples.max(), 200)
    y_fit = stats.norm.pdf(x_fit, h_mean, h_std)
    ax.plot(x_fit, y_fit, "r-", linewidth=2, label="正态拟合")

    # 标记均值
    ax.axvline(
        h_mean,
        color="darkred",
        linestyle="--",
        linewidth=2,
        label=f"均值 = {h_mean:.6f} cm",
    )

    # 标记 95% 置信区间
    ax.axvline(h_95_ci[0], color="orange", linestyle=":", linewidth=1.5, label="95% CI")
    ax.axvline(h_95_ci[1], color="orange", linestyle=":", linewidth=1.5)

    # 填充 95% 区间
    ax.fill_betweenx(
        [0, ax.get_ylim()[1]], h_95_ci[0], h_95_ci[1], color="orange", alpha=0.2
    )

    ax.set_xlabel("h (cm)", fontsize=11)
    ax.set_ylabel("概率密度", fontsize=11)
    ax.set_title("h 值分布（蒙特卡洛模拟）", fontsize=12, fontweight="bold")

    # 添加统计信息文本框
    textstr = "\n".join(
        [
            f"样本数: {len(h_samples)}",
            f"均值: {h_mean:.6f} cm",
            f"标准差 (MC): {h_std:.6e} cm",
            f"标准差 (MC): {h_std * 10000:.4f} μm",
            f"解析解 σ: {analytical_results['sigma_h'] * 10000:.4f} μm",
            f"95% CI: [{h_95_ci[0]:.6f}, {h_95_ci[1]:.6f}] cm",
        ]
    )
    props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
    ax.text(
        0.98,
        0.97,
        textstr,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=props,
    )

    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"分布图已保存到: {save_path}")

    return fig


def plot_sensitivity(sensitivity: Dict, variance_contrib: Dict, save_path: str = None):
    """
    绘制敏感性分析图

    显示：
    - 各参数的 Δh（绝对变化）
    - 各参数的方差贡献百分比
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    params = list(sensitivity.keys())
    delta_h = [sensitivity[p] * 10000 for p in params]  # 转换为 μm
    var_contrib = [variance_contrib[p] for p in params]

    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A"]

    # 子图 1: Δh 条形图
    bars1 = ax1.bar(params, delta_h, color=colors, edgecolor="black", linewidth=1.5)
    ax1.set_ylabel("|Δh| (μm)", fontsize=11)
    ax1.set_xlabel("参数", fontsize=11)
    ax1.set_title("单参数 ±1μm 扰动对 h 的影响", fontsize=12, fontweight="bold")
    ax1.grid(True, axis="y", alpha=0.3)

    # 在条形上添加数值标签
    for bar, val in zip(bars1, delta_h):
        height = bar.get_height()
        ax1.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{val:.4f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    # 子图 2: 方差贡献饼图
    ax2.pie(
        var_contrib,
        labels=params,
        autopct="%1.1f%%",
        colors=colors,
        startangle=90,
        textprops={"fontsize": 10},
    )
    ax2.set_title("方差贡献百分比", fontsize=12, fontweight="bold")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"敏感性图已保存到: {save_path}")

    return fig


def plot_all(
    analyzer: "PrecisionAnalyzer",
    x_t: float,
    y_t: float,
    z_t: float,
    y_f: float,
    z_f: float,
    y_b: float,
    z_b: float,
    output_dir: str = ".",
):
    """
    生成所有可视化图表

    Args:
        analyzer: 精度分析器实例
        x_t, y_t, z_t: P_t 坐标
        y_f, z_f: P_f 的 y, z 坐标
        y_b, z_b: P_b 的 y, z 坐标
        output_dir: 输出目录
    """
    import os

    # 运行分析
    print("运行误差传播分析...")
    analytical = analyzer.analytical_error_propagation(
        x_t, y_t, z_t, y_f, z_f, y_b, z_b
    )

    print("运行蒙特卡洛模拟...")
    mc_results = analyzer.monte_carlo_simulation(x_t, y_t, z_t, y_f, z_f, y_b, z_b)

    print("运行敏感性分析...")
    sensitivity = analyzer.sensitivity_analysis(x_t, y_t, z_t, y_f, z_f, y_b, z_b)

    # 生成图表
    print("\n生成可视化图表...")

    plot_3d_model(
        analyzer,
        x_t,
        y_t,
        z_t,
        y_f,
        z_f,
        y_b,
        z_b,
        save_path=os.path.join(output_dir, "3d_model.png"),
    )

    plot_distribution(
        mc_results, analytical, save_path=os.path.join(output_dir, "distribution.png")
    )

    plot_sensitivity(
        sensitivity,
        analytical["variance_contributions"],
        save_path=os.path.join(output_dir, "sensitivity.png"),
    )

    print("\n所有图表已生成！")
    plt.show()
