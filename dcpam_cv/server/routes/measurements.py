"""DCPAM Web 后端：拍照采样 + measurements 管理路由。"""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from .. import state
from ...config import SpotExtractionConfig
from ..constants import CAPTURE_MAX_N, MEASUREMENTS_DIR, _NAME_RE
from ..schemas import CaptureRequest, ExportRequest
from ...steps.spot_extraction import extract_spots

router = APIRouter()


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


@router.post("/api/capture")
def capture(req: CaptureRequest = Body(default=CaptureRequest())) -> dict:
    n = max(1, min(CAPTURE_MAX_N, int(req.n)))
    name = _sanitize_name(req.name)
    index = max(1, int(req.index or 1))
    record_id = f"{name}-{index:03d}"

    sample_dir = MEASUREMENTS_DIR / record_id
    if sample_dir.exists():
        raise HTTPException(409, f"采样目录已存在：{record_id}")

    try:
        cam = state._get_camera()
    except Exception as exc:
        raise HTTPException(503, f"相机连接失败:{state._describe(exc)}") from exc

    sample_dir.mkdir(parents=True, exist_ok=True)
    spot_config = SpotExtractionConfig()

    ts = datetime.now()
    t_capture_start = time.perf_counter()

    # 阶段 1：紧凑拍照 —— capture 串行，imwrite 丢线程池不阻塞下一帧。
    pairs: list[tuple[int, np.ndarray, np.ndarray, Path, Path]] = []
    with state._camera_lock, ThreadPoolExecutor(max_workers=4) as executor:
        write_futures = []
        for i in range(n):
            try:
                pair = cam.capture()
            except Exception as exc:
                state._mark_capture_failed(state._describe(exc))
                raise HTTPException(500, f"第 {i + 1} 帧拍照失败：{state._describe(exc)}") from exc

            front_path = sample_dir / f"cam1_{i:03d}.png"
            rear_path = sample_dir / f"cam2_{i:03d}.png"
            write_futures.append(executor.submit(cv2.imwrite, str(front_path), pair.front))
            write_futures.append(executor.submit(cv2.imwrite, str(rear_path), pair.rear))
            pairs.append((i, pair.front, pair.rear, front_path, rear_path))

        for fut in write_futures:
            fut.result()
    state._mark_capture_ok()
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
            extraction_errors.append(f"frame {i}: {state._describe(exc)}")

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


@router.get("/api/measurements")
def list_measurements() -> list[dict]:
    return _load_measurements()


@router.delete("/api/measurements/{record_id}")
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
        raise HTTPException(500, f"删除失败：{state._describe(exc)}") from exc
    return {"ok": True, "id": record_id}


@router.get("/api/measurements/next-index")
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


@router.post("/api/measurements/export-zip")
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
