"""DCPAM Web 后端：相机 + 预览生产者的共享可变状态与访问函数。

模块级可变状态（用 global 修改）都集中在这里。路由模块通过
`from .. import state` 后以 `state._camera` / `state._get_camera()` 的方式访问，
不要在路由模块里用 global 改这里的变量（跨模块 global 不生效）。
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import constants
from .constants import PATHS

_camera_lock = threading.RLock()
_camera = None
_camera_error: Optional[str] = None
_last_capture_error: Optional[str] = None
_last_capture_ts: float = 0.0

# ---- Preview 生产者-消费者共享状态 ----
# 一个后台线程持续 cam.capture() → _latest_pair；两条 MJPEG 消费者从
# Condition 上等新帧，不再各自 capture，也不抢 _camera_lock。
_frame_cond = threading.Condition()
_latest_pair = None                 # 最新的 ImagePair（或 None 表示上一次失败）
_latest_pair_seq: int = 0           # 每收到新帧自增，供消费者判断"是不是新的"
_latest_pair_error: Optional[str] = None  # 若上次 capture 失败，这里保留错误消息
_preview_thread: Optional[threading.Thread] = None
_preview_stop = threading.Event()
_preview_consumers: int = 0
_preview_consumers_lock = threading.Lock()


def _describe(exc: BaseException) -> str:
    msg = str(exc)
    return msg or exc.__class__.__name__


def _mark_capture_ok() -> None:
    global _last_capture_error, _last_capture_ts
    with _camera_lock:
        _last_capture_error = None
        _last_capture_ts = time.time()


def _mark_capture_failed(message: str) -> None:
    """记录采集失败；同时把缓存的相机丢掉，逼迫下次 open()。"""
    global _camera, _last_capture_error, _last_capture_ts
    with _camera_lock:
        _last_capture_error = message or "capture failed"
        _last_capture_ts = time.time()
        if _camera is not None:
            try:
                _camera.close()
            except Exception:
                pass
        _camera = None


def _get_camera():
    """懒加载双相机；失败时缓存错误信息直到下一次显式重试。"""
    global _camera, _camera_error
    with _camera_lock:
        if _camera is not None:
            return _camera
        from dcpam.camera import DualCamera

        try:
            cam = DualCamera(paths=PATHS)
            cam.open()
        except Exception as exc:
            _camera_error = str(exc)
            raise
        _camera = cam
        _camera_error = None
        return cam


def _close_camera() -> None:
    global _camera, _camera_error, _last_capture_error
    with _camera_lock:
        if _camera is not None:
            try:
                _camera.close()
            except Exception:
                pass
        _camera = None
        _camera_error = None
        _last_capture_error = None


def _reset_camera_error() -> None:
    """允许下一次调用重新尝试 open。"""
    global _camera_error
    with _camera_lock:
        _camera_error = None


def _preview_producer_loop() -> None:
    """后台线程：持续 cam.capture() 并把最新一对图放到 _latest_pair。

    - 通过 Condition.notify_all() 唤醒所有等待的消费者
    - 每轮结束用 _preview_stop.wait(PREVIEW_INTERVAL_S) 做限速，也用来响应停止
    - _camera_lock 保证跟 /api/capture 天然互斥：采样期间生产者会自然阻塞
    """
    global _latest_pair, _latest_pair_seq, _latest_pair_error
    while not _preview_stop.is_set():
        pair = None
        error: Optional[str] = None
        try:
            with _camera_lock:
                cam = _get_camera()
                pair = cam.capture()
            _mark_capture_ok()
        except Exception as exc:
            error = _describe(exc)
            _mark_capture_failed(error)

        with _frame_cond:
            _latest_pair = pair
            _latest_pair_error = error
            _latest_pair_seq += 1
            _frame_cond.notify_all()

        # 失败时退避 0.5s，成功时按 PREVIEW_INTERVAL_S 限速；两种情况都能被 stop 打断
        delay = 0.5 if error else constants.PREVIEW_INTERVAL_S
        if _preview_stop.wait(delay):
            break


def _acquire_preview_producer() -> None:
    """新增一个 MJPEG 消费者；必要时启动生产者线程。"""
    global _preview_thread, _preview_consumers
    with _preview_consumers_lock:
        _preview_consumers += 1
        if _preview_thread is None or not _preview_thread.is_alive():
            _preview_stop.clear()
            _preview_thread = threading.Thread(
                target=_preview_producer_loop,
                name="dcpam-preview",
                daemon=True,
            )
            _preview_thread.start()


def _release_preview_producer() -> None:
    """消费者退出；引用计数归零时通知生产者停下。"""
    global _preview_thread, _preview_consumers
    with _preview_consumers_lock:
        _preview_consumers -= 1
        if _preview_consumers <= 0:
            _preview_consumers = 0
            _preview_stop.set()
            _preview_thread = None  # 不 join：让 daemon 线程自行退出，避免阻塞请求
