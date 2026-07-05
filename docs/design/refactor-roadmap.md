# DCPAM 重构迭代路线

> 记录 PnP 标定与坐标变换这一轮的完整演进：每一步的动机、改了什么、如何验证。
> 细节见各专项文档链接。目的是让后来者快速看清"为什么现在长这样"。

---

## 演进总览

```
旧: 取景框矩形四角拟合 PnP  →  相机→设备系(80mm 混在标定里)  →  测量
                              ↓ ①               ↓ ②                ↓ ③
新: 5 圆点 PnP            相机→取景框局部系   +  geometry.rear_to_front(6DOF)
```

三步依次解决：**标定精度**（①）、**标定与装配解耦**（②）、**配置语义清晰**（③）。

---

## ① 5 圆点 PnP 替代取景框矩形拟合

**动机**：旧方案从标定图拟合取景框内层四边形的 4 个角点做 PnP，边缘提取不清，
重投影误差高达 20~39px，是精度瓶颈。

**改了什么**：
- 每个成像面贴 5 个黑圆点，用影像仪测出它们在成像面局部坐标系下的 3D 坐标
  （object points，`pnp.toml` 的 `points`；转换脚本 `scripts/pnp/pnp_影像仪转换.py`）。
- 标定时用 `cv2.normalize` + `SimpleBlobDetector` 提取 5 个圆心（对多光照鲁棒，
  实测 54/54 全中），与 object points 做 PnP（排列择优解决点序对应）。
- 新增 `dcpam/pnp/circles.py`；`pose.py` 改为通用 PnP + `estimate_unordered`；
  删除 `rectangle.py`（矩形拟合整套）。

**排查中修正的两个 bug**：
- 取景框尺寸 `22×17` 实为 `25×20`（旧标定一直用错值 → 深度偏近）。
- 影像仪↔相机视角存在**左右镜像**，object points 的 X 轴方向反了 → 成像面法线
  解成 −Z（与设备规格"Z 正=远离相机"相反）、σ 从 174 恶化到 469μm。翻 X（+翻 Z
  保右手系）修正后 σ 回落到 206μm。

**结果**：reproj 20~39px → **1.5px**；姿态跨 32 图 std=0.001；法线朝向符合规格。
公平对照（旧法也用真实 25×20）下新旧 σ 持平（~205μm），而新法几何全面更优。

**验证**：重跑 pipeline，`spot-measurements.csv` 组内 σ；详见
[pnp-5circles-experiment-log.md](./pnp-5circles-experiment-log.md)（含全部弯路与证据）。

---

## ② 80mm 装配尺寸从标定解耦为 rear_to_front

**动机**：旧标定把"相机↔取景框位姿"与"取景框在设备系的位置（前 0 / 后 80mm）"
合并，**80mm 装配尺寸被硬编码进后相机标定变换**。导致前后标定不独立、80mm 写错会
污染标定、装配误差无处安放。

**改了什么**（纯重构，数学等价）：
- 标定只输出「相机→各自取景框局部系」（`front_camera_to_frame` / `rear_camera_to_frame`，
  前后独立，不含装配尺寸）。
- 新增 6DOF 装配变换 `rear_to_front`（rotation+translation，初值 R=I / t=[80,0,0]）：
  后框局部系 → 前框局部系（=设备系）。
- pipeline 在 `optical_geometry.py` 里合成 `rear_to_front ∘ rear_camera_to_frame`，
  合成后仍以 `rear_camera_to_device` 暴露，故调用点零改动。

**收益**：前后标定独立可复用；80mm 错误只影响最后一步、易定位；`rear_to_front` 的
6DOF 正是将来几何自标定要优化的装配误差（安装的平移+旋转偏差）。

**验证**：重跑 pipeline，`spot-measurements.csv` 与重构前**逐字节相同**（等价判据）。

---

## ③ config 扁平化 + rear_to_front 归入 geometry

**动机**：`rear_to_front` 依赖设备物理测量、非相机标定产物，放 `[calibration]` 语义
不对；`[device.geometry]` 两层嵌套多余。

**改了什么**（纯命名/结构调整，数值不变）：
- `rear_to_front` 从 `[calibration]` 移到 `[geometry]`（与 reflection/probe_rod 并列），
  由人手动测量填写，**标定脚本不再写它**。
- 去掉多余的 `device` 层：`[device.geometry.*]` → 顶层 `[geometry.*]`；
  schema 删 `DeviceConfig` 包装类，`AppConfig.device`→`AppConfig.geometry`，
  `DeviceGeometryConfig`→`GeometryConfig`。
- 前端 `geometry.js` / `ConfigForm.jsx` 同步键名。

**结果**：`[calibration]` 只放相机标定产物，`[geometry]` 放全部设备物理几何——
正好对应"几何自标定只优化 geometry 里的量"。

---

## ④ 收尾精简

- `_camera_to_frame` 化简为求逆：5 圆点 object points 自带朝向、原点=框中心，
  camera→frame 就是 PnP 位姿的逆（`R=R_pnpᵀ, t=-R_pnpᵀ@t_pnp`），去掉冗余的
  基构造/平移（15 行→5 行）。
- `pnp.toml` 删除不再参与计算的 `point`/`normal`/`x_axis`，只留 `points`。
- 删除死代码 `dcpam/precision/`、过时文档与产物。

---

## 下一步：几何自标定（未做）

用"最小化组内 σ + 真值约束正则"反求真实几何。**只优化** `geometry` 里的
反射镜（front/rear_reflection）、靶点/杆长（probe_rod）、装配（rear_to_front）——
其余（相机内参、camera_to_frame）不是自标定自由度。已有基础设施
`scripts/30_mirror_sensitivity_mc.py`。陷阱：σ 最小 ≠ 唯一真值（参数可能互相抵消），
需真值约束正则 + 分阶段放开 + 交叉验证。详见 pnp-5circles-experiment-log.md §10。
