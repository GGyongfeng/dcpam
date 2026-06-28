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
width_mm = 22.0
height_mm = 17.0
point = [-0.31316080434, -0.152703843963, 31.451463126367]
x_axis = [0.996019661834, -0.003407355985, -0.089068642996]
y_axis = [0.006126892679, 0.999522753242, 0.030277498883]
normal = [0.088922969058, -0.030702698215, 0.995565191184]
d = -31.288823131926
corners = [
    [-11.321455672286, -8.611166330681, 32.173859458819],
    [10.590976888063, -8.686128162351, 30.214349312908],
    [10.695134063606, 8.305758642754, 30.729066793915],
    [-11.217298496744, 8.380720474425, 32.688576939825],
]
reprojection_error_px = 34.798883421550414

[calibration.frame_surfaces.rear_frame_pnp]
method = "pnp_frame_pose"
width_mm = 22.0
height_mm = 17.0
point = [-0.361361300837, -0.15688045129, 32.154834528736]
x_axis = [0.999974922605, 0.003492190779, -0.00616106852]
y_axis = [-0.003265116741, 0.999328718002, 0.036489072184]
normal = [0.006284359507, -0.036468040526, 0.999315059851]
d = -32.136260589924
corners = [
    [-11.333331957191, -8.689588652878, 31.912449168891],
    [10.666116340112, -8.61276045574, 31.776905661445],
    [10.610609355518, 8.375827750297, 32.397219888581],
    [-11.388838941785, 8.298999553159, 32.532763396026],
]
reprojection_error_px = 35.1643625650104

[device.geometry.view_frame]
width_mm = 22.0
height_mm = 17.0

[device.geometry.front_frame]
point = [0.0, 0.0, 0.0]
normal = [0.0, 0.0, 1.0]
rect_corners = [
    [-11.0, -8.5, 0.0],
    [11.0, -8.5, 0.0],
    [11.0, 8.5, 0.0],
    [-11.0, 8.5, 0.0],
]

[device.geometry.rear_frame]
point = [80.0, 0.0, 0.0]
normal = [0.0, 0.0, 1.0]
rect_corners = [
    [69.0, -8.5, 0.0],
    [91.0, -8.5, 0.0],
    [91.0, 8.5, 0.0],
    [69.0, 8.5, 0.0],
]

[device.geometry.front_reflection]
point = [0.0, 0.0, 23.0]
normal = [0.7071067811865475, 0.0, 0.7071067811865475]

[device.geometry.rear_reflection]
point = [80.0, 0.0, 23.0]
normal = [0.7071067811865475, 0.0, 0.7071067811865475]

[device.geometry.probe_rod]
root = [41.0, 37.0, -132.0]
length_mm = 109.0
"""
