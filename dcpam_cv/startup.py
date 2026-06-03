from __future__ import annotations

import os
import platform
import subprocess
import sys

from pydantic import BaseModel
from rich.console import Console

from .path import DCPAMPaths

BANNER = r"""
     ____  ______  ____  ___    __  ___
    / __ \/ ____/ / __ \/   |  /  |/  /
   / / / / /     / /_/ / /| | / /|_/ /
  / /_/ / /___  / ____/ ___ |/ /  / /
 /_____/\____/ /_/   /_/  |_/_/  /_/
"""

_CAMERA_SUBNET = "192.168.0"
_HOST_IP = f"{_CAMERA_SUBNET}.1"


class CheckResult(BaseModel):
    """单项检测结果。"""
    name: str
    passed: bool
    message: str
    remedy: str = ""


def _check_os() -> CheckResult:
    info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    return CheckResult(name="操作系统", passed=True, message=info)


def _check_aravis() -> CheckResult:
    try:
        stderr_fd = sys.stderr.fileno()
        devnull = os.open(os.devnull, os.O_WRONLY)
        saved = os.dup(stderr_fd)
        os.dup2(devnull, stderr_fd)
        try:
            import gi
            gi.require_version("Aravis", "0.8")
            from gi.repository import Aravis
            return CheckResult(name="Aravis 库", passed=True, message="已安装")
        finally:
            os.dup2(saved, stderr_fd)
            os.close(saved)
            os.close(devnull)
    except Exception:
        return CheckResult(
            name="Aravis 库",
            passed=False,
            message="未安装或无法加载",
            remedy=(
                "brew install aravis pygobject3 libffi\n"
                'PKG_CONFIG_PATH="/opt/homebrew/opt/libffi/lib/pkgconfig" '
                "uv pip install 'dcpam[camera]'"
            ),
        )


def _check_network() -> CheckResult:
    if sys.platform != "darwin":
        return CheckResult(name="交换机 IP", passed=True, message=_HOST_IP)
    result = subprocess.run(["ifconfig"], capture_output=True, text=True)
    if _HOST_IP in result.stdout:
        return CheckResult(name="交换机 IP", passed=True, message=_HOST_IP)

    iface = _find_ethernet_iface(result.stdout)
    iface_hint = iface or "enX"
    return CheckResult(
        name="交换机 IP",
        passed=False,
        message=f"未配置 {_HOST_IP}",
        remedy=f"sudo ifconfig {iface_hint} {_HOST_IP} netmask 255.255.255.0 up",
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


def _check_cameras() -> CheckResult:
    try:
        import gi
        gi.require_version("Aravis", "0.8")
        from gi.repository import Aravis
        Aravis.update_device_list()
        n = Aravis.get_n_devices()
        if n >= 2:
            ids = [Aravis.get_device_id(i) for i in range(n)]
            return CheckResult(name="双相机", passed=True, message=f"{n} 台在线: {', '.join(ids)}")
        return CheckResult(
            name="双相机",
            passed=False,
            message=f"仅检测到 {n} 台",
            remedy="检查相机电源、网线、交换机连接",
        )
    except Exception:
        return CheckResult(
            name="双相机",
            passed=False,
            message="无法检测 (Aravis 未就绪)",
            remedy="请先安装 Aravis",
        )


def _check_file(name: str, path) -> CheckResult:
    if path.exists():
        return CheckResult(name=name, passed=True, message=str(path))
    return CheckResult(
        name=name,
        passed=False,
        message="缺失",
        remedy=f"创建配置文件: {path}",
    )


def run_checks(paths: DCPAMPaths) -> list[CheckResult]:
    """运行全部启动检测。"""
    results = [_check_os()]

    aravis = _check_aravis()
    results.append(aravis)

    if aravis.passed:
        results.append(_check_network())
        results.append(_check_cameras())
    else:
        results.append(CheckResult(name="交换机 IP", passed=False, message="跳过", remedy="请先安装 Aravis"))
        results.append(CheckResult(name="双相机", passed=False, message="跳过", remedy="请先安装 Aravis"))

    results.append(_check_file("config.toml", paths.config_file))

    return results


def _print_banner(console: Console) -> None:
    console.print(BANNER, style="bold cyan", highlight=False)


def _print_results(console: Console, results: list[CheckResult]) -> None:
    for r in results:
        mark = "[bold green] ✓ [/]" if r.passed else "[bold red] ✗ [/]"
        console.print(f"  {mark} {r.name:<16} {r.message}")
        if not r.passed and r.remedy:
            for line in r.remedy.splitlines():
                console.print(f"                       [dim]→ {line}[/]")


def startup(paths: DCPAMPaths) -> None:
    """Banner + 健康检查循环，全部通过后返回。"""
    console = Console()
    _print_banner(console)

    while True:
        results = run_checks(paths)
        _print_results(console, results)
        console.print()

        if all(r.passed for r in results):
            console.print("  [bold green]Ready![/]\n")
            return

        console.print("  [yellow]请修复以上问题，按 Enter 重试 / Q 退出[/]")
        user_input = input("  > ").strip().lower()
        if user_input == "q":
            raise SystemExit(0)
        console.print()
