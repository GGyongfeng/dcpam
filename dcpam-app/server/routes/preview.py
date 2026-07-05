"""DCPAM Web 后端：MJPEG 预览路由。"""
from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from .. import constants, state
from ..schemas import PreviewConfigUpdate

router = APIRouter()


def _encode_jpeg(frame: np.ndarray) -> bytes:
    h, w = frame.shape[:2]
    if max(h, w) > constants.PREVIEW_MAX_SIDE:
        scale = constants.PREVIEW_MAX_SIDE / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), constants.PREVIEW_QUALITY])
    if not ok:
        raise RuntimeError("JPEG 编码失败")
    return enc.tobytes()


def _error_frame(message: str) -> bytes:
    canvas = np.zeros((360, 640, 3), dtype=np.uint8)
    # cv2.putText 不支持中文；把非 ASCII 字符替换掉，避免乱码
    ascii_msg = (message or "camera error").encode("ascii", "replace").decode("ascii")
    cv2.putText(canvas, ascii_msg[:60], (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return _encode_jpeg(canvas)


def _preview_generator(which: str):
    """MJPEG 消费者：从 _frame_cond 上等新帧，encode，yield。"""
    boundary = b"--frame\r\n"
    state._acquire_preview_producer()
    last_seen = -1
    try:
        while True:
            with state._frame_cond:
                # 至多等 1s；超时也继续循环，保持 HTTP 连接活着
                state._frame_cond.wait_for(
                    lambda: state._latest_pair_seq != last_seen,
                    timeout=1.0,
                )
                if state._latest_pair_seq == last_seen:
                    continue
                pair = state._latest_pair
                error = state._latest_pair_error
                last_seen = state._latest_pair_seq

            try:
                if pair is None:
                    jpeg = _error_frame(error or "camera error")
                else:
                    frame = pair.front if which == "front" else pair.rear
                    jpeg = _encode_jpeg(frame)
            except Exception as exc:
                jpeg = _error_frame(state._describe(exc))

            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
    finally:
        state._release_preview_producer()


@router.get("/api/preview/config")
def get_preview_config() -> dict:
    return {
        "interval_ms": int(round(constants.PREVIEW_INTERVAL_S * 1000)),
        "max_side": constants.PREVIEW_MAX_SIDE,
        "quality": constants.PREVIEW_QUALITY,
    }


@router.post("/api/preview/config")
def set_preview_config(update: PreviewConfigUpdate = Body(...)) -> dict:
    """运行时改预览参数——生产者/编码器在下一帧就读取新值，无需重启。"""
    if update.interval_ms is not None:
        if not (0 <= update.interval_ms <= 500):
            raise HTTPException(400, "interval_ms 必须在 0-500 之间")
        constants.PREVIEW_INTERVAL_S = update.interval_ms / 1000.0
    if update.max_side is not None:
        if not (200 <= update.max_side <= 2600):
            raise HTTPException(400, "max_side 必须在 200-2600 之间")
        constants.PREVIEW_MAX_SIDE = int(update.max_side)
    if update.quality is not None:
        if not (1 <= update.quality <= 100):
            raise HTTPException(400, "quality 必须在 1-100 之间")
        constants.PREVIEW_QUALITY = int(update.quality)
    return get_preview_config()


@router.get("/api/preview.mjpeg")
def preview(cam: str = "front"):
    if cam not in ("front", "rear"):
        raise HTTPException(400, "cam 必须是 front 或 rear")
    return StreamingResponse(
        _preview_generator(cam),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
