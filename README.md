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

## Quick start (macOS)

Complete flow to get the web UI running from scratch. For Windows see [Windows notes](#windows-notes).

### 1. Clone and install dependencies

```bash
git clone https://github.com/GGyongfeng/dcpam.git
cd dcpam
uv sync                          # Python dependencies
npm --prefix dcpam_app/web install   # frontend dependencies (required first run)
```

This installs everything needed for the web UI (analysis mode). **If you only need
analysis without a camera, stop here** and skip to step 4.

> Requires [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) (with npm) installed.

### 2. Install camera dependencies (only for capture / live preview)

Camera capture is built on [Aravis](https://github.com/AravisProject/aravis) (open-source
GigE Vision library). Install the system C libraries first, then the Python binding:

```bash
# 1) system C libraries (brew)
brew install aravis pygobject3 libffi

# 2) Python binding into the project .venv (camera is an optional extra)
PKG_CONFIG_PATH="/opt/homebrew/opt/libffi/lib/pkgconfig" uv sync --extra camera
```

> Order matters: PyGObject links against libffi at build time, so brew must run first.
> `PKG_CONFIG_PATH` tells the compiler where libffi lives; omitting it fails the build.
>
> ⚠️ After installing camera deps, **always sync with `--extra camera`** (`uv sync --extra camera`).
> A bare `uv sync` removes PyGObject as an "unused" package.

Verify the camera deps loaded (Aravis importable):

```bash
DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib" \
  uv run python -c "import gi; gi.require_version('Aravis','0.8'); from gi.repository import Aravis; print('Aravis OK')"
```

Printing `Aravis OK` means success. `DYLD_FALLBACK_LIBRARY_PATH` lets Python find the Aravis
shared library; `uv run dcpam` sets it automatically, so normal use needs no manual export.

### 3. Configure passwordless camera-NIC setup (one time)

GigE Vision cameras talk over Ethernet, so macOS must set the camera-facing NIC to
`192.168.0.1`. That needs `sudo`. To avoid typing a password every reconnect, install a
**one-time NOPASSWD rule** — afterwards startup / reconnect configure the NIC automatically:

```bash
printf '%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* 192.168.0.1 netmask 255.255.255.0 up\n%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* -alias 192.168.0.1\n' "$(whoami)" "$(whoami)" \
  | sudo tee /etc/sudoers.d/dcpam-camera-net > /dev/null \
  && sudo chmod 440 /etc/sudoers.d/dcpam-camera-net \
  && sudo visudo -c -f /etc/sudoers.d/dcpam-camera-net
```

Enter your password once; `parsed OK` means success. The rule permits only two commands:
configure `en*` to `192.168.0.1`, and remove that address (`-alias`, used to auto-clear a
stale NIC on the same subnet that would otherwise steal the route). All other sudo is
unaffected. Remove it with `sudo rm /etc/sudoers.d/dcpam-camera-net`.

> Skipping this rule still works — `dcpam` prints this install command as a reminder on startup.

### 4. Start the web UI

```bash
uv run dcpam
```

This launches both the **FastAPI backend** (`http://127.0.0.1:8011`) and the **Vite
frontend**. Open the frontend URL (default `http://127.0.0.1:5173/`). `Ctrl+C` stops both.

On startup it runs health checks (OS / camera SDK / NIC / config.toml). **Analysis mode
works without a camera**; measurement mode (capture / preview) needs one.

### 5. Capture and measure

1. Connect the network cable (camera ↔ Mac);
2. Switch to **measurement mode** in the frontend;
3. Click **⚡** — it auto-configures the NIC (passwordless) and connects the camera;
4. Click "capture + measure" to burst N frames, average, and write to history.

Day-to-day it is just: **plug cable → click the bolt → capture** — no backend restart, no password.

> Even if spot extraction fails, as long as images were captured a record is still written
> and shown in history, and the index auto-increments.

## Runtime data directory

Runtime config and data live directly at the repo root:

```
<repo root>/
├── camera.toml         # camera hardware params (AE/AG/exposure/gain)
├── config.toml         # device geometry / calibration
├── pnp.toml            # PnP circle conventions
├── measurements/       # one subdir per capture (images + sample.json)
├── config_backups/     # automatic backups of config.toml
├── captures/           # single-shot debug frames
└── pictures/           # scripts/capture_once.py debug captures
```

The three `*.toml` files ship as placeholder templates — fill in real calibration values before first use.

## Common commands and switches

```bash
uv run dcpam                     # start backend + frontend (backend hot-reload on by default)
uv run dcpam net                 # configure the camera NIC only (passwordless)
uv run python scripts/run_analysis.py   # precision analysis script

DCPAM_NO_RELOAD=1 uv run dcpam   # disable backend hot-reload
DCPAM_HOST=0.0.0.0 DCPAM_PORT=9000 uv run dcpam   # custom backend host/port
```

- **Hot-reload**: `uv run dcpam` enables backend hot-reload by default (editing `.py`
  auto-restarts); the frontend already has HMR. Disable with `DCPAM_NO_RELOAD=1`.
- **Global install** (use `dcpam` from any directory): `uv tool install -e '.[camera]'`

Optional debug scripts:

```bash
uv run python scripts/check_camera_env.py   # self-check SDK / camera reachability
uv run python scripts/capture_once.py       # grab one frame pair to <repo>/pictures/
```

## Windows notes

Windows uses the Daheng Galaxy SDK and does **not** need Aravis / sudo NIC setup:

- Install the Daheng Galaxy SDK (with its Python samples; looked up at `D:/Camera_Galaxy/GalaxySDK`)
- After `uv sync`, run `uv run dcpam`
- Set the NIC to the `192.168.0.x` subnet via Windows network settings

## Repository Layout

- `dcpam/` — 核心模块（相机采集、配置管理、CV pipeline）
- `dcpam_app/` — 应用层（server 后端 + CLI、web 前端、desktop 预留）
- `scripts/` — 可执行脚本
- `exp/` — 降方差优化实验
- `docs/` — 架构设计文档
- `papers/` — 论文

## License

No license file is included in the current repository yet.
