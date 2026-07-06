from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dcpam.path import DCPAMPaths
from dcpam.pipeline import console
from . import net
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


def _reload_enabled() -> bool:
    """默认开启后端热更新；DCPAM_NO_RELOAD=1 可关闭。"""
    return os.environ.get("DCPAM_NO_RELOAD") != "1"


def _start_backend(host: str, port: int) -> subprocess.Popen | None:
    """启动 uvicorn 后端。

    默认（热更新）：作为独立子进程跑，开启 --reload —— reloader 需要独占主线程/
    进程，无法在线程里跑，故走子进程。返回该子进程供退出时清理。
    DCPAM_NO_RELOAD=1：在后台守护线程里跑（随主进程退出而结束），不热更。
    """
    if _reload_enabled():
        env = {**os.environ, "DCPAM_HOST": host, "DCPAM_PORT": str(port)}
        kwargs = {"env": env}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen([sys.executable, "-m", "dcpam_app.server.app"], **kwargs)

    from .app import run as run_server

    thread = threading.Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        name="dcpam-server",
        daemon=True,
    )
    thread.start()
    return None


def _start_frontend() -> subprocess.Popen:
    """启动 vite dev server。失败抛出 RuntimeError。"""
    # cli 现处 dcpam_app/server/，web 在 dcpam_app/web/
    web_dir = Path(__file__).resolve().parent.parent / "web"
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


_CAMERA_HOST_IP = net.CAMERA_HOST_IP
_CAMERA_NETMASK = net.CAMERA_NETMASK

# 免密 sudo 规则文件（仅放开配置/清理相机网卡这两条命令）。
# 装一次后，启动/重连配网卡、清理冲突网卡都不再要密码。
# 仅 macOS 需要；Windows 走 Galaxy SDK 不涉及。
_SUDOERS_FILE = net.SUDOERS_FILE
# 两行规则：① 把 en 网口配成 192.168.0.1；② 摘掉 en 网口上的 192.168.0.1（清理抢路由的残留网卡）。
_SUDOERS_RULES = (
    "%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* 192.168.0.1 netmask 255.255.255.0 up",
    "%s ALL=(root) NOPASSWD: /sbin/ifconfig en[0-9]* -alias 192.168.0.1",
)


def _sudoers_setup_command() -> str:
    """返回一次性安装免密规则的完整命令（供提示用户手动执行）。"""
    import getpass

    user = getpass.getuser()
    rules = "\\n".join(rule % user for rule in _SUDOERS_RULES)
    return (
        f"printf '{rules}\\n' | sudo tee {_SUDOERS_FILE} > /dev/null "
        f"&& sudo chmod 440 {_SUDOERS_FILE} "
        f"&& sudo visudo -c -f {_SUDOERS_FILE}"
    )


def _print_sudoers_setup_hint() -> None:
    """提示用户一次性安装免密规则，之后配网卡不再要密码。"""
    console.print(
        "  [yellow]•[/] 配置相机网卡需要 sudo。执行下面这条命令[bold]一次[/]（输一次密码），"
        "之后启动/重连都免密：\n"
    )
    console.print(f"      [cyan]{_sudoers_setup_command()}[/]\n")
    console.print("  [dim]  看到 “parsed OK” 即成功。仅放开配置/清理相机网卡这两条命令，其它 sudo 不受影响。[/]")


def _configure_camera_ip_nopasswd(iface: str) -> bool:
    """把网口配成相机 IP。配之前先清掉其它网卡上的同网段残留（防抢路由）。

    成功返回 True；未装免密规则返回 False。清理失败不 fatal（打印提示后继续配）。
    """
    for conflict in net.find_conflicting_interfaces(iface):
        if net.clear_conflicting_ip(conflict):
            console.print(f"  [green]•[/] 已清理冲突网卡 [bold]{conflict}[/] 上的 {_CAMERA_HOST_IP}")
        else:
            console.print(
                f"  [yellow]•[/] 网卡 [bold]{conflict}[/] 也配了 {_CAMERA_HOST_IP} 会抢路由，"
                f"但免密清理失败，可手动：sudo ifconfig {conflict} -alias {_CAMERA_HOST_IP}"
            )
    return net.configure_camera_ip(iface)


def _find_camera_interface() -> str | None:
    """macOS: 找一个活跃的千兆以太网接口用于配置 192.168.0.1。"""
    return net.find_camera_interface()


def _report_route_verification(iface: str) -> None:
    """配完 IP 后校验直连路由指向；异常打印明确告警。"""
    result = net.verify_camera_route(iface)
    if result["ok"]:
        console.print(f"  [green]•[/] {result['message']}")
    else:
        console.print(f"  [bold red]✗[/] {result['message']}")


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

    console.print(f"  [green]•[/] 检测到千兆接口：[bold]{iface}[/]")
    if _configure_camera_ip_nopasswd(iface):
        console.print(f"  [bold green]✓[/] 已配置 {iface} = {_CAMERA_HOST_IP}")
        _report_route_verification(iface)
        return 0

    # 免密规则尚未安装：提示一次性安装，不再交互式要密码
    console.print("  [bold red]✗[/] 配置失败：尚未安装免密规则。")
    _print_sudoers_setup_hint()
    return 1


def _startup_configure_net() -> None:
    """启动时用免密 sudo 配相机 IP。

    已装免密规则（见 _SUDOERS_FILE）→ 静默配好，无需密码；
    未装 → 打印一次性安装提示，不阻塞、正常启动 web。
    Windows 不涉及（走 Galaxy SDK，无需配 192.168.0.1）。
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

    if _configure_camera_ip_nopasswd(iface):
        console.print(f"  [green]•[/] 已配置网卡 [bold]{iface}[/] = {_CAMERA_HOST_IP}")
        _report_route_verification(iface)
        return

    # 免密规则尚未安装：提示用户一次性安装
    _print_sudoers_setup_hint()


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
            "  [yellow]以上自检未全部通过：分析模式可直接使用；测量模式（拍照/预览）需按上面的提示修复[/]\n"
            "  [dim]修复后无需重启，前端切到测量模式点 ⚡ 即可连接相机[/]\n"
        )

    host = os.environ.get("DCPAM_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DCPAM_PORT", DEFAULT_PORT))

    console.print(f"  [green]API[/]  http://{host}:{port}")
    if _reload_enabled():
        console.print("  [dim]后端热更新已开启（改 .py 自动重启）；DCPAM_NO_RELOAD=1 可关闭[/]")
    backend = _start_backend(host=host, port=port)
    time.sleep(0.4)  # 让 uvicorn 抢先打印 banner

    try:
        frontend = _start_frontend()
    except RuntimeError as exc:
        console.print(f"  [bold red]✗[/] {exc}")
        if backend is not None:
            _terminate_process_group(backend)
        sys.exit(1)

    def _shutdown() -> None:
        _terminate_process_group(frontend)
        if backend is not None:
            _terminate_process_group(backend)

    def _on_terminal_signal(signum, _frame):
        _shutdown()
        sys.exit(128 + signum)

    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _on_terminal_signal)
    signal.signal(signal.SIGTERM, _on_terminal_signal)

    console.print("  [dim]Ctrl+C 退出[/]")
    try:
        frontend.wait()
    except KeyboardInterrupt:
        console.print("\n  [dim]正在关闭...[/]")
        _shutdown()
