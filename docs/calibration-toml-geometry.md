# 标定 TOML 几何表达

本文说明 `config.toml` 中标定几何的组织方式。当前原则是：TOML 里尽量保存算法直接使用的几何结果，而不是保存某一种标定工具的原始输出。

## 单位约定

相机内参中的 `focal_lengths` 和 `principal_point` 使用像素单位，`distortion_coeffs` 为无量纲畸变参数。

相机外参、平面点坐标、成像面圆点坐标和设备几何统一使用毫米。旋转矩阵、法向量和四元数本身没有长度单位。

## 平面表达

当前主链路不再保存外部标定工具派生的光学平面。算法直接使用两类几何：

- `calibration.frame_surfaces`：PnP 得到的相机实像面，位于各自相机坐标系。
- 顶层 `geometry`：设备坐标系下的反射面和探测杆。

平面统一使用 `point + normal + d` 表示，其中 `point` 是平面上一点，`normal` 是单位法向量，`d` 满足平面方程：

```text
normal · X + d = 0
```

## 5 圆点 PnP 定位法

`calibration.frame_surfaces` 保存由成像面标定图做 5 圆点 PnP 得到的实像面：

- `front_frame_pnp`：前成像面在前相机坐标系下的平面。
- `rear_frame_pnp`：后成像面在后相机坐标系下的平面。

每个成像面上贴 5 个黑圆点，其在成像面局部坐标系（原点=框中心，自带朝向）下的 3D 坐标由影像仪测出，作为 PnP 的 object points，保存在 `pnp.toml` 的 `front_frame.points` / `rear_frame.points`（顺序：左上, 右上, 中, 左下, 右下）。标定时用 `SimpleBlobDetector` 从相机图提取 5 个圆心像素，与 object points 做 PnP，求解成像面局部系到相机坐标系的刚体位姿：

```text
P_camera = R_frame_to_camera · P_frame + t_frame_to_camera
```

从这个位姿得到两类结果。其一是实像面平面：`point` 等于框中心在相机坐标系中的位置，`normal` 等于 `R_frame_to_camera` 的第三列，`d = -normal · point`，写入 `frame_surfaces.{front,rear}_frame_pnp`。其二是「相机→成像面局部系」的完整刚体变换（旋转矩阵三列即局部系三轴在相机系下的朝向），写入 `calibration.front_camera_to_frame` / `rear_camera_to_frame`。标定入口为 `scripts/pnp/pnp_定位.py`。

## 相机坐标系统一

当前算法主链路在设备坐标系下完成镜像反射、激光线构造与靶点距离计算。设备坐标系定义为前取景框局部系（原点=前框中心）。

前相机系下的实像点通过 `calibration.front_camera_to_frame` 直接搬入前框局部系，即设备系。后相机系下的实像点先通过 `calibration.rear_camera_to_frame` 搬入后框局部系，再经顶层 `geometry.rear_to_front` 的装配变换并入前框系（=设备系）。其中 `rear_to_front` 是后取景框局部系到前取景框局部系的 6DOF 变换，含前后模块约 80mm 的装配平移，由人手动测量填写，标定脚本不写它。

`config.toml` 因此不再保存后相机相对前相机的外参，也不再依赖该外参做坐标统一。

## 设备几何与可视化几何

`geometry` 只保存算法关心的设备坐标系几何，例如反射面和探测杆 `root + length`。这些量用于计算，不追求把实体模型画得完整。

Web 端为了把设备画得更清楚，另有 `dcpam_app/web/src/device_visual.toml` 保存底板、玻璃片厚度、取景框外轮廓、探杆半径等可视化参数。这些参数不属于核心算法配置，用户上传 `config.toml` 时也不需要包含它们。
