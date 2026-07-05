from pathlib import Path


class DCPAMPaths:
    """DCPAM 运行时配置与数据路径管理。

    全局根目录 = ~/.dcpam（跨项目共享，不随代码仓库走）。
    配置文件（config.toml / pnp.toml）与运行数据（data/）都在此根下。
    项目仓库根目录只保留 config.toml / pnp.toml 的**模板**，供首次填写参考。
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path.home() / ".dcpam"

    # ---- 配置文件 ----
    @property
    def config_file(self) -> Path:
        return self.root / "config.toml"

    @property
    def pnp_file(self) -> Path:
        return self.root / "pnp.toml"

    # ---- 运行数据（统一在 root/data 下）----
    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def measurements_dir(self) -> Path:
        return self.data_dir / "measurements"

    @property
    def config_backups_dir(self) -> Path:
        return self.data_dir / "config_backups"

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
        self.data_dir.mkdir(exist_ok=True)
        self.measurements_dir.mkdir(exist_ok=True)
        self.config_backups_dir.mkdir(exist_ok=True)
        self.captures_dir.mkdir(exist_ok=True)
