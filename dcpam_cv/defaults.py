from __future__ import annotations

from pathlib import Path

from .path import DCPAMPaths


class DefaultConfigInitializer:
    """首次运行时创建缺失的本机配置文件。"""

    def __init__(self, paths: DCPAMPaths) -> None:
        self.paths = paths

    def create_missing(self) -> list[Path]:
        """创建缺失配置文件，返回本次创建的路径。"""
        created: list[Path] = []
        for path, content in self._files().items():
            if path.exists():
                continue
            path.write_text(content, encoding="utf-8")
            created.append(path)
        return created

    def _files(self) -> dict[Path, str]:
        return {
            self.paths.camera_file: _CAMERA_TOML,
            self.paths.calibration_file: _CALIBRATION_TOML,
            self.paths.device_file: _DEVICE_TOML,
            self.paths.pipeline_file: _PIPELINE_TOML,
        }


_CAMERA_TOML = """[front]
serial = ""
exposure_auto = true
gain_auto = true

[rear]
serial = ""
exposure_auto = true
gain_auto = true
"""


_CALIBRATION_TOML = """[front_camera]
model = "OPENCV"
focal_lengths = [2990.6987249288663, 2977.3564887249863]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.18636511590856567, 0.07840190379269005, 0.0022669627721650172, -5.4958790543323754e-05]
resolution = [2592, 1944]

[rear_camera]
model = "OPENCV"
focal_lengths = [3110.5703660675968, 3097.2606630525938]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.22375474192683689, 0.11599968695378729, -0.0010907287180217534, -0.001286167658601872]
resolution = [2592, 1944]

[transform]
r_rear_from_front = [
    [0.99981958, -0.01442669, -0.01235624],
    [0.01451016, 0.99987232, 0.00669294],
    [0.01225810, -0.00687103, 0.99990126],
]
t_rear_from_front = [-7.86547923, 0.15503238, 0.70268141]
baseline_norm = 7.89832639

[planes]

[planes.front_image_real]
point = [0.89568958305, 11.6958981485, 5.23343140273]
normal = [0.00492360142167, -0.0832961234852, 0.996512676267]
d = -4.24536777526

[planes.rear_image_real]
point = [8.40410009288, 11.0517674219, 4.08626158655]
normal = [0.014021645213, 0.0867422307864, 0.996132109142]
d = -5.14695064286

[planes.front_reflection]
point = [-47.8575602765, -8.18769513583, 15.0908206393]
normal = [0.433725569982, 0.0533280620017, 0.899465534496]
d = 7.62000847045

[planes.rear_reflection]
point = [-41.314707067, -2.88091562171, 11.0941717449]
normal = [0.445325119069, 0.2168568307, 0.868710914692]
d = 9.38559499095
"""


_DEVICE_TOML = """[tool]
mount_position = [0.0, 0.0, 0.0]
bar_length = 200.0
"""


_PIPELINE_TOML = """[spot_extraction]
method = "improved_circle_fit"
gaussian_kernel = 9
gaussian_sigma = 2.0
centroid_threshold = 0.3
"""
