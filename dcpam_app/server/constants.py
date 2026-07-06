"""DCPAM Web 后端：跨模块共享的非路径常量。

所有路径统一由 dcpam.path.DCPAMPaths 提供（PATHS.measurements_dir /
config_file / config_backups_dir 等），不在此处另立路径别名。
"""
from __future__ import annotations

import re

from dcpam.path import DCPAMPaths

PATHS = DCPAMPaths()

CAPTURE_MAX_N = 50
PREVIEW_MAX_SIDE = 800
PREVIEW_QUALITY = 60
CONFIG_BACKUP_KEEP = 20

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
PREVIEW_INTERVAL_S = 0.033  # ~30 fps 上限（实际取决于相机 fps）

