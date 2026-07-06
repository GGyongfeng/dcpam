"""DCPAM Web 后端：相机健康与重连路由。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import net, state

router = APIRouter()


def _log(message: str) -> None:
    """打一行带时间戳的日志到 server stdout（与 _log_health_change 同风格）。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


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
    _log("收到重连请求")
    # 先尝试免密 sudo 重配 IP（配前会清掉抢路由的残留网卡）。
    # 失败不 fatal，因为掉线可能不是 IP 问题；返回值里带 net 状态让前端提示。
    net_status = _reconfigure_camera_ip()
    if net_status["status"] == "ok":
        _log(f"配置网卡 {net_status.get('interface')} = {net.CAMERA_HOST_IP}")
        route = net_status.get("route") or {}
        if route.get("ok"):
            _log(f"直连路由 → {route.get('route_iface')}（正常）")
        elif route:
            _log(f"路由异常：{route.get('message')}")
    elif net_status["status"] == "nopasswd_missing":
        _log("免密规则未安装，跳过配网卡")
    elif net_status["status"] == "no_interface":
        _log("未检测到千兆以太网接口，跳过配网卡")

    state._close_camera()
    state._reset_camera_error()
    try:
        state._get_camera()
    except Exception as exc:
        msg = state._describe(exc)
        _log(f"重连失败：{msg}")
        detail = {
            "message": f"相机连接失败:{msg}",
            "net": net_status,
        }
        raise HTTPException(503, detail) from exc
    # open() 成功也不代表网线还接着——再抓一帧验证
    try:
        _probe_capture()
    except Exception as exc:
        msg = state._describe(exc)
        _log(f"重连失败：{msg}")
        detail = {
            "message": f"相机断线:{msg}",
            "net": net_status,
        }
        raise HTTPException(503, detail) from exc
    _log("相机已重连")
    return {"camera": "ok", "net": net_status}


def _reconfigure_camera_ip() -> dict:
    """用免密 sudo（-n）重配相机 IP：先清冲突网卡，再配相机网卡，最后校验路由。

    返回 {status, interface?, route?, message?}：
      status = "ok" | "no_interface" | "nopasswd_missing" | "not_darwin" | "error"

    需要预先安装免密规则（/etc/sudoers.d/dcpam-camera-net），装一次后永久免密。
    """
    import sys

    if sys.platform != "darwin":
        return {"status": "not_darwin"}
    iface = net.find_camera_interface()
    if not iface:
        return {"status": "no_interface", "message": "未检测到千兆以太网接口，请检查网线"}

    # 配前清掉其它网卡上的同网段残留（防抢路由），失败不致命。
    for conflict in net.find_conflicting_interfaces(iface):
        if net.clear_conflicting_ip(conflict):
            _log(f"清理冲突网卡 {conflict} 上的 {net.CAMERA_HOST_IP}")
        else:
            _log(f"网卡 {conflict} 抢占 {net.CAMERA_HOST_IP} 但免密清理失败，请手动清理")

    if not net.configure_camera_ip(iface):
        return {
            "status": "nopasswd_missing",
            "interface": iface,
            "message": "未安装免密规则，请在启动 dcpam 的终端按提示执行一次性安装命令后重试",
        }

    route = net.verify_camera_route(iface)
    return {"status": "ok", "interface": iface, "route": route}
