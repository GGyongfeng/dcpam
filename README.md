# DCPAM

English | [中文](README.zh.md)

DCPAM is a dual-camera point-to-axis measurement project built around a laser reference line.
The current repository mainly contains a classical computer vision workflow for geometry and precision analysis, plus a Daheng dual-camera capture utility.

## Features

- Compute the distance from a target point `P_t` to the axis defined by two measured points `P_f` and `P_b`
- Estimate measurement uncertainty with analytical error propagation
- Validate uncertainty with Monte Carlo simulation
- Visualize the 3D geometry, distance distribution, and sensitivity contribution
- Capture synchronized image pairs from two Daheng GigE Vision cameras

## Installation

Clone the repository and install the Python dependencies with `uv`:

```bash
git clone https://github.com/GGyongfeng/dcpam.git
cd dcpam
uv sync
```

### macOS 额外依赖

相机采集基于 [Aravis](https://github.com/AravisProject/aravis)（开源 GigE Vision 库），macOS 上需要：

```bash
brew install aravis pygobject3 libffi
PKG_CONFIG_PATH="/opt/homebrew/opt/libffi/lib/pkgconfig" uv pip install PyGObject
```

### 网络配置

GigE Vision 相机通过网口通信，需要确保 Mac 与相机在同一子网。
如果相机 IP 为 `192.168.0.x`，给连接相机的网口配置静态 IP：

```bash
# 查看哪个网口连接了相机（找 status: active 的以太网口）
ifconfig | grep -B5 "status: active"

# 配置静态 IP（将 en6 替换为你的实际网口）
sudo ifconfig en6 192.168.0.1 netmask 255.255.255.0 up
```

## Usage

### 相机拍照

单次拍照（拍一对后退出）：

```bash
uv run dcpam
```

交互模式（ENTER 拍照，Q 退出）：

```bash
uv run dcpam -i
```

图片保存到 `~/.dcpam/images/`，命名格式：`{YYYYMMDD_HHMMSS}_{front|rear}_{uid}.png`

### 精度分析

```bash
uv run python scripts/run_analysis.py
```

## Repository Layout

- `dcpam_cv/` — 核心模块（相机采集、配置管理、精度分析）
- `scripts/` — 可执行脚本
- `docs/` — 架构设计文档
- `papers/` — 论文

## License

No license file is included in the current repository yet.
