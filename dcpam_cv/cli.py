from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .path import DCPAMPaths
from .pipeline import console
from .startup import print_health_report

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8011


def _force_utf8_console() -> None:
    """Windows 默认 cmd 是 GBK，rich 输出 ✓/✗ 会崩。强制切 UTF-8。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


def _start_backend(host: str, port: int) -> threading.Thread:
    """在后台线程跑 uvicorn。"""
    from .server import run as run_server

    thread = threading.Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        name="dcpam-server",
        daemon=True,
    )
    thread.start()
    return thread


def _start_frontend() -> subprocess.Popen:
    """启动 vite dev server。失败抛出 RuntimeError。"""
    web_dir = Path(__file__).resolve().parent / "web"
    if not (web_dir / "node_modules").exists():
        raise RuntimeError(
            f"前端依赖未安装：请先 cd {web_dir} && npm install"
        )

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise RuntimeError("找不到 npm，请安装 Node.js")

    if sys.platform == "win32":
        # 独立进程组，方便 CTRL_BREAK 关掉 vite + esbuild 子孙
        return subprocess.Popen(
            [npm, "run", "dev"],
            cwd=web_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=web_dir,
        start_new_session=True,
    )


def _terminate_process_group(proc: subprocess.Popen, timeout: float = 8.0) -> None:
    """向整个进程组发信号，防止 vite/esbuild 孤儿化。"""
    if sys.platform == "win32":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.terminate()
        except OSError:
            return
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.kill()
        except OSError:
            pass
        return

    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


_CAMERA_HOST_IP = "192.168.0.1"
_CAMERA_NETMASK = "255.255.255.0"


def _find_camera_interface() -> str | None:
    """macOS: 找一个活跃的千兆以太网接口用于配置 192.168.0.1。"""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None

    current_iface: str | None = None
    is_gigabit = False
    for line in result.stdout.splitlines():
        if not line.startswith("\t") and ":" in line:
            current_iface = line.split(":")[0]
            is_gigabit = False
        if current_iface and "1000baseT" in line:
            is_gigabit = True
        if current_iface and is_gigabit and "status: active" in line:
            return current_iface
    return None


def _run_net_command() -> int:
    """`uv run dcpam net`：探测千兆以太网口，用 sudo 配 192.168.0.1。"""
    if sys.platform != "darwin":
        console.print("  [yellow]目前只在 macOS 支持自动配置网卡；请手动配置 192.168.0.1[/]")
        return 1

    iface = _find_camera_interface()
    if not iface:
        console.print(
            "  [bold red]✗[/] 未检测到活跃的千兆以太网口。请先连接相机网线，或手动指定接口："
        )
        console.print(f"      sudo ifconfig <interface> {_CAMERA_HOST_IP} netmask {_CAMERA_NETMASK} up")
        return 1

    cmd = ["sudo", "ifconfig", iface, _CAMERA_HOST_IP, "netmask", _CAMERA_NETMASK, "up"]
    console.print(f"  [green]•[/] 检测到千兆接口：[bold]{iface}[/]")
    console.print(f"  [dim]执行：{' '.join(cmd)}[/]")
    console.print("  [dim]（需要输入 sudo 密码）[/]")
    try:
        result = subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        console.print("\n  [yellow]已取消[/]")
        return 1
    if result.returncode == 0:
        console.print(f"  [bold green]✓[/] 已配置 {iface} = {_CAMERA_HOST_IP}")
    else:
        console.print(f"  [bold red]✗[/] 配置失败（退出码 {result.returncode}）")
    return result.returncode


def _startup_configure_net() -> None:
    """启动时先尝试 sudo 配 IP。目的双重：
    1) 让 IP 一定处于正确状态（不管之前有没有配过）
    2) 让 sudo 密码缓存到当前 shell，后续重连时可无密码重配

    用户不输密码 / Ctrl+C 时不阻塞，正常启动 web。
    """
    if sys.platform != "darwin":
        return

    iface = _find_camera_interface()
    if not iface:
        console.print(
            "  [yellow]•[/] 未检测到千兆以太网接口，跳过网卡配置。\n"
            "  [dim]  连接相机网线后运行：uv run dcpam net[/]"
        )
        return

    cmd = ["sudo", "ifconfig", iface, _CAMERA_HOST_IP, "netmask", _CAMERA_NETMASK, "up"]
    console.print(f"  [green]•[/] 配置网卡 [bold]{iface}[/] = {_CAMERA_HOST_IP}")
    console.print("  [dim]  （回车跳过则不配置，后续可 uv run dcpam net 手动配置）[/]")
    try:
        result = subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        console.print("\n  [yellow]  跳过网卡配置[/]")
        return
    if result.returncode != 0:
        console.print(f"  [yellow]  网卡配置未完成（退出码 {result.returncode}），继续启动 web[/]")


def main() -> None:
    """dcpam 入口：`dcpam` 启动前后端；`dcpam net` 配置相机网卡。"""
    _force_utf8_console()

    if len(sys.argv) > 1 and sys.argv[1] == "net":
        sys.exit(_run_net_command())

    _ensure_aravis_libs()

    paths = DCPAMPaths()
    paths.ensure_dirs()

    _startup_configure_net()

    results = print_health_report(paths)
    failed = [r for r in results if not r.passed]
    if failed:
        console.print(
            "  [yellow]以上检测未全部通过：分析模式可直接使用；测量模式（拍照/预览）需要相机连接[/]\n"
            "  [dim]修复后无需重启，前端切到测量模式点 ⚡ 即可重连相机[/]\n"
        )

    host = os.environ.get("DCPAM_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DCPAM_PORT", DEFAULT_PORT))

    console.print(f"  [green]API[/]  http://{host}:{port}")
    _start_backend(host=host, port=port)
    time.sleep(0.4)  # 让 uvicorn 抢先打印 banner

    try:
        frontend = _start_frontend()
    except RuntimeError as exc:
        console.print(f"  [bold red]✗[/] {exc}")
        sys.exit(1)

    def _on_terminal_signal(signum, _frame):
        _terminate_process_group(frontend)
        sys.exit(128 + signum)

    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _on_terminal_signal)
    signal.signal(signal.SIGTERM, _on_terminal_signal)

    console.print("  [dim]Ctrl+C 退出[/]")
    try:
        frontend.wait()
    except KeyboardInterrupt:
        console.print("\n  [dim]正在关闭...[/]")
        _terminate_process_group(frontend)
