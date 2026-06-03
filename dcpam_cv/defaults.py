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
        return {self.paths.config_file: _CONFIG_TOML}


_CONFIG_TOML = """[camera.front]
serial = ""
exposure_auto = true
gain_auto = true

[camera.rear]
serial = ""
exposure_auto = true
gain_auto = true

[calibration.front_camera]
model = "OPENCV"
focal_lengths = [2990.6987249288663, 2977.3564887249863]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.18636511590856567, 0.07840190379269005, 0.0022669627721650172, -5.4958790543323754e-05]
resolution = [2592, 1944]

[calibration.rear_camera]
model = "OPENCV"
focal_lengths = [3110.5703660675968, 3097.2606630525938]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.22375474192683689, 0.11599968695378729, -0.0010907287180217534, -0.001286167658601872]
resolution = [2592, 1944]

[calibration.transform]
r_rear_from_front = [
    [0.99981958, -0.01442669, -0.01235624],
    [0.01451016, 0.99987232, 0.00669294],
    [0.01225810, -0.00687103, 0.99990126],
]
t_rear_from_front = [-7.86547923, 0.15503238, 0.70268141]
baseline_norm = 7.89832639

[calibration.plane_sources.colmap]
translation_scale = 10.0
image_z_offset_mm = 2.0

[calibration.plane_sources.colmap.poses.front_image_real]
qw = 0.99894211725101356
qx = 0.041629173538092784
qy = 0.0032670746694997057
qz = -0.0192609583277078
tx = 0.089568958305045965
ty = 1.169589814845861
tz = 0.32334314027346434

[calibration.plane_sources.colmap.poses.rear_image_real]
qw = 0.99897717621314275
qx = -0.043336816375192572
qy = 0.007474341138556574
qz = 0.010519314436925029
tx = 0.8404100092877268
ty = 1.1051767421873566
tz = 0.20862615865511441

[calibration.plane_sources.colmap.poses.front_reflection]
qw = 0.97364224661064569
qx = -0.017773449519223234
qy = 0.22349795803090025
qz = 0.041875325230739543
tx = -4.7857560276513356
ty = -0.81876951358304295
tz = 1.5090820639262519

[calibration.plane_sources.colmap.poses.rear_reflection]
qw = 0.96626197672734082
qx = -0.10585653485599716
qy = 0.23332153068748793
qz = 0.026329634955708021
tx = -4.1314707067044427
ty = -0.28809156217078657
tz = 1.1094171744869852

[device.tool]
mount_position = [0.0, 0.0, 0.0]
bar_length = 200.0

[pipeline.spot_extraction]
method = "improved_circle_fit"
gaussian_kernel = 9
gaussian_sigma = 2.0
centroid_threshold = 0.3
"""
