# DCPAM 项目全流程文档

> DCPAM: Dual-Camera-Based Point-to-Axis Measurement Model with Laser Reference Line
>
> 基于双相机系统和激光基准线的三维点线距离测量模型

## 1. 项目背景与目标

在电力、船舶、航空等领域，大型旋转设备（汽轮机、发电机、压缩机等）的轴线长度大、安装精度要求高。转动设备的对中精度直接影响机组运行平衡性和使用寿命，是安装调试过程中的关键工序。

目前行业内仍以**钢丝找中法**为主，存在以下问题：
- 钢丝自重下垂引入系统性弯曲误差
- 对气流和机械振动敏感
- 测量范围受钢丝张力和下垂修正精度限制

DCPAM 项目的目标是**用激光基准线替代钢丝**，通过双相机系统重建激光轴线的三维空间位置，计算任意目标点到激光轴线的垂直距离，从而实现非接触式高精度轴线对中测量。

核心算法脉络可参考 [`dcpam-core-algorithm.md`](dcpam-core-algorithm.md)；
基于当前标定数据的坐标统一方案可参考
[`calibrated-coordinate-unification.md`](calibrated-coordinate-unification.md)。

### 精度要求

项目要求测量探头目标点到激光基准线的距离误差在 **±1.5 丝**（±15 μm）以内。
实际工程验收目标为 **±5 丝**（±50 μm）以内。

> 换算关系：1 丝 = 10 μm = 0.01 mm

### 单位规范

系统内所有物理长度统一使用 **mm（毫米）** 作为单位，包括：

- 标定参数（calibration.toml）中的平移向量、基线长度、几何尺寸
- 管线参数（pipeline.toml）中的杆长、安装位置
- 最终输出的测量距离 H

相机内参（焦距、主点）单位为 **px（像素）**，畸变系数和旋转矩阵无量纲。

COLMAP 标定输出的原始尺度约为 cm，
写入 calibration.toml 时需乘以 10 转换为 mm。


## 2. DCPAM 模型总公式

$$h_t = \mathrm{DCPAM}(I_{C_1}, I_{C_2}, l_T)$$

- $h_t$：目标点到激光基准线的距离
- $I_{C_1}$、$I_{C_2}$：分别为相机 C1、C2 采集的图像
- $l_T$：侧杆工装的长度

两种参数调优策略：
- **DCPAM-CV**：经验驱动的传统计算机视觉方法，通过实验→观察→调参的手动循环优化
- **DCPAM-CNN**：基于卷积神经网络的深度学习方法，直接从原始图像回归光斑圆心坐标


## 3. DCPAM-CV 完整计算流程

### 3.1 坐标系定义

| 坐标系 | 说明 |
|--------|------|
| C1 | 相机 1 坐标系，原点在 C1 光心，Z 轴沿光轴方向，右手系 |
| C2 | 相机 2 坐标系，原点在 C2 光心，Z 轴沿光轴方向，右手系 |
| D（设备坐标系） | 定义为 D ≡ C1，即设备坐标系与前相机坐标系重合 |

光心在各自坐标系中的位置为 $(0, 0, 0)^T$（这是坐标系定义决定的，与镜头参数无关）。

### 3.2 关键坐标点定义

| 符号 | 含义 | 所属坐标系 |
|------|------|-----------|
| $P^f_{real}$ | 前相机接收屏上的激光实像点 | C1 |
| $P^f_{virtual}$ | 前虚像面的激光虚像点 | C1 |
| $P^{b\text{-}C2}_{real}$ | 后相机接收屏上的激光实像点 | C2 |
| $P^{b\text{-}C2}_{virtual}$ | 后虚像面的激光虚像点 | C2 |
| $P^b_{virtual}$ | 后虚像点转换到 C1 坐标系后的坐标 | C1 |
| $P_T$ | 目标点 | C1 |

### 3.3 提取光斑圆心像素坐标

激光分别在 C1、C2 相机中成像，提取像素坐标 $(u_1, v_1)$ 和 $(u_2, v_2)$。

对应的齐次像素坐标为：

$$\mathbf{p}_1 = \begin{bmatrix} u_1 \\ v_1 \\ 1 \end{bmatrix}, \quad \mathbf{p}_2 = \begin{bmatrix} u_2 \\ v_2 \\ 1 \end{bmatrix}$$

光斑提取算法（代码 `center.py` 中的实现）：
- 质心法（centroid method）：亮斑区域的质量中心
- 高斯拟合（Gaussian fit）：二维高斯函数拟合
- 改进圆拟合（improved circle fit）：高斯模糊→质心粗定位→Sobel 梯度→Canny 边缘→梯度方向投票→高斯精修

### 3.4 像素坐标 → 相机坐标系

已知相机内参矩阵 $K_1$、$K_2$，以及接收屏到光心的距离 $Z_s$，反投影公式为：

$$P^f_{real} = Z_s \cdot K_1^{-1} \cdot \mathbf{p}_1, \quad P^{b\text{-}C2}_{real} = Z_s \cdot K_2^{-1} \cdot \mathbf{p}_2$$

**依赖项：** 相机标定（内参 $K_1$, $K_2$）；工装几何尺寸（$Z_s$）

**误差来源：** $Z_s$ 依赖探头工装的机械精度

### 3.5 实像点 → 虚像点变换

接收屏安装在可旋转的镜面上。为了重建"展开"的激光路径，需要将实像点旋转到虚像位置。

在 C1 坐标系中，旋转中心为 $R_{O1} = (x_{O1}, 0, z_{O1})^T$，旋转角为 $\theta$（右手系，从 Z 轴到 X 轴逆时针）：

$$P^f_{virtual} = H_1 \cdot P^f_{real}$$

其中 $H_1$ 是 4×4 刚体变换矩阵（绕过 $R_{O1}$ 平行于 Y 轴的旋转轴旋转）：

$$H_1 = \begin{bmatrix} \cos\theta & 0 & \sin\theta & x_{O1}(1-\cos\theta) - z_{O1}\sin\theta \\ 0 & 1 & 0 & 0 \\ -\sin\theta & 0 & \cos\theta & z_{O1}(1-\cos\theta) + x_{O1}\sin\theta \\ 0 & 0 & 0 & 1 \end{bmatrix}$$

同理，后相机的实像点在 C2 坐标系中绕 $R_{O2}$ 旋转 $2\theta$ 得到虚像点：

$$P^{b\text{-}C2}_{virtual} = H_2 \cdot P^{b\text{-}C2}_{real}$$

理想状态下 $z_{O1} = z_{O2} = Z_s$。

### 3.6 C2 坐标系 → C1 坐标系

将 C2 坐标系中的虚像点转换到 C1 坐标系：

$$P^b_{virtual} = T_{C2 \to C1} \cdot P^{b\text{-}C2}_{virtual}$$

其中：

$$T_{C2 \to C1} = E_1 \cdot E_2^{-1}$$

$E_1$、$E_2$ 分别为两个相机基于同一世界坐标系 W 标定的外参矩阵。

等价地，若已知相对位姿 $R_{21}$, $t_{21}$（C1→C2），则：

$$R_{12} = R_{21}^T, \quad t_{12} = -R_{21}^T t_{21}$$

**依赖项：** 双相机外参标定

### 3.7 计算目标点到激光线的距离

在 C1 坐标系中，由 $P^f_{virtual}$、$P^b_{virtual}$、$P_T$ 的空间坐标，用叉积公式求解 $P_T$ 到直线 $P^b_{virtual}P^f_{virtual}$ 的距离：

$$H = \frac{|\vec{L} \times \vec{w}|}{|\vec{L}|}$$

其中：
- $\vec{L} = P^f_{virtual} - P^b_{virtual}$（激光线方向向量）
- $\vec{w} = P_T - P^b_{virtual}$

目标点 $P_T = (x_0, y_0, z_0 + l)^T$，其中 $(x_0, y_0, z_0)$ 是工装安装位置，$l = l_T$ 是侧杆长度。


## 4. 精度分析

### 4.1 端到端矩阵公式

将所有变换组合后，虚像点坐标是像素坐标的仿射函数：

$$x_f = A_1 u_1 + B_1 v_1 + C_1, \quad y_f = D_1 u_1 + E_1 v_1 + F_1, \quad z_f = G_1 u_1 + H_1 v_1 + I_1$$

$$x_b = A_2 u_2 + B_2 v_2 + C_2, \quad y_b = D_2 u_2 + E_2 v_2 + F_2, \quad z_b = G_2 u_2 + H_2 v_2 + I_2$$

系数 $A_1, B_1, \ldots, I_2$ 由复合矩阵乘积确定。

### 4.2 关键结论

当 $l$ 固定、仅像素坐标 $u_1, v_1, u_2, v_2$ 变化（如像素提取噪声引起）时：
- $H$ 的**绝对值**与 $l$ 有关
- $H$ 的**变化量 $\Delta H$** 几乎不依赖 $l$，仅取决于像素噪声和系统系数

### 4.3 误差传播

一阶泰勒展开：

$$\sigma_H^2 \approx \sum_{q \in \{u_1, v_1, u_2, v_2\}} \left(\frac{\partial H}{\partial q}\right)^2 \sigma_q^2$$

### 4.4 Monte Carlo 验证

$N = 10000$ 次采样，每个像素坐标在 $\pm 1\,\mu m$ 范围内均匀扰动，比较经验标准差 $\hat{\sigma}_H$ 与解析值 $\sigma_H$。

### 4.5 灵敏度分析

单参数扰动 $\pm 1\,\mu m$，记录 $|\Delta H|$。各参数的方差贡献：

$$\eta_q = \frac{(\partial H / \partial q)^2 \sigma_q^2}{\sigma_H^2} \times 100\%$$


## 5. 相机标定

### 5.1 内参标定

使用 SIMPLE_RADIAL 模型：焦距 $f$，主点 $(c_x, c_y)$，径向畸变系数 $k$。

内参矩阵：

$$K = \begin{bmatrix} f & 0 & c_x \\ 0 & f & c_y \\ 0 & 0 & 1 \end{bmatrix}$$

使用 COLMAP 的特征提取和 SfM 流程，基于棋盘格图像标定。

当前标定结果：

| 参数 | C1（左） | C2（右） |
|------|---------|---------|
| 分辨率 | 2592×1944 | 2592×1944 |
| 焦距 (px) | 2918.30 | 3757.72 |
| 主点 | (1296, 972) | (1296, 972) |
| 畸变 $k$ | -0.2137 | -0.2384 |

### 5.2 外参标定

双相机标定流程（使用 COLMAP）：
1. 双相机同步拍摄图像对
2. 所有图像同时进行特征提取与匹配
3. 运行 SfM 建图（含去畸变）
4. 导出内参（cameras.txt）和外参（images.txt）
5. 计算相机间相对位姿（预期基线约 7.5-8.0 cm）

### 5.3 Zs 标定

接收屏到光心距离 $Z_s$ 由工装机械尺寸确定，也可通过观测屏幕上已知点直接标定复合矩阵 $Z_s K^{-1}$。

### 5.4 相机倾斜角 α 标定

相机安装时可能存在残余倾斜角 $\alpha$（相机 x 像素方向与水平方向的夹角），需要标定和补偿。


## 6. 镜面变换标定

矩阵 $H_1$、$H_2$ 编码了镜面旋转变换，标定需要：
- 旋转中心位置 $R_{O1}$（或 $R_{O2}$）
- 旋转角度 $\theta$


## 7. DCPAM-CNN（规划中）

用卷积神经网络替代手工 CV 特征提取，直接从原始图像回归光斑圆心坐标。目前代码库中尚未实现。


## 8. 倾斜偏差模型（规划中）

测量探头的倾斜偏差 $\beta$ 会引入系统误差。需要建立 $\beta$ 与测量精度的关系模型，找到倾斜度舍弃阈值 $\beta(\sigma)$：在指定精度 $\sigma$ 下，舍弃倾斜度超过阈值的数据。


## 9. 代码结构

```
dcpam/
├── dcpam_cv/                     # 核心 CV 和精度分析代码
│   ├── __init__.py
│   ├── center.py                 # 光斑圆心提取（质心法/高斯拟合/改进圆拟合）
│   └── precision/
│       ├── __init__.py
│       ├── precision_analysis.py # 核心数学模型（点线距离、误差传播、Monte Carlo、灵敏度分析）
│       └── visualization.py     # 3D 模型、分布直方图、灵敏度图表可视化
├── scripts/
│   └── run_analysis.py          # 交互式精度分析脚本（rich 终端 UI）
├── dual_daheng_capture.py       # 大恒双相机同步采集工具
├── papers/                      # IEEE 论文（按章节拆分的 LaTeX）
│   ├── dcpam.tex                # 主文件
│   ├── IEEEtran.cls
│   └── chapters/                # 各章节 tex 文件
├── docs/                        # 项目文档
├── pictures/                    # 采集图像保存目录
└── reference/                   # 相机标定文件和模板（不纳入版本管理）
```

### 核心类和方法

**`PrecisionAnalyzer`**（`precision_analysis.py`）：
- `point_to_line_distance()`：三维点到直线距离（叉积法）
- `compute_h()`：参数化的距离计算
- `compute_partial_derivatives()`：数值偏导数
- `analytical_error_propagation()`：线性误差传播
- `monte_carlo_simulation()`：Monte Carlo 随机验证（默认 10000 次）
- `sensitivity_analysis()`：单参数扰动灵敏度分析

**`DualDahengController`**（`dual_daheng_capture.py`）：
- `open_two_cameras()`：打开两个大恒相机，设置连续流模式
- `get_current_frames()`：获取同步帧
- `save_pair()`：保存带时间戳的图像对

### 默认分析参数

- 目标点：$(0, 0, -200)$ cm
- 前屏偏移：$(y_f, z_f) = (0.5, 0.5)$ cm
- 后屏偏移：$(y_b, z_b) = (-0.5, -0.5)$ cm
- 前屏 x 坐标：$X_F = +5.0$ cm
- 后屏 x 坐标：$X_B = -5.0$ cm
- 误差范围：1 μm
- Monte Carlo 采样数：10000


## 10. 依赖

- Python 3.13（uv 管理）
- numpy >= 1.20.0
- matplotlib >= 3.3.0
- scipy >= 1.6.0
- rich >= 13.0.0
- opencv-python >= 4.13.0.90
- 大恒 Galaxy SDK + gxipy（厂商提供，不在 uv.lock 中）
