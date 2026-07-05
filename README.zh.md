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

运行 Web 界面（同时启动 FastAPI 后端 + Vite 前端）：

```bash
uv run dcpam
```

启动后浏览器打开 Vite 给出的地址（默认 http://127.0.0.1:5173/）。
顶部有 *分析 / 测量* 两个 tab：分析模式上传 TOML + CSV 复现历史样本；
测量模式上传 TOML 后接相机实时预览，按"拍照 + 测量"自动连拍 N 张取均值并写入 `data/measurements.jsonl`。

运行精度分析脚本：

```bash
uv run python scripts/run_analysis.py
```

采集工具已经并入 `uv run dcpam` 的测量模式，不再有独立入口。使用前请确认：

- 已连接两台相机，处于 `192.168.0.x` 同一子网
- Windows：安装大恒 Galaxy SDK（含 Python 样例目录，默认查找 `D:/Camera_Galaxy/GalaxySDK`）
- macOS：`brew install aravis pygobject3 libffi`

可选的调试脚本：

```bash
uv run python scripts/check_camera_env.py   # 自检 SDK / 相机可达性
uv run python scripts/capture_once.py       # 单次抓一对帧到 pictures/
```

## 仓库结构

- `dcpam/`：可复用的 CV 核心（config/pipeline/optical_geometry/pnp/steps/camera）
- `dcpam/camera.py`：双相机采集控制器（Windows→gxipy，其他→Aravis，接口统一）
- `dcpam_app/`：应用层（不依赖顺序：应用 → 核心，核心不反向依赖应用）
  - `dcpam_app/server/`：FastAPI 后端 + CLI（拍照、圆心提取、JSONL 落盘）
  - `dcpam_app/web/`：React + Three.js 前端
  - `dcpam_app/desktop/`：桌面程序（预留，将来 pywebview + PyInstaller 打包 exe）
- `scripts/`：可直接运行的脚本
- `exp/`：降方差优化实验记录
- `data/`：测量模式输出目录（imgs/ + measurements.jsonl，已加入 .gitignore）
- `pictures/`：`scripts/capture_once.py` 的采集图像保存目录
- `docs/`：项目说明与规范文档

## 许可证

当前仓库里还没有提供 `LICENSE` 文件。
