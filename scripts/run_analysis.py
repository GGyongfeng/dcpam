"""
完整精度分析脚本（带交互式参数输入）

运行方式：
    python run_analysis.py

或者直接在代码中修改参数并运行

如果要降低测量误差的影响：
1. 保持直线尽可能平行于主轴
2. 增加两个接收屏之间的距离（增加基线）
3. 减小 P_t 到直线的距离
4. 提高 yf, zf, yb, zb 的测量精度
"""

import numpy as np
import os

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from dcpam_cv.precision import PrecisionAnalyzer

console = Console()


def interactive_input():
    """交互式参数输入"""
    console.print(
        Panel.fit("[bold cyan]精度分析 - 参数设置[/bold cyan]", border_style="cyan")
    )

    console.print("\n[yellow]请输入参数（直接回车使用默认值）:[/yellow]\n")

    # 屏幕距离
    console.print("[bold green]--- 前后屏幕距离 ---[/bold green]")
    screen_distance = float(input("  前后屏幕距离 (cm) [默认 10.0]: ") or "10.0")

    # P_t 位置
    console.print("\n[bold green]--- P_t (目标点) 位置 ---[/bold green]")
    x_t = float(input("  x_t (cm) [默认 0.0]: ") or "0.0")
    y_t = float(input("  y_t (cm) [默认 0.0]: ") or "0.0")
    z_t = float(input("  z_t (cm) [范围: -100 到 -200, 默认 -150.0]: ") or "-150.0")

    # P_f 位置
    console.print(f"\n[bold green]--- P_f (前接收屏, x=+{screen_distance/2:.1f}cm) 位置 ---[/bold green]")
    y_f = float(input("  y_f (cm) [默认 0.5]: ") or "0.5")
    z_f = float(input("  z_f (cm) [默认 0.5]: ") or "0.5")

    # P_b 位置
    console.print(f"\n[bold green]--- P_b (后接收屏, x={-screen_distance/2:.1f}cm) 位置 ---[/bold green]")
    y_b = float(input("  y_b (cm) [默认 -0.5]: ") or "-0.5")
    z_b = float(input("  z_b (cm) [默认 -0.5]: ") or "-0.5")

    # 测量误差范围
    console.print("\n[bold green]--- 测量误差范围 ---[/bold green]")
    error_range_um = float(input("  测量误差范围 (μm) [默认 10.0]: ") or "10.0")

    # 蒙特卡洛采样次数
    console.print("\n[bold green]--- 蒙特卡洛模拟参数 ---[/bold green]")
    n_samples = int(input("  采样次数 [默认 10000]: ") or "10000")

    # 是否生成图表
    console.print("\n[bold green]--- 可视化选项 ---[/bold green]")
    generate_plots_input = (
        input("  是否生成可视化图表? (y/N) [默认 N]: ").strip().lower()
    )
    generate_plots = generate_plots_input in ["y", "yes", "是"]

    return {
        "screen_distance": screen_distance,
        "x_t": x_t,
        "y_t": y_t,
        "z_t": z_t,
        "y_f": y_f,
        "z_f": z_f,
        "y_b": y_b,
        "z_b": z_b,
        "error_range_um": error_range_um,
        "n_samples": n_samples,
        "generate_plots": generate_plots,
    }


def run_analysis_with_params(params: dict, generate_plots: bool = None):
    """
    使用给定参数运行完整分析

    Args:
        params: 参数字典
        generate_plots: 是否生成可视化图表
    """
    screen_distance = params.get("screen_distance", 10.0)
    analyzer = PrecisionAnalyzer(screen_distance=screen_distance)

    x_t = params["x_t"]
    y_t = params["y_t"]
    z_t = params["z_t"]
    y_f = params["y_f"]
    z_f = params["z_f"]
    y_b = params["y_b"]
    z_b = params["z_b"]
    error_range_um = params.get("error_range_um", 1.0)
    n_samples = params.get("n_samples", 10000)

    # 如果 generate_plots 参数没有在函数调用时指定，从 params 读取，默认为 False
    if generate_plots is None:
        generate_plots = params.get("generate_plots", False)

    # 设置测量误差范围
    analyzer.error_range = error_range_um / 10000  # 转换 μm 为 cm

    # 输入参数表格
    params_table = Table(
        title="[bold]输入参数[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    params_table.add_column("参数", style="cyan", justify="left")
    params_table.add_column("数值", style="green", justify="right")
    params_table.add_column("说明", style="yellow", justify="left")

    params_table.add_row("屏幕距离", f"{screen_distance:.2f} cm", "前后屏幕之间的距离")
    params_table.add_row("P_t", f"({x_t:.2f}, {y_t:.2f}, {z_t:.2f}) cm", "目标点位置")
    params_table.add_row(
        "P_f", f"({analyzer.X_F:.2f}, {y_f:.2f}, {z_f:.2f}) cm", "前接收屏位置"
    )
    params_table.add_row(
        "P_b", f"({analyzer.X_B:.2f}, {y_b:.2f}, {z_b:.2f}) cm", "后接收屏位置"
    )
    params_table.add_row(
        "测量误差", f"±{analyzer.error_range * 10000:.1f} μm", "测量设备的精度"
    )

    # 计算 P_f 和 P_b 连线与 x 轴的夹角
    dx = analyzer.X_F - analyzer.X_B
    dy = y_f - y_b
    dz = z_f - z_b
    line_length = np.sqrt(dx**2 + dy**2 + dz**2)

    if line_length > 0:
        cos_angle = dx / line_length
        angle_rad = np.arccos(np.clip(cos_angle, -1, 1))
        angle_deg = np.degrees(angle_rad)
        params_table.add_row("直线夹角", f"{angle_deg:.4f}°", "P_f-P_b连线与x轴夹角")
    else:
        params_table.add_row("直线夹角", "未定义", "P_f和P_b重合")

    console.print(params_table, justify="center")

    # 1. 解析法
    console.print("\n")

    analytical = analyzer.analytical_error_propagation(
        x_t, y_t, z_t, y_f, z_f, y_b, z_b
    )

    # 主要结果
    result_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    result_table.add_column("指标", style="cyan bold", width=15)
    result_table.add_column("数值", style="green", width=45)

    result_table.add_row(
        "名义 h 值",
        f"{analytical['h_nominal']:.6f} cm = {analytical['h_nominal'] * 10:.4f} mm",
    )
    result_table.add_row(
        "估算 σ_h",
        f"{analytical['sigma_h']:.6e} cm = {analytical['sigma_h'] * 10000:.6f} μm",
    )

    # 偏导数和方差贡献整合到一个表格
    analysis_table = Table(
        box=box.SIMPLE, show_header=True, header_style="bold cyan", padding=(0, 2)
    )
    analysis_table.add_column("参数", style="cyan", justify="center", width=8)
    analysis_table.add_column("偏导数", style="green", justify="right", width=15)
    analysis_table.add_column(
        "方差贡献", style="yellow bold", justify="right", width=12
    )
    analysis_table.add_column("重要性", style="magenta", justify="center", width=10)

    sorted_params = sorted(
        analytical["variance_contributions"].items(), key=lambda x: x[1], reverse=True
    )

    for key, contrib in sorted_params:
        deriv_key = f"dh_d{key}"
        deriv_val = analytical["derivatives"].get(deriv_key, 0)

        if contrib > 50:
            importance = "🔴 极高"
        elif contrib > 20:
            importance = "🟡 高"
        elif contrib > 5:
            importance = "🟢 中"
        else:
            importance = "⚪ 低"

        analysis_table.add_row(key, f"{deriv_val:.3e}", f"{contrib:.2f}%", importance)

    # 使用 Group 组合多个元素
    separator_text = Text(
        "\n各参数对误差的影响（偏导数越大、方差贡献越高，影响越大）", style="dim"
    )

    panel_content = Group(
        result_table,
        Text(""),  # 空行
        separator_text,
        analysis_table,
    )

    console.print(
        Panel(
            panel_content,
            title="[bold yellow]1. 误差传播解析解[/bold yellow]",
            subtitle="[dim]通过数学公式计算误差传播[/dim]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    # 2. 蒙特卡洛
    console.print("\n")

    mc_results = analyzer.monte_carlo_simulation(
        x_t, y_t, z_t, y_f, z_f, y_b, z_b, n_samples=n_samples
    )

    mc_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    mc_table.add_column("统计量", style="cyan bold", width=18)
    mc_table.add_column("数值", style="green", width=50)

    mc_table.add_row(
        "h 均值", f"{mc_results['h_mean']:.6f} cm = {mc_results['h_mean'] * 10:.4f} mm"
    )
    mc_table.add_row(
        "h 标准差 (σ)",
        f"{mc_results['h_std']:.6e} cm = {mc_results['h_std'] * 10000:.6f} μm",
    )
    mc_table.add_row("h 中位数", f"{mc_results['h_median']:.6f} cm")
    mc_table.add_row(
        "95% 置信区间",
        f"[{mc_results['h_95_ci'][0]:.6f}, {mc_results['h_95_ci'][1]:.6f}] cm",
    )
    mc_table.add_row(
        "h 范围", f"[{mc_results['h_min']:.6f}, {mc_results['h_max']:.6f}] cm"
    )
    mc_table.add_row(
        "相对精度", f"{mc_results['h_std'] / mc_results['h_mean'] * 100:.6f}%"
    )

    console.print(
        Panel(
            mc_table,
            title=f"[bold yellow]2. 蒙特卡洛模拟 ({n_samples:,} 次采样)[/bold yellow]",
            subtitle="[dim]通过随机采样模拟实际测量误差分布[/dim]",
            border_style="yellow",
            padding=(1, 1),
        )
    )

    # 3. 敏感性分析
    console.print("\n")

    sensitivity = analyzer.sensitivity_analysis(x_t, y_t, z_t, y_f, z_f, y_b, z_b)
    sorted_sens = sorted(sensitivity.items(), key=lambda x: x[1], reverse=True)

    sens_table = Table(
        box=box.SIMPLE, show_header=True, header_style="bold cyan", padding=(0, 2)
    )
    sens_table.add_column("参数", style="cyan", justify="center", width=8)
    sens_table.add_column("|Δh| (μm)", style="green bold", justify="right", width=15)
    sens_table.add_column("敏感度", style="magenta", justify="center", width=10)

    for key, val in sorted_sens:
        val_um = val * 10000
        if val_um > 20:
            sensitivity_level = "🔴 极高"
        elif val_um > 10:
            sensitivity_level = "🟡 高"
        elif val_um > 1:
            sensitivity_level = "🟢 中"
        else:
            sensitivity_level = "⚪ 低"
        sens_table.add_row(key, f"{val_um:.4f}", sensitivity_level)

    console.print(
        Panel(
            sens_table,
            title="[bold yellow]3. 敏感性分析 (单参数 ±1μm 扰动)[/bold yellow]",
            subtitle="[dim]每个参数变化1μm时，对h值的影响[/dim]",
            border_style="yellow",
            padding=(1, 1),
        )
    )

    # 4. 结论
    console.print("\n")

    conclusion_table = Table(
        box=box.SIMPLE, show_header=True, header_style="bold cyan", padding=(0, 2)
    )
    conclusion_table.add_column("分析方法", style="cyan", width=18)
    conclusion_table.add_column(
        "h 不确定度", style="green bold", justify="right", width=18
    )

    conclusion_table.add_row("解析估计", f"±{analytical['sigma_h'] * 10000:.4f} μm")
    conclusion_table.add_row("蒙特卡洛 (1σ)", f"±{mc_results['h_std'] * 10000:.4f} μm")

    # 计算 95% 置信区间相对于均值的偏差（取上下界中较大的偏差）
    ci_lower_dev = abs(mc_results["h_mean"] - mc_results["h_95_ci"][0]) * 10000
    ci_upper_dev = abs(mc_results["h_95_ci"][1] - mc_results["h_mean"]) * 10000
    ci_deviation = max(ci_lower_dev, ci_upper_dev)

    conclusion_table.add_row(
        "95% 置信区间",
        f"±{ci_deviation:.4f} μm",
    )

    most_sensitive = sorted_sens[0]

    # 构建文本内容
    text_content = Text()
    text_content.append("🎯 最敏感参数: ", style="bold red")
    text_content.append(f"{most_sensitive[0]}", style="bold green")
    text_content.append(" (变化1μm → h变化 ", style="")
    text_content.append(f"{most_sensitive[1] * 10000:.4f} μm", style="yellow")
    # 使用 Group 组合表格和文本
    conclusion_group = Group(conclusion_table, text_content)

    console.print(
        Panel(
            conclusion_group,
            title="[bold yellow]4. 总结与结论[/bold yellow]",
            subtitle="[dim]综合分析结果的关键发现[/dim]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    console.print("\n" + "=" * 80)

    # 生成可视化
    if generate_plots:
        console.print("\n[bold cyan]📊 正在生成可视化图表...[/bold cyan]")

        # 创建结果目录
        results_dir = "results"
        os.makedirs(results_dir, exist_ok=True)

        from dcpam_cv.precision import (
            plot_3d_model,
            plot_distribution,
            plot_sensitivity,
        )

        # 生成图表
        plot_3d_model(
            analyzer,
            x_t,
            y_t,
            z_t,
            y_f,
            z_f,
            y_b,
            z_b,
            save_path=os.path.join(results_dir, "3d_model.png"),
        )

        plot_distribution(
            mc_results,
            analytical,
            save_path=os.path.join(results_dir, "distribution.png"),
        )

        plot_sensitivity(
            sensitivity,
            analytical["variance_contributions"],
            save_path=os.path.join(results_dir, "sensitivity.png"),
        )

        console.print(
            f"\n[bold green]✓ 图表已保存到目录:[/bold green] [cyan]{results_dir}/[/cyan]"
        )
        console.print("  [yellow]•[/yellow] 3d_model.png: 三维空间模型")
        console.print("  [yellow]•[/yellow] distribution.png: h 值分布图")
        console.print("  [yellow]•[/yellow] sensitivity.png: 敏感性分析图")

        # 显示图表
        import matplotlib.pyplot as plt

        plt.show()

    return analytical, mc_results, sensitivity


def main():
    """主函数"""
    console.print("\n")
    console.print(
        Panel.fit(
            "[bold magenta]欢迎使用精度分析工具！[/bold magenta]\n"
            "[dim]DCPAM - Dynamic Coordinate Precision Analysis Module[/dim]",
            border_style="magenta",
        )
    )
    console.print("\n")

    # 选择输入模式
    mode = input("选择模式 [1: 交互式输入, 2: 使用默认参数]: ").strip()

    if mode == "1":
        params = interactive_input()
    else:
        # 默认参数
        params = {
            "screen_distance": 10.0,
            "x_t": 0.0,
            "y_t": 0.0,
            "z_t": -150.0,
            "y_f": 0.5,
            "z_f": 0.5,
            "y_b": -0.5,
            "z_b": -0.5,
            "error_range_um": 10.0,
            "n_samples": 10000,
            "generate_plots": False,
        }
        console.print("\n[yellow]使用默认参数进行分析...[/yellow]")

    # 运行分析
    run_analysis_with_params(params)


if __name__ == "__main__":
    main()
