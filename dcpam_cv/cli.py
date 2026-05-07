from __future__ import annotations

import argparse
import os
import subprocess
import sys

from .path import DCPAMPaths

_CAMERA_SUBNET = "192.168.0"
_HOST_IP = f"{_CAMERA_SUBNET}.1"
_NETMASK = "255.255.255.0"


def _ensure_aravis_libs() -> None:
    """macOS: 确保 Aravis 动态库可被加载，必要时重启进程。"""
    if sys.platform != "darwin":
        return
    brew_lib = "/opt/homebrew/lib"
    key = "DYLD_FALLBACK_LIBRARY_PATH"
    current = os.environ.get(key, "")
    if brew_lib not in current:
        os.environ[key] = brew_lib + (":" + current if current else "")
        os.execv(sys.argv[0], sys.argv)


def _ensure_camera_network() -> None:
    """检测并配置相机子网，需要 sudo 权限。"""
    if sys.platform != "darwin":
        return
    result = subprocess.run(["ifconfig"], capture_output=True, text=True)
    if _HOST_IP in result.stdout:
        return

    iface = _find_ethernet_iface(result.stdout)
    if iface is None:
        print(f"  [WARN] 未找到活跃的以太网口，跳过网络配置")
        return

    print(f"  配置 {iface} → {_HOST_IP} (需要 sudo 权限)")
    subprocess.run(
        ["sudo", "ifconfig", iface, _HOST_IP, "netmask", _NETMASK, "up"],
        check=True,
    )


def _find_ethernet_iface(ifconfig_output: str) -> str | None:
    """从 ifconfig 输出中找到活跃的千兆以太网口。"""
    current_iface = None
    is_gigabit = False
    for line in ifconfig_output.splitlines():
        if not line.startswith("\t") and ":" in line:
            current_iface = line.split(":")[0]
            is_gigabit = False
        if current_iface and "1000baseT" in line:
            is_gigabit = True
        if current_iface and is_gigabit and "status: active" in line:
            return current_iface
    return None


def _capture_once(camera) -> None:
    """单次拍照并保存。"""
    pair = camera.capture()
    camera.save(pair)

    ts = pair.timestamp.strftime("%H:%M:%S")
    print(f"  [{ts}] Captured pair (uid: {pair.uid})")
    print(f"  Saved: {pair.front_path}")
    print(f"  Saved: {pair.rear_path}")


def _interactive(camera) -> None:
    """交互模式：ENTER 拍照，Q 退出。"""
    print("  Ready. Press ENTER to capture, Q to quit.\n")

    while True:
        user_input = input("> ").strip().lower()
        if user_input == "q":
            break
        if user_input != "":
            continue
        _capture_once(camera)
        print()


def main() -> None:
    """dcpam CLI 入口。"""
    _ensure_aravis_libs()
    _ensure_camera_network()

    from .camera import DualCamera

    parser = argparse.ArgumentParser(description="DCPAM — Dual-Camera Point-to-Axis Measurement")
    parser.add_argument("-o", "--once", action="store_true", help="单次拍照后退出")
    args = parser.parse_args()

    paths = DCPAMPaths()
    paths.ensure_dirs()

    print("\n  DCPAM — Dual-Camera Point-to-Axis Measurement")
    print(f"  Config: {paths.root}/\n")

    with DualCamera(paths=paths) as camera:
        if args.once:
            _capture_once(camera)
        else:
            _interactive(camera)

    print("  Cameras closed. Bye.")
