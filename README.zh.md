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

## 快速开始（macOS）

下面是从零把 Web 界面跑起来的完整流程。Windows 见文末[「Windows 说明」](#windows-说明)。

### 1. 克隆并安装依赖

```bash
git clone https://github.com/GGyongfeng/dcpam.git
cd dcpam
uv sync                          # Python 依赖
npm --prefix dcpam_app/web install   # 前端依赖（首次必装，否则前端起不来）
```

这一步装好运行 Web 界面（分析模式）所需的全部依赖。**只做分析、不接相机的话，到这就够了**，直接跳到第 4 步。

> 需要本机装有 [uv](https://docs.astral.sh/uv/) 和 [Node.js](https://nodejs.org/)（含 npm）。

### 2. 安装相机依赖（只有要拍照 / 实时预览才需要）

相机采集基于 [Aravis](https://github.com/AravisProject/aravis)（开源 GigE Vision 库）。
先装系统 C 库，再装 Python 绑定 PyGObject：

```bash
# ① 系统 C 库（brew）
brew install aravis pygobject3 libffi

# ② Python 绑定，装进项目 .venv（camera 是可选依赖组）
PKG_CONFIG_PATH="/opt/homebrew/opt/libffi/lib/pkgconfig" uv sync --extra camera
```

> 顺序不能反：PyGObject 编译时要链接 libffi，所以必须先 `brew` 装好系统库。
> `PKG_CONFIG_PATH` 是告诉编译器去哪找 libffi，缺了会编译失败。
>
> ⚠️ 装了相机依赖后，**后续同步一律带 `--extra camera`**（即 `uv sync --extra camera`）。
> 裸跑 `uv sync` 会把 PyGObject 当作"多余包"卸掉。

验证相机依赖装好了（能加载 Aravis）：

```bash
DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib" \
  uv run python -c "import gi; gi.require_version('Aravis','0.8'); from gi.repository import Aravis; print('Aravis OK')"
```

打印 `Aravis OK` 即成功。这里的 `DYLD_FALLBACK_LIBRARY_PATH` 是让 Python 找到 Aravis
动态库；`uv run dcpam` 启动时会自动设置它，正常使用无需手动加。

### 3. 配置相机网卡免密（只需一次）

GigE Vision 相机通过网口通信，Mac 要把连相机的网口配成 `192.168.0.1`。
这一步需要 `sudo`；为了避免每次连相机都输密码，装一条**一次性免密规则**——之后
启动 / 重连都自动配好、永不再输密码：

```bash
printf '%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* 192.168.0.1 netmask 255.255.255.0 up\n%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* -alias 192.168.0.1\n' "$(whoami)" "$(whoami)" \
  | sudo tee /etc/sudoers.d/dcpam-camera-net > /dev/null \
  && sudo chmod 440 /etc/sudoers.d/dcpam-camera-net \
  && sudo visudo -c -f /etc/sudoers.d/dcpam-camera-net
```

执行时输**一次**密码，看到 `parsed OK` 即成功。
该规则只放开两条命令：把 en 网口配成 `192.168.0.1`，以及摘掉这个地址
（`-alias`，用于自动清理同网段上抢路由的残留网卡）；其它 sudo 操作不受影响。
不想要了 `sudo rm /etc/sudoers.d/dcpam-camera-net` 即可移除。

> 不装这条规则也能用：`dcpam` 启动时会打印这条安装命令提醒你。

### 4. 启动 Web 界面

```bash
uv run dcpam
```

这会同时拉起 **FastAPI 后端**（`http://127.0.0.1:8011`）和 **Vite 前端**。
启动后浏览器打开前端地址（默认 `http://127.0.0.1:5173/`）。`Ctrl+C` 一起退出。

启动时会做健康检查（操作系统 / 相机 SDK / 网卡 / config.toml）。
**没接相机也能用分析模式**，测量模式（拍照 / 预览）才需要相机。

### 5. 拍照测量

1. 网线接好相机 ↔ Mac；
2. 前端切到**测量模式**；
3. 点 **⚡** 按钮 —— 自动配网卡（免密）+ 连相机，连上即可拍照；
4. 点「拍照 + 测量」连拍 N 张、取均值、自动写入历史。

以后日常使用就这么简单：**插网线 → 点闪电 → 拍照**，不用重启后端、不用输密码。

> 即便圆心提取失败，只要图拍到了，也会生成记录并显示在历史里，序号自动 +1。

## 运行时数据目录

运行时的配置与数据都在 `~/.dcpam/`（跨项目共享，不随代码仓库走）：

```
~/.dcpam/
├── config.toml          # 设备几何 / 标定配置
├── pnp.toml             # PnP 圆点约定
├── measurements/        # 每次采样一个子目录（图片 + sample.json）
├── config_backups/      # config.toml 的自动备份
└── captures/            # 单次抓帧调试图
```

项目仓库根目录只保留 `config.toml` / `pnp.toml` 的**模板**，供首次填写参考。

## 常用命令与开关

```bash
uv run dcpam                     # 启动前后端（后端默认热更新）
uv run dcpam net                 # 单独配相机网卡（免密）
uv run python scripts/run_analysis.py   # 精度分析脚本

DCPAM_NO_RELOAD=1 uv run dcpam   # 关闭后端热更新
DCPAM_HOST=0.0.0.0 DCPAM_PORT=9000 uv run dcpam   # 自定义后端地址/端口
```

- **热更新**：`uv run dcpam` 默认开启后端热更新，改 `.py` 自动重启；前端本就有 HMR。生产可用 `DCPAM_NO_RELOAD=1` 关闭。
- **全局安装**（可在任意目录用 `dcpam` 命令）：`uv tool install -e '.[camera]'`

可选调试脚本：

```bash
uv run python scripts/check_camera_env.py   # 自检 SDK / 相机可达性
uv run python scripts/capture_once.py       # 单次抓一对帧到 ~/.dcpam/pictures/
```

## Windows 说明

Windows 走大恒 Galaxy SDK，**无需** Aravis / sudo 网卡免密那套：

- 安装大恒 Galaxy SDK（含 Python 样例目录，默认查找 `D:/Camera_Galaxy/GalaxySDK`）
- `uv sync` 后即可 `uv run dcpam`
- 网卡配置通过系统网络设置手动设成 `192.168.0.x` 同一子网

## 仓库结构

- `dcpam/`：可复用的 CV 核心（config/pipeline/optical_geometry/pnp/steps/camera）
- `dcpam/camera.py`：双相机采集控制器（Windows→gxipy，其他→Aravis，接口统一）
- `dcpam_app/`：应用层（不依赖顺序：应用 → 核心，核心不反向依赖应用）
  - `dcpam_app/server/`：FastAPI 后端 + CLI（拍照、圆心提取、JSONL 落盘）
  - `dcpam_app/web/`：React + Three.js 前端
  - `dcpam_app/desktop/`：桌面程序（预留，将来 pywebview + PyInstaller 打包 exe）
- `scripts/`：可直接运行的脚本
- `exp/`：降方差优化实验记录
- `data/`：（已废弃）运行时数据现统一在 `~/.dcpam/`，不再放仓库内
- `pictures/`：（运行时目录 `~/.dcpam/pictures/`）`scripts/capture_once.py` 的采集图像保存目录
- `docs/`：项目说明与规范文档

## 许可证

当前仓库里还没有提供 `LICENSE` 文件。
