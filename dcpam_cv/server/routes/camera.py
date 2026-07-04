"""DCPAM Web 后端：相机健康与重连路由。"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

_last_health_ok: Optional[bool] = None


def _log_health_change(ok: bool, message: str = "") -> None:
    """相机状态变化时打印一行到 server stdout（不重复打）。"""
    global _last_health_ok
    if _last_health_ok == ok:
        return
    _last_health_ok = ok
    ts = datetime.now().strftime("%H:%M:%S")
    if ok:
        print(f"[{ts}] 相机已连接", flush=True)
    else:
        print(f"[{ts}] 相机丢失:{message}", flush=True)


@router.get("/api/health")
def health() -> dict:
    """相机健康：只有真实抓到过帧才算 ok；最近一次抓帧失败就报错。"""
    with state._camera_lock:
        cached = state._camera
        last_err = state._last_capture_error
    if cached is None:
        try:
            state._get_camera()
        except Exception as exc:
            msg = state._describe(exc)
            _log_health_change(False, msg)
            return {"camera": "error", "message": msg}
        # 首次打开后再做一次真实抓帧确认
        try:
            _probe_capture()
        except Exception as exc:
            msg = state._describe(exc)
            _log_health_change(False, msg)
            return {"camera": "error", "message": msg}
        _log_health_change(True)
        return {"camera": "ok"}
    if last_err:
        _log_health_change(False, last_err)
        return {"camera": "error", "message": last_err}
    _log_health_change(True)
    return {"camera": "ok"}


def _probe_capture() -> None:
    """做一次真实抓帧确认相机在线。失败时抛异常并把 cache 清掉。"""
    with state._camera_lock:
        cam = state._get_camera()
        try:
            cam.capture()
        except Exception as exc:
            state._mark_capture_failed(state._describe(exc))
            raise
        state._mark_capture_ok()


@router.post("/api/camera/reconnect")
def camera_reconnect() -> dict:
    # 先尝试无密码 sudo 重配 IP（利用启动时缓存的 sudo credentials）。
    # 失败不 fatal，因为掉线可能不是 IP 问题；返回值里带 sudo_status 让前端提示。
    net_status = _reconfigure_camera_ip()

    state._close_camera()
    state._reset_camera_error()
    try:
        state._get_camera()
    except Exception as exc:
        detail = {
            "message": f"相机连接失败:{state._describe(exc)}",
            "net": net_status,
        }
        raise HTTPException(503, detail) from exc
    # open() 成功也不代表网线还接着——再抓一帧验证
    try:
        _probe_capture()
    except Exception as exc:
        detail = {
            "message": f"相机断线:{state._describe(exc)}",
            "net": net_status,
        }
        raise HTTPException(503, detail) from exc
    return {"camera": "ok", "net": net_status}


def _find_camera_interface() -> Optional[str]:
    """扫描 ifconfig 找活跃的千兆以太网接口。"""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    current_iface: Optional[str] = None
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


def _reconfigure_camera_ip() -> dict:
    """尝试无密码 sudo 重配 IP。
    返回 {status, interface?, message?}：
      status = "ok" | "no_interface" | "sudo_expired" | "not_darwin" | "error"
    """
    if sys.platform != "darwin":
        return {"status": "not_darwin"}
    iface = _find_camera_interface()
    if not iface:
        return {"status": "no_interface", "message": "未检测到千兆以太网接口，请检查网线"}

    cmd = ["sudo", "-n", "ifconfig", iface, "192.168.0.1", "netmask", "255.255.255.0", "up"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "message": state._describe(exc)}
    if result.returncode == 0:
        return {"status": "ok", "interface": iface}
    stderr = result.stderr.strip()
    if "password is required" in stderr or "a password is required" in stderr:
        return {
            "status": "sudo_expired",
            "interface": iface,
            "message": "sudo 密码已过期，请在启动 dcpam 的终端执行 `sudo -v` 后再点重连",
        }
    return {"status": "error", "interface": iface, "message": stderr or f"exit {result.returncode}"}
