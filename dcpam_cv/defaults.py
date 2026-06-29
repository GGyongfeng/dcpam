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


_CONFIG_TOML = """[pipeline.spot_extraction]
method = "improved_circle_fit"
gaussian_kernel = 9
gaussian_sigma = 2.0
centroid_threshold = 0.3


[calibration.front_camera]
model = "OPENCV"
focal_lengths = [2990.6987249288663, 2977.3564887249863]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.18636511590856567, 0.07840190379269005, 0.0022669627721650172, -5.4958790543323754e-05]
resolution = [2592, 1944]

[calibration.rear_camera]
model = "OPENCV"
focal_lengths = [3110.5703660675968, 3097.260663052594]
principal_point = [1296.0, 972.0]
distortion_coeffs = [-0.2237547419268369, 0.11599968695378729, -0.0010907287180217534, -0.001286167658601872]
resolution = [2592, 1944]

[calibration.frame_surfaces.front_frame_pnp]
method = "pnp_frame_pose"
point = [-0.31316080434, -0.152703843963, 31.451463126367]
normal = [0.088922969058, -0.030702698215, 0.995565191184]
d = -31.288823131926

[calibration.frame_surfaces.rear_frame_pnp]
method = "pnp_frame_pose"
point = [-0.361361300837, -0.15688045129, 32.154834528736]
normal = [0.006284359507, -0.036468040526, 0.999315059851]
d = -32.136260589924

[calibration.front_camera_to_device]
rotation = [
    [0.9960196618340632, -0.003407355985000216, -0.08906864299600564],
    [0.0061268926789970046, 0.9995227532415113, 0.030277498882985195],
    [0.08892296905795527, -0.03070269821498456, 0.9955651911834993],
]
translation = [3.1127331429861678, -0.7977219704889075, -31.288823131925312]

[calibration.rear_camera_to_device]
rotation = [
    [0.9999749226046896, 0.0034921907789989158, -0.006161068519998088],
    [-0.003265116741000486, 0.9993287180021487, 0.03648907218400543],
    [0.006284359507002429, -0.0364680405260141, 0.9993150598513864],
]
translation = [80.56000823408296, -1.0177048247605276, -32.136260589926536]

[device.geometry.front_reflection]
point = [0.0, 0.0, 23.0]
normal = [0.7071067811865475, 0.0, 0.7071067811865475]

[device.geometry.rear_reflection]
point = [80.0, 0.0, 23.0]
normal = [0.7071067811865475, 0.0, 0.7071067811865475]

[device.geometry.probe_rod]
root = [41.0, 0.0, -132.0]
length_mm = 586.051
"""
