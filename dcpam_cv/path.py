from pathlib import Path


class DCPAMPaths:
    """~/.dcpam/ 全局路径管理。"""

    def __init__(self, root: Path | None = None):
        self.root = root or Path.home() / ".dcpam"

    @property
    def calibration_file(self) -> Path:
        return self.root / "calibration.toml"

    @property
    def pipeline_file(self) -> Path:
        return self.root / "pipeline.toml"

    @property
    def camera_file(self) -> Path:
        return self.root / "camera.toml"

    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    def capture_dir(self, uid: str) -> Path:
        return self.captures_dir / uid

    def ensure_dirs(self) -> None:
        """首次运行时创建目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.captures_dir.mkdir(exist_ok=True)
