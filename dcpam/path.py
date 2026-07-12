from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DCPAMPaths:
    """DCPAM 运行时配置与数据路径管理。

    根目录 = 项目仓库根（dcpam/ 的上一级）。配置文件
    （config.toml / camera.toml / pnp.toml）与运行数据
    （measurements / config_backups / captures / pictures）都平铺在此根下。
    """

    def __init__(self, root: Path | None = None):
        self.root = root or _PROJECT_ROOT

    # ---- 配置文件 ----
    @property
    def config_file(self) -> Path:
        return self.root / "config.toml"

    @property
    def camera_file(self) -> Path:
        return self.root / "camera.toml"

    @property
    def pnp_file(self) -> Path:
        return self.root / "pnp.toml"

    # ---- 运行数据（平铺在 root 下）----
    @property
    def measurements_dir(self) -> Path:
        return self.root / "measurements"

    @property
    def config_backups_dir(self) -> Path:
        return self.root / "config_backups"

    # ---- 单次抓帧调试图 ----
    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    def capture_dir(self, uid: str) -> Path:
        return self.captures_dir / uid

    @property
    def pictures_dir(self) -> Path:
        """scripts/capture_once.py 单次抓帧调试输出。"""
        return self.root / "pictures"

    def ensure_dirs(self) -> None:
        """首次运行时创建目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.measurements_dir.mkdir(exist_ok=True)
        self.config_backups_dir.mkdir(exist_ok=True)
        self.captures_dir.mkdir(exist_ok=True)
