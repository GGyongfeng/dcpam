# DCPAM 核心算法整理

本文整理飞书文档《[2601.05] DCPAM:Dual-Camera-Based Point-to-Axis Measurement
Model with Laser Reference Line》的核心内容，用作后续代码实现、精度分析和
标定数据接入的本地算法索引。


## 1. 模型目标

DCPAM 的目标是用激光基准线替代传统钢丝找中法。系统通过前、后两个相机
采集激光在接收屏上的图像，恢复激光在设备坐标系中的空间直线，再计算目标点
到该直线的距离。

整体模型可以写为：

```text
h_t = DCPAM(I_C1, I_C2, l_T)
```

其中 `I_C1`、`I_C2` 是两个相机采集的图像，`l_T` 是侧杆工装长度，
`h_t` 是目标点到激光基准线的距离。


## 2. 两条实现路线

当前核心路线是 `DCPAM-CV`。它通过传统视觉方法提取光斑圆心，再用几何模型
完成反投影、镜像变换、坐标统一和点线距离计算。

规划路线是 `DCPAM-CNN`。它用 CNN 从原始图像直接回归光斑圆心或相关几何量，
用于替代一部分手工 CV 参数调优流程。当前项目实现仍应以 `DCPAM-CV` 为主。


## 3. 坐标系约定

前相机坐标系记为 `C1`，后相机坐标系记为 `C2`。每个相机坐标系的原点位于
对应相机光心，`Z` 轴沿光轴方向，整体为右手坐标系。

设备坐标系 `D` 是算法主坐标系。它的原点定义在前取景框中心，三个轴沿
取景框平面方向和法向布置。前模块与后模块都通过各自取景框的 PnP 位姿与
设备实像面对齐，把相机系下的实像点直接搬到 `D`。后相机到前相机的外参
不参与主链路计算。

相机光心在自身坐标系中恒为 `(0, 0, 0)^T`，这是坐标系定义，不由焦距、
主点或畸变参数计算得到。


## 4. 关键点定义

每个模块在自己的相机系下先得到接收屏上的实像点：

```text
P_f_real_in_C1     前接收屏上的激光实像点
P_b_real_in_C2     后接收屏上的激光实像点
```

随后通过 PnP 取景框-设备实像面对齐变换转入设备坐标系：

```text
P_f_real     = T_C1_to_D * P_f_real_in_C1
P_b_real     = T_C2_to_D * P_b_real_in_C2
```

在设备系下完成镜像反射得到虚像点：

```text
P_f_virtual  = mirror(P_f_real, front_reflection_plane_D)
P_b_virtual  = mirror(P_b_real, rear_reflection_plane_D)
```

目标点 `P_T` 由设备几何中的探测杆 `root + length` 直接给出，同样位于 `D`。
最终激光线由 `P_f_virtual` 与 `P_b_virtual` 两点确定。


## 5. DCPAM-CV 计算流程

第一步，从前、后相机图像中提取光斑圆心像素坐标：

```text
p_1 = [u_1, v_1, 1]^T
p_2 = [u_2, v_2, 1]^T
```

第二步，用相机内参把像素点反投影为相机坐标系下的一条射线，再与对应
取景框 PnP 实像面求交，得到接收屏上的三维实像点：

```text
ray = undistort(K^-1 * p)
P_real_cam = ray ∩ image_plane_cam
```

第三步，用 PnP 取景框位姿与设备实像面的对齐关系把实像点转入设备坐标系：

```text
P_f_real = T_C1_to_D * P_f_real_in_C1
P_b_real = T_C2_to_D * P_b_real_in_C2
```

第四步，在设备坐标系下用各自反射面对实像点做镜像，得到虚像点：

```text
P_f_virtual = mirror(P_f_real, front_reflection_plane_D)
P_b_virtual = mirror(P_b_real, rear_reflection_plane_D)
```

第五步，用前、后两个虚像点确定激光空间直线，并计算目标点到直线的距离：

```text
L = P_f_virtual - P_b_virtual
w = P_T - P_b_virtual
H = norm(L x w) / norm(L)
```


## 6. 精度分析主线

当前实现把两路像素点到虚像点的全过程整理为：

```text
pixel -> undistorted ray -> image plane intersection -> reflection plane mirror
```

在局部小扰动范围内，两个虚像点坐标仍可用于建立像素圆心坐标到最终距离的
误差传播关系：

```text
x_f = A_1 u_1 + B_1 v_1 + C_1
y_f = D_1 u_1 + E_1 v_1 + F_1
z_f = G_1 u_1 + H_1 v_1 + I_1

x_b = A_2 u_2 + B_2 v_2 + C_2
y_b = D_2 u_2 + E_2 v_2 + F_2
z_b = G_2 u_2 + H_2 v_2 + I_2
```

目标点可写为：

```text
P_T = [x_0, y_0, z_0 + l]^T
```

核心观察是：`H` 的绝对值会随侧杆长度 `l` 改变，但当 `l` 固定时，
由 `u_1`、`v_1`、`u_2`、`v_2` 扰动引起的距离变化主要由像素噪声和
复合矩阵系数决定。这条主线可以用于误差传播、Monte Carlo 验证和
灵敏度分析。


## 7. 标定与后续实现关系

当前算法依赖的标定入口有两类。第一类是各相机的内参矩阵 `K`，用于反投影。
第二类是取景框 PnP 位姿与设备坐标系下的设备实像面、反射面、探测杆几何，
用于把相机系下的实像点搬入设备坐标系并完成镜像与距离计算。

当前项目实现按下面这条平面驱动链路理解：

```text
pixel -> 成像面求交 -> 取景框 PnP 对齐 -> 设备系镜像 -> distance
```

历史上曾以"后相机相对前相机外参 T_C2_to_C1"作为坐标统一手段。该外参在
微距标定时无法对同一成像面合焦，可靠性不足；当前主链路不再使用它。


## 8. 相关本地文档

`docs/project-overview.md` 是项目全流程概览，适合快速了解背景、模块和代码结构。

`docs/calibration-toml-geometry.md` 描述 `config.toml` 中标定几何的组织方式，
对应当前 PnP 实像面 + 设备几何反射面的主链路。

`docs/camera-plane-constraint-model.md` 整理 C1/C2/P1/P2 之间的约束关系，
作为后续标定一致性分析的共同语言。

本文则保留 2601.05 文档的核心模型脉络，作为算法分析时的入口。
