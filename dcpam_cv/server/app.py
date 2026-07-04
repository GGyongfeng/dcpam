"""DCPAM Web 后端：提供拍照、预览、JSONL 落盘 API。"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import tomllib
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import tomli_w
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ..config import SpotExtractionConfig
from ..path import DCPAMPaths
from ..steps.spot_extraction import extract_spots

PATHS = DCPAMPaths()
DATA_DIR = PATHS.root / "data"
MEASUREMENTS_DIR = DATA_DIR / "measurements"
CONFIG_PATH = PATHS.config_file
CONFIG_BACKUP_DIR = DATA_DIR / "config_backups"

CAPTURE_MAX_N = 50
PREVIEW_MAX_SIDE = 800
PREVIEW_QUALITY = 60

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
PREVIEW_INTERVAL_S = 0.033  # ~30 fps 上限（实际取决于相机 fps）

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
        from ..camera import DualCamera

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


app = FastAPI(title="DCPAM Server")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    _close_camera()


app.router.lifespan_context = _lifespan


def _describe(exc: BaseException) -> str:
    msg = str(exc)
    return msg or exc.__class__.__name__


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


@app.get("/api/health")
def health() -> dict:
    """相机健康：只有真实抓到过帧才算 ok；最近一次抓帧失败就报错。"""
    with _camera_lock:
        cached = _camera
        last_err = _last_capture_error
    if cached is None:
        try:
            _get_camera()
        except Exception as exc:
            msg = _describe(exc)
            _log_health_change(False, msg)
            return {"camera": "error", "message": msg}
        # 首次打开后再做一次真实抓帧确认
        try:
            _probe_capture()
        except Exception as exc:
            msg = _describe(exc)
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
    with _camera_lock:
        cam = _get_camera()
        try:
            cam.capture()
        except Exception as exc:
            _mark_capture_failed(_describe(exc))
            raise
        _mark_capture_ok()


@app.post("/api/camera/reconnect")
def camera_reconnect() -> dict:
    # 先尝试无密码 sudo 重配 IP（利用启动时缓存的 sudo credentials）。
    # 失败不 fatal，因为掉线可能不是 IP 问题；返回值里带 sudo_status 让前端提示。
    net_status = _reconfigure_camera_ip()

    _close_camera()
    _reset_camera_error()
    try:
        _get_camera()
    except Exception as exc:
        detail = {
            "message": f"相机连接失败:{_describe(exc)}",
            "net": net_status,
        }
        raise HTTPException(503, detail) from exc
    # open() 成功也不代表网线还接着——再抓一帧验证
    try:
        _probe_capture()
    except Exception as exc:
        detail = {
            "message": f"相机断线:{_describe(exc)}",
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
        return {"status": "error", "message": _describe(exc)}
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


# ---------------------------------------------------------------------------
# Preview (MJPEG)
# ---------------------------------------------------------------------------

def _encode_jpeg(frame: np.ndarray) -> bytes:
    h, w = frame.shape[:2]
    if max(h, w) > PREVIEW_MAX_SIDE:
        scale = PREVIEW_MAX_SIDE / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), PREVIEW_QUALITY])
    if not ok:
        raise RuntimeError("JPEG 编码失败")
    return enc.tobytes()


def _error_frame(message: str) -> bytes:
    canvas = np.zeros((360, 640, 3), dtype=np.uint8)
    # cv2.putText 不支持中文；把非 ASCII 字符替换掉，避免乱码
    ascii_msg = (message or "camera error").encode("ascii", "replace").decode("ascii")
    cv2.putText(canvas, ascii_msg[:60], (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return _encode_jpeg(canvas)


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
        delay = 0.5 if error else PREVIEW_INTERVAL_S
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


def _preview_generator(which: str):
    """MJPEG 消费者：从 _frame_cond 上等新帧，encode，yield。"""
    boundary = b"--frame\r\n"
    _acquire_preview_producer()
    last_seen = -1
    try:
        while True:
            with _frame_cond:
                # 至多等 1s；超时也继续循环，保持 HTTP 连接活着
                _frame_cond.wait_for(
                    lambda: _latest_pair_seq != last_seen,
                    timeout=1.0,
                )
                if _latest_pair_seq == last_seen:
                    continue
                pair = _latest_pair
                error = _latest_pair_error
                last_seen = _latest_pair_seq

            try:
                if pair is None:
                    jpeg = _error_frame(error or "camera error")
                else:
                    frame = pair.front if which == "front" else pair.rear
                    jpeg = _encode_jpeg(frame)
            except Exception as exc:
                jpeg = _error_frame(_describe(exc))

            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
    finally:
        _release_preview_producer()


class PreviewConfigUpdate(BaseModel):
    """预览参数的运行时可调项。所有字段可选，仅传的字段会被更新。"""
    interval_ms: Optional[int] = None      # 0 ~ 500 ms
    max_side: Optional[int] = None         # 200 ~ 2600 px
    quality: Optional[int] = None          # 1 ~ 100


@app.get("/api/preview/config")
def get_preview_config() -> dict:
    return {
        "interval_ms": int(round(PREVIEW_INTERVAL_S * 1000)),
        "max_side": PREVIEW_MAX_SIDE,
        "quality": PREVIEW_QUALITY,
    }


@app.post("/api/preview/config")
def set_preview_config(update: PreviewConfigUpdate = Body(...)) -> dict:
    """运行时改预览参数——生产者/编码器在下一帧就读取新值，无需重启。"""
    global PREVIEW_INTERVAL_S, PREVIEW_MAX_SIDE, PREVIEW_QUALITY
    if update.interval_ms is not None:
        if not (0 <= update.interval_ms <= 500):
            raise HTTPException(400, "interval_ms 必须在 0-500 之间")
        PREVIEW_INTERVAL_S = update.interval_ms / 1000.0
    if update.max_side is not None:
        if not (200 <= update.max_side <= 2600):
            raise HTTPException(400, "max_side 必须在 200-2600 之间")
        PREVIEW_MAX_SIDE = int(update.max_side)
    if update.quality is not None:
        if not (1 <= update.quality <= 100):
            raise HTTPException(400, "quality 必须在 1-100 之间")
        PREVIEW_QUALITY = int(update.quality)
    return get_preview_config()


@app.get("/api/preview.mjpeg")
def preview(cam: str = "front"):
    if cam not in ("front", "rear"):
        raise HTTPException(400, "cam 必须是 front 或 rear")
    return StreamingResponse(
        _preview_generator(cam),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# Capture + sample.json（每次采样一个目录）
# ---------------------------------------------------------------------------

class CaptureRequest(BaseModel):
    n: int = 10
    name: str = "sample"
    index: int = 1


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _sanitize_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "sample"
    if not _NAME_RE.match(name):
        raise HTTPException(400, "名称只能包含字母、数字、._-，长度 1-64")
    return name


def _load_measurements() -> list[dict]:
    if not MEASUREMENTS_DIR.exists():
        return []
    records: list[dict] = []
    for sub in sorted(MEASUREMENTS_DIR.iterdir()):
        if not sub.is_dir():
            continue
        sample_json = sub / "sample.json"
        if not sample_json.exists():
            continue
        try:
            records.append(json.loads(sample_json.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    records.sort(key=lambda r: r.get("ts", ""))
    return records


@app.post("/api/capture")
def capture(req: CaptureRequest = Body(default=CaptureRequest())) -> dict:
    n = max(1, min(CAPTURE_MAX_N, int(req.n)))
    name = _sanitize_name(req.name)
    index = max(1, int(req.index or 1))
    record_id = f"{name}-{index:03d}"

    sample_dir = MEASUREMENTS_DIR / record_id
    if sample_dir.exists():
        raise HTTPException(409, f"采样目录已存在：{record_id}")

    try:
        cam = _get_camera()
    except Exception as exc:
        raise HTTPException(503, f"相机连接失败:{_describe(exc)}") from exc

    sample_dir.mkdir(parents=True, exist_ok=True)
    spot_config = SpotExtractionConfig()

    ts = datetime.now()
    t_capture_start = time.perf_counter()

    # 阶段 1：紧凑拍照 —— capture 串行，imwrite 丢线程池不阻塞下一帧。
    pairs: list[tuple[int, np.ndarray, np.ndarray, Path, Path]] = []
    with _camera_lock, ThreadPoolExecutor(max_workers=4) as executor:
        write_futures = []
        for i in range(n):
            try:
                pair = cam.capture()
            except Exception as exc:
                _mark_capture_failed(_describe(exc))
                raise HTTPException(500, f"第 {i + 1} 帧拍照失败：{_describe(exc)}") from exc

            front_path = sample_dir / f"cam1_{i:03d}.png"
            rear_path = sample_dir / f"cam2_{i:03d}.png"
            write_futures.append(executor.submit(cv2.imwrite, str(front_path), pair.front))
            write_futures.append(executor.submit(cv2.imwrite, str(rear_path), pair.rear))
            pairs.append((i, pair.front, pair.rear, front_path, rear_path))

        for fut in write_futures:
            fut.result()
    _mark_capture_ok()
    t_capture_done = time.perf_counter()

    # 阶段 2：批量提圆心
    frames: list[dict] = []
    extraction_errors: list[str] = []
    for i, front_img, rear_img, front_path, rear_path in pairs:
        try:
            result = extract_spots(_to_gray(front_img), _to_gray(rear_img), spot_config)
            front_uv: Optional[list[float]] = [result.spots.front.u, result.spots.front.v]
            rear_uv: Optional[list[float]] = [result.spots.rear.u, result.spots.rear.v]
            front_q = _quality_to_dict(result.front_quality)
            rear_q = _quality_to_dict(result.rear_quality)
        except Exception as exc:
            front_uv = None
            rear_uv = None
            front_q = None
            rear_q = None
            extraction_errors.append(f"frame {i}: {_describe(exc)}")

        frames.append({
            "index": i,
            "front_path": str(front_path.resolve()),
            "rear_path": str(rear_path.resolve()),
            "front_uv": front_uv,
            "rear_uv": rear_uv,
            "front_quality": front_q,
            "rear_quality": rear_q,
        })
    t_extract_done = time.perf_counter()

    valid_front = np.array([f["front_uv"] for f in frames if f["front_uv"] is not None])
    valid_rear = np.array([f["rear_uv"] for f in frames if f["rear_uv"] is not None])

    if valid_front.size == 0 or valid_rear.size == 0:
        # 提取全失败：留下图但删空 record dir
        raise HTTPException(
            500,
            "圆心提取全部失败：\n" + "\n".join(extraction_errors[:5]),
        )

    # 聚合各帧 confidence（min / mean），方便前端一眼判断这次采样质量
    def _agg_confidence(side: str) -> dict:
        vals = [f[f"{side}_quality"]["confidence"]
                for f in frames if f.get(f"{side}_quality")]
        if not vals:
            return {"min": 0.0, "mean": 0.0}
        return {"min": float(min(vals)), "mean": float(sum(vals) / len(vals))}

    front_conf = _agg_confidence("front")
    rear_conf = _agg_confidence("rear")

    def _mean_std(arr: np.ndarray) -> tuple[list[float], list[float]]:
        mean = arr.mean(axis=0).tolist()
        std = arr.std(axis=0).tolist() if arr.shape[0] > 1 else [0.0, 0.0]
        return mean, std

    front_mean, front_std = _mean_std(valid_front)
    rear_mean, rear_std = _mean_std(valid_rear)

    record = {
        "id": record_id,
        "name": name,
        "index": index,
        "ts": ts.isoformat(),
        "n": n,
        "valid_n": min(int(valid_front.shape[0]), int(valid_rear.shape[0])),
        "dir": str(sample_dir.resolve()),
        "frames": frames,
        "front_uv_mean": front_mean,
        "rear_uv_mean": rear_mean,
        "front_uv_std": front_std,
        "rear_uv_std": rear_std,
        "front_confidence": front_conf,
        "rear_confidence": rear_conf,
        "extraction_errors": extraction_errors,
        "timing_ms": {
            "capture": int((t_capture_done - t_capture_start) * 1000),
            "extract": int((t_extract_done - t_capture_done) * 1000),
        },
    }
    sample_json = sample_dir / "sample.json"
    sample_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _quality_to_dict(q) -> dict:
    """SpotQuality dataclass → JSON 可序列化 dict。"""
    return {
        "max_intensity": q.max_intensity,
        "peak_to_bg_ratio": q.peak_to_bg_ratio,
        "mask_pixel_count": q.mask_pixel_count,
        "compactness": q.compactness,
        "confidence": q.confidence,
    }


@app.get("/api/measurements")
def list_measurements() -> list[dict]:
    return _load_measurements()


@app.delete("/api/measurements/{record_id}")
def delete_measurement(record_id: str) -> dict:
    """删除单个采样目录（连同图片、sample.json 一起清掉）。"""
    if not _ID_RE.match(record_id or ""):
        raise HTTPException(400, "非法的采样 id")
    base = MEASUREMENTS_DIR.resolve()
    sub = (MEASUREMENTS_DIR / record_id).resolve()
    try:
        sub.relative_to(base)
    except ValueError:
        raise HTTPException(400, "非法的采样 id")
    if not sub.exists():
        raise HTTPException(404, f"采样目录不存在：{record_id}")
    if not sub.is_dir():
        raise HTTPException(400, f"路径不是目录：{record_id}")
    import shutil

    try:
        shutil.rmtree(sub)
    except OSError as exc:
        raise HTTPException(500, f"删除失败：{_describe(exc)}") from exc
    return {"ok": True, "id": record_id}


@app.get("/api/measurements/next-index")
def next_index(name: str) -> dict:
    """给定名称，找当前磁盘上最大 index，返回 max+1（用作下次序号的默认值）。"""
    name = _sanitize_name(name)
    if not MEASUREMENTS_DIR.exists():
        return {"name": name, "next_index": 1}
    prefix = f"{name}-"
    max_index = 0
    for sub in MEASUREMENTS_DIR.iterdir():
        if not sub.is_dir() or not sub.name.startswith(prefix):
            continue
        try:
            idx = int(sub.name[len(prefix):])
        except ValueError:
            continue
        max_index = max(max_index, idx)
    return {"name": name, "next_index": max_index + 1}


_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}-\d{1,6}$")


class ExportRequest(BaseModel):
    ids: list[str]


@app.post("/api/measurements/export-zip")
def export_measurements_zip(req: ExportRequest = Body(...)) -> StreamingResponse:
    """把选中的采样目录整体打包成 zip 下载。"""
    if not req.ids:
        raise HTTPException(400, "请至少选择一个采样")
    if not MEASUREMENTS_DIR.exists():
        raise HTTPException(404, "尚无采样目录")

    base = MEASUREMENTS_DIR.resolve()
    picked: list[tuple[str, Path]] = []
    missing: list[str] = []
    for raw in req.ids:
        rid = (raw or "").strip()
        if not _ID_RE.match(rid):
            missing.append(rid or "<empty>")
            continue
        sub = (MEASUREMENTS_DIR / rid).resolve()
        try:
            sub.relative_to(base)
        except ValueError:
            missing.append(rid)
            continue
        if not sub.is_dir() or not (sub / "sample.json").exists():
            missing.append(rid)
            continue
        picked.append((rid, sub))

    if not picked:
        detail = "找不到有效采样目录"
        if missing:
            detail += f"：{', '.join(missing[:5])}"
        raise HTTPException(404, detail)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rid, sub in picked:
            for path in sorted(sub.rglob("*")):
                if not path.is_file():
                    continue
                arcname = f"{rid}/{path.relative_to(sub).as_posix()}"
                zf.write(path, arcname)
    buf.seek(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = (
        f"{picked[0][0]}.zip"
        if len(picked) == 1
        else f"measurements_{ts}_n{len(picked)}.zip"
    )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Config (config.toml CRUD)
# ---------------------------------------------------------------------------

class ConfigUpdateRequest(BaseModel):
    data: Optional[dict] = None
    text: Optional[str] = None


def _read_config_file() -> tuple[str, dict]:
    if not CONFIG_PATH.exists():
        raise HTTPException(404, f"config.toml 不存在：{CONFIG_PATH}")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(500, f"config.toml 解析失败：{exc}") from exc
    return text, data


CONFIG_BACKUP_KEEP = 20


def _backup_config(reason: str) -> Optional[str]:
    if not CONFIG_PATH.exists():
        return None
    CONFIG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = CONFIG_BACKUP_DIR / f"config_{ts}_{reason}.toml"
    target.write_bytes(CONFIG_PATH.read_bytes())

    # 只保留最新 CONFIG_BACKUP_KEEP 份，旧的自动删掉
    backups = sorted(
        CONFIG_BACKUP_DIR.glob("config_*.toml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[CONFIG_BACKUP_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass

    return str(target.relative_to(PATHS.root))


def _validate_toml_text(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(400, f"TOML 解析失败：{exc}") from exc


@app.get("/api/config")
def get_config() -> dict:
    text, data = _read_config_file()
    return {"text": text, "data": data, "path": str(CONFIG_PATH)}


@app.put("/api/config")
def put_config(req: ConfigUpdateRequest = Body(...)) -> dict:
    if req.text is not None:
        text = req.text
        data = _validate_toml_text(text)
    elif req.data is not None:
        data = req.data
        try:
            text = tomli_w.dumps(_coerce_for_toml(data))
        except Exception as exc:
            raise HTTPException(400, f"TOML 序列化失败：{exc}") from exc
    else:
        raise HTTPException(400, "需要提供 text 或 data 字段")

    backup = _backup_config("save")
    CONFIG_PATH.write_text(text, encoding="utf-8")
    return {"ok": True, "backup": backup, "text": text, "data": data}


@app.get("/api/config/download", response_class=PlainTextResponse)
def download_config() -> PlainTextResponse:
    if not CONFIG_PATH.exists():
        raise HTTPException(404, f"config.toml 不存在：{CONFIG_PATH}")
    return PlainTextResponse(
        CONFIG_PATH.read_text(encoding="utf-8"),
        media_type="application/toml",
        headers={"Content-Disposition": 'attachment; filename="config.toml"'},
    )


def _coerce_for_toml(value: Any) -> Any:
    """递归把 None / NaN / Inf 之类清理掉，避免 tomli_w 报错；list/dict 深拷贝。"""
    if isinstance(value, dict):
        return {k: _coerce_for_toml(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [_coerce_for_toml(v) for v in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"不可序列化的浮点：{value}")
    return value


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(host: str = "127.0.0.1", port: int = 8011) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run()
