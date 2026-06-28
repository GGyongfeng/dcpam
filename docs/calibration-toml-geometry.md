# 标定 TOML 几何表达

本文说明 `config.toml` 中标定几何的组织方式。当前原则是：TOML 里尽量保存算法直接使用的几何结果，而不是保存某一种标定工具的原始输出。

## 单位约定

相机内参中的 `focal_lengths` 和 `principal_point` 使用像素单位，`distortion_coeffs` 为无量纲畸变参数。

相机外参、平面点坐标、取景框角点和设备几何统一使用毫米。旋转矩阵、法向量和四元数本身没有长度单位。

## 平面表达

当前主链路不再保存外部标定工具派生的光学平面。算法直接使用两类几何：

- `calibration.frame_surfaces`：PnP 得到的相机实像面，位于各自相机坐标系。
- `device.geometry`：设备坐标系下的设备实像面、反射面和探测杆。

平面统一使用 `point + normal + d` 表示，其中 `point` 是平面上一点，`normal` 是单位法向量，`d` 满足平面方程：

```text
normal · X + d = 0
```

## PnP 目标定位法

`calibration.frame_surfaces` 保存由取景框图像 PnP 目标定位得到的结果：

- `front_frame_pnp`：前取景框在前相机坐标系下的平面与角点。
- `rear_frame_pnp`：后取景框在后相机坐标系下的平面与角点。

PnP 的目标点定义在取景框坐标系中，取景框中心为原点，矩形尺寸为 `22 mm x 17 mm`，四个局部角点为：

```text
(-11, -8.5, 0)
( 11, -8.5, 0)
( 11,  8.5, 0)
(-11,  8.5, 0)
```

PnP 求解的是取景框坐标系到相机坐标系的刚体位姿：

```text
P_camera = R_frame_to_camera · P_frame + t_frame_to_camera
```

从这个位姿可以得到三类结果。第一类是取景框平面：`point` 等于取景框中心在相机坐标系中的位置，`normal` 等于 `R_frame_to_camera` 的第三列。第二类是取景框自身坐标轴：`x_axis`、`y_axis` 和 `normal` 分别对应旋转矩阵三列，可以恢复完整姿态。第三类是四个角点：把局部四角点分别通过上面的刚体变换映射到相机坐标系。

当前算法把这个 PnP 结果视为相机坐标系下的实像面。随后将 PnP 实像面与设备坐标系中的设备实像面对齐，从而得到设备坐标系到相机坐标系的变换。

## 相机坐标系统一

当前算法主链路在设备坐标系下完成镜像反射、激光线构造与靶点距离计算。
前、后相机系下的实像点分别通过 `frame_surfaces.front_frame_pnp` 与
`frame_surfaces.rear_frame_pnp` 的 PnP 位姿、与 `device.geometry` 中
对应的设备实像面对齐，搬入设备坐标系。`config.toml` 因此不再保存后相机
相对前相机的外参，也不再依赖该外参做坐标统一。

## 设备几何与可视化几何

`device.geometry` 只保存算法关心的设备坐标系几何，例如设备实像面、反射面和探测杆 `root + length`。这些量用于计算，不追求把实体模型画得完整。

Web 端为了把设备画得更清楚，另有 `dcpam_cv/web/src/device_visual.toml` 保存底板、玻璃片厚度、取景框外轮廓、探杆半径等可视化参数。这些参数不属于核心算法配置，用户上传 `config.toml` 时也不需要包含它们。
