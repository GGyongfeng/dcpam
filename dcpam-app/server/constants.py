"""DCPAM Web 后端：跨模块共享的路径与常量。"""
from __future__ import annotations

import re

from dcpam_cv.path import DCPAMPaths

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

CONFIG_BACKUP_KEEP = 20
