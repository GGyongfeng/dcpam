from __future__ import annotations

import os
import platform
import subprocess
import sys

from pydantic import BaseModel
from rich.console import Console

from dcpam.path import DCPAMPaths

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


def _check_camera_sdk() -> CheckResult:
    if sys.platform == "win32":
        return _check_gxipy()
    return _check_aravis()


def _check_gxipy() -> CheckResult:
    try:
        from dcpam.camera import _get_gxipy  # noqa: WPS433 局部导入避免循环
        _get_gxipy()
        return CheckResult(name="Galaxy SDK", passed=True, message="已加载 gxipy")
    except Exception as exc:
        return CheckResult(
            name="Galaxy SDK",
            passed=False,
            message=str(exc).splitlines()[0][:80],
            remedy=(
                "安装大恒 Galaxy SDK（含 Python 样例）到 D:/Camera_Galaxy/GalaxySDK 或\n"
                "C:/Program Files/Daheng Imaging/GalaxySDK，然后确认 numpy<2"
            ),
        )


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
    if iface:
        remedy = f"uv run dcpam net  # 自动配置 {iface}"
    else:
        remedy = "先连接相机网线后运行：uv run dcpam net"
    return CheckResult(
        name="交换机 IP",
        passed=False,
        message=f"未配置 {_HOST_IP}",
        remedy=remedy,
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


def _check_permission() -> CheckResult:
    """免密网卡配置规则是否装好（macOS）。没装则给出安装提示。"""
    from . import net

    if sys.platform != "darwin":
        return CheckResult(name="网卡免密权限", passed=True, message="非 macOS，无需配置")
    if net.sudoers_installed():
        return CheckResult(name="网卡免密权限", passed=True, message="已配置")
    return CheckResult(
        name="网卡免密权限",
        passed=False,
        message="未安装免密规则",
        remedy=(
            "执行一次（输一次密码），之后配网卡/重连免密：\n"
            "printf '%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* 192.168.0.1 "
            "netmask 255.255.255.0 up\\n%s ALL=(root) NOPASSWD: /sbin/ifconfig "
            "en[0-9]* -alias 192.168.0.1\\n' \"$(whoami)\" \"$(whoami)\" "
            "| sudo tee /etc/sudoers.d/dcpam-camera-net > /dev/null "
            "&& sudo chmod 440 /etc/sudoers.d/dcpam-camera-net "
            "&& sudo visudo -c -f /etc/sudoers.d/dcpam-camera-net"
        ),
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
    """运行启动自检：只查环境/权限/网卡/配置，不探测相机。

    相机连接留到运行时（前端切测量模式点 ⚡ 或调重连接口）再做，启动不阻塞、不探测。
    """
    results = [_check_os()]

    sdk = _check_camera_sdk()
    results.append(sdk)

    if sdk.passed:
        results.append(_check_permission())
        results.append(_check_network())
    else:
        sdk_name = "Galaxy SDK" if sys.platform == "win32" else "Aravis"
        results.append(CheckResult(name="网卡免密权限", passed=False, message="跳过", remedy=f"请先安装 {sdk_name}"))
        results.append(CheckResult(name="交换机 IP", passed=False, message="跳过", remedy=f"请先安装 {sdk_name}"))

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


def print_health_report(paths: DCPAMPaths) -> list[CheckResult]:
    """非交互式：打印 banner + 检查结果，返回结果列表供调用方判断。"""
    console = Console()
    _print_banner(console)
    results = run_checks(paths)
    _print_results(console, results)
    console.print()
    return results
