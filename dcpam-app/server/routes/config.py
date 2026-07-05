"""DCPAM Web 后端：config.toml 的增删改查路由。"""
from __future__ import annotations

import tomllib
from datetime import datetime
from typing import Any, Optional

import tomli_w
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import PlainTextResponse

from ..constants import CONFIG_BACKUP_DIR, CONFIG_BACKUP_KEEP, CONFIG_PATH, PATHS
from ..schemas import ConfigUpdateRequest

router = APIRouter()


def _read_config_file() -> tuple[str, dict]:
    if not CONFIG_PATH.exists():
        raise HTTPException(404, f"config.toml 不存在：{CONFIG_PATH}")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(500, f"config.toml 解析失败：{exc}") from exc
    return text, data


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


@router.get("/api/config")
def get_config() -> dict:
    text, data = _read_config_file()
    return {"text": text, "data": data, "path": str(CONFIG_PATH)}


@router.put("/api/config")
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


@router.get("/api/config/download", response_class=PlainTextResponse)
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
