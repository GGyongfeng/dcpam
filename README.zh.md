# DCPAM

[English](README.md) | 中文

DCPAM 是一个围绕激光基准线构建的双相机点到轴线测量项目。
当前仓库主要包含基于传统计算机视觉的几何建模与精度分析流程，以及一个用于大恒双相机采集的脚本工具。

## 功能

- 计算目标点 `P_t` 到由 `P_f` 与 `P_b` 两点定义的轴线距离
- 使用解析误差传播估计测量不确定度
- 使用蒙特卡洛模拟验证误差分布
- 可视化三维几何关系、距离分布和敏感性贡献
- 通过两台大恒相机采集成对图像，用于数据获取

## 当前状态

当前仓库里已经具备可运行的 `CV` 精度分析流程。
之前的 README 提到过 `MLP` 和 `CNN` 版本，但它们在当前代码树中还没有对应实现。

## 安装

先克隆仓库，再用 `uv` 安装 Python 依赖：

```bash
git clone https://github.com/GGyongfeng/dcpam.git
cd dcpam
uv sync
```

如果要运行双相机采集脚本，还需要额外安装大恒 Galaxy SDK 及其 `gxipy` Python 绑定。
这部分不是 `uv sync` 自动安装的内容，而是硬件厂商提供的运行环境。

## 使用

运行精度分析脚本：

```bash
uv run python scripts/run_analysis.py
```

运行大恒双相机采集工具：

```bash
uv run python dual_daheng_capture.py
```

使用采集工具前，请确认：

- 已连接两台大恒相机
- 已安装 Daheng Galaxy SDK
- 运行环境可以正确导入 `gxipy`

## 仓库结构

- `dcpam_cv/`：可复用的 CV 与精度分析代码
- `scripts/`：可直接运行的脚本
- `pictures/`：采集图片保存目录
- `docs/`：项目说明与规范文档
- `dual_daheng_capture.py`：实时预览与双相机成对采集入口

## 许可证

当前仓库里还没有提供 `LICENSE` 文件。
