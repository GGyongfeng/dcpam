"""DCPAM Web 后端：请求体的 Pydantic 模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PreviewConfigUpdate(BaseModel):
    """预览参数的运行时可调项。所有字段可选，仅传的字段会被更新。"""
    interval_ms: Optional[int] = None      # 0 ~ 500 ms
    max_side: Optional[int] = None         # 200 ~ 2600 px
    quality: Optional[int] = None          # 1 ~ 100


class CaptureRequest(BaseModel):
    n: int = 10
    name: str = "sample"
    index: int = 1


class ExportRequest(BaseModel):
    ids: list[str]


class GroupAssignRequest(BaseModel):
    ids: list[str]
    group: str = ""          # 空串 = 移出分组（归为未分组）


class GroupCreateRequest(BaseModel):
    name: str


class ConfigUpdateRequest(BaseModel):
    data: Optional[dict] = None
    text: Optional[str] = None
