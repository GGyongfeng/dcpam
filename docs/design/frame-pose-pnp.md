# 取景框 PnP 位姿求解

本文记录从取景框图像四边形进一步求解取景框坐标系位姿的算法流程。
这一步承接 `frame-center-localization.md`：前一阶段负责从图片中稳定提取
内层取景框四个角点；当前阶段把这四个像素角点和取景框真实尺寸结合，
求解取景框坐标系到相机坐标系的刚体变换。


## 1. 目标

前、后相机各自都能看到对应取景框。因为取景框固定在设备结构上，
它可以作为设备几何关系和相机坐标系之间的转接坐标系。

当前求解目标是：

```text
front frame coordinate  -> front camera coordinate
rear frame coordinate   -> rear camera coordinate
```

也就是在每个相机自己的坐标系下，恢复对应取景框坐标系的位置和姿态。


## 2. 取景框坐标系定义

当前取景框真实尺寸采用：

```text
width  = 22 mm
height = 17 mm
```

取景框坐标系以矩形中心为原点，坐标轴采用 OpenCV/相机坐标习惯：

```text
X: 指向取景框右侧
Y: 指向取景框下侧
Z: 按右手系垂直于取景框平面，方向与相机正 Z 基本一致
```

四个 3D 点按图像角点顺序排列：

```text
top_left     = [-11, -8.5, 0]
top_right    = [ 11, -8.5, 0]
bottom_right = [ 11,  8.5, 0]
bottom_left  = [-11,  8.5, 0]
```

使用中心作为原点的好处是：PnP 输出的平移向量 `tvec` 直接就是取景框中心
在相机坐标系下的位置。


## 3. PnP 输入

图像点来自上一阶段输出的平均四边形：

```text
dataset/frame/front/rectangle_detection/average_inner_quadrilateral.csv
dataset/frame/rear/rectangle_detection/average_inner_quadrilateral.csv
```

每个 CSV 中保存：

```text
top_left, top_right, bottom_right, bottom_left
```

这些像素点和上面的 3D 点一一对应，然后结合对应相机内参：

```text
front: calibration.front_camera
rear:  calibration.rear_camera
```

调用 OpenCV PnP 求解。


## 4. 求解算法

核心代码位于：

```text
dcpam_cv/steps/frame_pose.py
```

入口类是：

```python
FramePoseEstimator(width_mm=22.0, height_mm=17.0)
```

它执行的数学关系是：

```text
P_camera = R_frame_to_camera @ P_frame + t_frame_to_camera
```

其中：

```text
R_frame_to_camera: 3x3 旋转矩阵
t_frame_to_camera: 3x1 平移向量
```

脚本没有只固定使用某一种 PnP 解法，而是尝试：

```text
SOLVEPNP_IPPE
SOLVEPNP_ITERATIVE
SOLVEPNP_SQPNP
```

然后过滤掉位于相机后方的解，并按四个角点的 RMS 重投影误差选择最优结果。

本次数据中 `SOLVEPNP_ITERATIVE` 明显优于 IPPE。原因可能是当前四个角点来自
圆角矩形边缘直线外推，并不完全等同于真实物理矩形的尖角；同时图像中有厚度、
圆角、边缘模糊和残余畸变影响。因此按重投影误差择优比固定使用某个 flag 更稳。


## 5. 配置写入

脚本位于：

```text
scripts/pnp_定位.py
```

默认执行（传入 frame 目录）：

```bash
uv run python scripts/pnp_定位.py --frame-dir dataset/data-0629/frame
```

它会把结果写入：

```text
config.toml
```

写入位置在 `calibration` 部分：

```toml
[calibration.frame_surfaces.front_frame_pnp]
method = "pnp_frame_pose"
width_mm = 22.0
height_mm = 17.0
point = [...]
x_axis = [...]
y_axis = [...]
normal = [...]
d = ...
corners = [...]
reprojection_error_px = ...

[calibration.frame_surfaces.rear_frame_pnp]
...
```

其中 `point` 是取景框中心在相机坐标系下的位置，`x_axis`、`y_axis` 和
`normal` 分别是取景框坐标系三个轴在相机坐标系下的方向。它们等价于
原始 PnP 位姿中的旋转矩阵三列，只是以更直接的几何形式保存。

如果需要恢复完整 4x4 齐次变换，可以按列拼出旋转矩阵：

```text
R_frame_to_camera = [x_axis, y_axis, normal]
t_frame_to_camera = point
```


## 6. 当前结果

脚本运行时会在 stdout 打印两侧的 PnP 摘要（中心、法向、重投影误差），
具体数值以最新一次写入 `config.toml` 的 `calibration.frame_surfaces` 为准。

当前前相机取景框中心在前相机坐标系下为：

```text
x = -0.3131608043 mm
y = -0.1527038440 mm
z = 31.4514631264 mm
```

取景框法向量在前相机坐标系下为：

```text
[0.0889229691, -0.0307026982, 0.9955651912]
```

当前后相机取景框中心在后相机坐标系下为：

```text
x = -0.3613613008 mm
y = -0.1568804513 mm
z = 32.1548345287 mm
```

取景框法向量在后相机坐标系下为：

```text
[0.0062843595, -0.0364680405, 0.9993150599]
```

重投影 RMS 误差约为：

```text
front: 34.7989 px
rear:  35.1644 px
```

这个误差说明当前结果可以作为第一版设备坐标系锚点，但还不是高精度位姿标定。
后续如果要提高精度，优先方向是：使用更明确的物理角点定义、先对图像去畸变、
对边缘做亚像素拟合，并区分厚度导致的内外两层轮廓。


## 7. 能否把取景框坐标系作为设备坐标系

可以，但需要明确选择一个固定基准。

如果设备几何尺寸都能稳定描述为“相对于取景框中心和取景框轴向”的关系，
那么取景框坐标系就是一个很自然的设备坐标系。建议后续把 **前取景框坐标系**
作为默认设备坐标系：

```text
device coordinate = front frame coordinate
```

原因是当前主测量流程最终会把激光点统一到前相机坐标系，前取景框坐标系
通过 `front_frame_pnp` 可以直接转到前相机坐标系，链路最短。

后取景框坐标系也有用，它可以作为后相机模块的局部设备坐标系。若后续需要把
后取景框坐标系统一到前取景框坐标系，可以通过：

```text
T_front_camera_from_front_frame
T_front_camera_from_rear_camera
T_rear_camera_from_rear_frame
```

组合得到。这里要特别注意已有相机外参方向，避免把 `rear_from_front` 和
`front_from_rear` 用反。


## 8. 后续接入方式

一旦目标点在设备坐标系下的位置确定，例如：

```text
P_target_frame = [x, y, z, 1]
```

如果采用前取景框坐标系作为设备坐标系，则目标点在前相机坐标系中为：

```text
R = [
    calibration.frame_surfaces.front_frame_pnp.x_axis,
    calibration.frame_surfaces.front_frame_pnp.y_axis,
    calibration.frame_surfaces.front_frame_pnp.normal,
]
t = calibration.frame_surfaces.front_frame_pnp.point

P_target_front_camera = R @ P_target_frame + t
```

得到这个点后，就可以继续和已经统一到前相机坐标系的激光线一起计算距离。
