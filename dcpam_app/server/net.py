"""DCPAM 相机网络配置：找网卡、配 IP、清冲突、校验路由。

纯网络工具函数，供 cli.py（启动/`dcpam net`）与 routes/camera.py（重连）共用，
避免 routes 反向 import cli 的启动逻辑。仅 macOS 需要（Windows 走 Galaxy SDK，
不需要手动配 192.168.0.1）。
"""
from __future__ import annotations

import subprocess
import sys
from typing import Optional

# 相机接在 192.168.0.x 网段：主机网口配 .1，相机常见首地址 .2 用作路由/连通性探测目标。
CAMERA_HOST_IP = "192.168.0.1"
CAMERA_NETMASK = "255.255.255.0"
CAMERA_PROBE_IP = "192.168.0.2"


def describe(exc: BaseException) -> str:
    """把异常压成一行简短描述。"""
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _run_ifconfig() -> Optional[str]:
    """跑 `ifconfig` 返回全文；不可用返回 None。"""
    try:
        result = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout


def find_camera_interface() -> Optional[str]:
    """找一个活跃的千兆以太网接口用于配置相机 IP（仅 macOS）。"""
    if sys.platform != "darwin":
        return None
    text = _run_ifconfig()
    if text is None:
        return None

    current_iface: Optional[str] = None
    is_gigabit = False
    for line in text.splitlines():
        if not line.startswith("\t") and ":" in line:
            current_iface = line.split(":")[0]
            is_gigabit = False
        if current_iface and "1000baseT" in line:
            is_gigabit = True
        if current_iface and is_gigabit and "status: active" in line:
            return current_iface
    return None


def find_conflicting_interfaces(keep_iface: str) -> list[str]:
    """找出除 keep_iface 外所有配了 CAMERA_HOST_IP 的网卡。

    这些网卡会和相机网卡抢 192.168.0.0/24 的直连路由，导致去相机的包被路由到
    错误（常是未接线的）网卡而超时——必须在配 keep_iface 前清掉。
    """
    text = _run_ifconfig()
    if text is None:
        return []

    conflicts: list[str] = []
    current_iface: Optional[str] = None
    for line in text.splitlines():
        if not line.startswith("\t") and ":" in line:
            current_iface = line.split(":")[0]
        elif current_iface and current_iface != keep_iface:
            # ifconfig 地址行形如 "\tinet 192.168.0.1 netmask 0xffffff00 ..."
            if line.strip().startswith(f"inet {CAMERA_HOST_IP} "):
                if current_iface not in conflicts:
                    conflicts.append(current_iface)
    return conflicts


def clear_conflicting_ip(iface: str) -> bool:
    """免密（-n）摘掉某网卡上的 CAMERA_HOST_IP 别名地址。成功返回 True。

    用 -alias 只删这一个地址，不动网卡其它配置；依赖免密规则里放开的
    `ifconfig en* -alias 192.168.0.1`。
    """
    cmd = ["sudo", "-n", "ifconfig", iface, "-alias", CAMERA_HOST_IP]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def configure_camera_ip(iface: str) -> bool:
    """免密（-n）把网口配成相机 IP 并置 up。成功返回 True；未装免密规则返回 False。"""
    cmd = ["sudo", "-n", "ifconfig", iface, CAMERA_HOST_IP, "netmask", CAMERA_NETMASK, "up"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _route_interface(dest_ip: str) -> Optional[str]:
    """`route -n get <ip>` 解析出这条路由实际走的网卡名。"""
    try:
        result = subprocess.run(
            ["route", "-n", "get", dest_ip],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _ping_ok(dest_ip: str) -> bool:
    """ping 一下相机；通返回 True。相机可能不回 ICMP，故失败不代表连不上。"""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-t", "1", dest_ip],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def verify_camera_route(keep_iface: str) -> dict:
    """校验去相机的直连路由是否指向 keep_iface。

    返回 {ok, route_iface, ping_ok, message}：
      - 路由指向别的网卡 → ok=False（硬失败，正是 en3 抢路由那类问题）；
      - 路由指向 keep_iface 但 ping 不通 → ok=True（相机常不回 ICMP，仅告警）。
    """
    route_iface = _route_interface(CAMERA_PROBE_IP)
    ping_ok = _ping_ok(CAMERA_PROBE_IP)
    if route_iface is None:
        return {
            "ok": False, "route_iface": None, "ping_ok": ping_ok,
            "message": f"无法解析到 {CAMERA_PROBE_IP} 的路由",
        }
    if route_iface != keep_iface:
        return {
            "ok": False, "route_iface": route_iface, "ping_ok": ping_ok,
            "message": f"直连路由指向 {route_iface}，非相机网卡 {keep_iface}（有其它网卡抢占同网段）",
        }
    if not ping_ok:
        return {
            "ok": True, "route_iface": route_iface, "ping_ok": False,
            "message": f"路由 → {keep_iface} 正常，但相机未回 ICMP（可能正常）",
        }
    return {
        "ok": True, "route_iface": route_iface, "ping_ok": True,
        "message": f"路由 → {keep_iface} 正常，相机可达",
    }
