from pathlib import Path


class DCPAMPaths:
    """项目本地配置与输出路径管理。"""

    def __init__(self, root: Path | None = None):
        # self.root = root or Path.home() / ".dcpam"
        self.root = root or Path(__file__).resolve().parents[1]

    @property
    def config_file(self) -> Path:
        return self.root / "config.toml"

    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    def capture_dir(self, uid: str) -> Path:
        return self.captures_dir / uid

    def ensure_dirs(self) -> None:
        """首次运行时创建目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.captures_dir.mkdir(exist_ok=True)
