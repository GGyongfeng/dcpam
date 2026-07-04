# PnP 标定改造实验记录：取景框矩形拟合 → 5 圆点 PnP

> 本文完整记录这次把 PnP 标定从"取景框四角矩形拟合"改为"5 圆点 PnP"的
> 全部探索过程：走过的弯路、试过的假设、纠正的错误，以及最终如何定位到真正的
> 根因。目的是留存实验轨迹，方便 review。

日期：2026-07（数据集 `dataset/pnp/20260702.xlsx`）

---

## 1. 背景与动机

旧 PnP 标定从标定图里拟合取景框内层四边形的 4 个角点做 PnP
（`dcpam_cv/pnp/rectangle.py` + `pose.py`）。边缘提取不清晰，重投影误差高达
**20~39px**，是测量精度的一个瓶颈。

新方案：在每个成像面贴 5 个黑圆点，用影像仪测出它们在成像面设备局部坐标系下的
精确 3D 坐标，标定时从相机图提取 5 个圆心像素坐标 ↔ 5 个 3D 点做 PnP，
完全抛弃矩形拟合。

---

## 2. 影像仪数据 → 设备局部坐标（前置转换）

脚本：`scripts/pnp/pnp_影像仪转换.py`，产物 `dataset/pnp/imaging_plane_points_device.csv`。

- xlsx 里每个成像面（按镜编号 `1 号`/`2 号`）测了 5 个圆点 + 取景框四条边框的方向向量。
- 由四条边框方向恢复设备坐标轴：+X 沿上下边框、+Y 沿左右边框、+Z = X × Y（右手系）；
  原点取四条边框直线两两求交得到的矩形中心。
- 变换 `p_device = Rᵀ(P − O)`。

> **关于 +Z 的方向（这里最初版是错的，见 §6）**：叉乘 X × Y 算出的 +Z，
> 方向由影像仪实测向量决定，实际 ≈ 影像仪的 +Z（"Z 轴向上"），即**从圆点面朝外、
> 朝影像仪镜头那一侧**。但设备里相机是**透过成像面从另一侧**拍摄，两个视角对该平面
> 左右镜像——最初版的 +Z 转到相机语境等价于法线指向 −Z（朝相机内部），
> 与设备规格"Z 正 = 远离相机"相反，这正是后面 σ 恶化的真根因。
> **最终版**在 `_device_axes` 里翻 X + 翻 Z（绕 Y 转 180° 保持右手系），使
> **+Z = 远离相机方向**（朝承接屏/激光那一侧），符合设备规格。

验证：圆点离面 RMS ≈ 0.0001~0.0002mm（5 点共面）；四条边求交得到的矩形
非常规整（前 25.02×20.00、后 24.99×20.01mm，四角 90°±0.06°）。

> **顺带纠正的一个配置错误**：`pnp.toml` 里原本写 `[frame] width=22, height=17`，
> 而影像仪实测取景框是 **25×20mm**。旧的矩形拟合 PnP 一直用错误的 22×17 造
> object points（尺度偏小 14%、长宽比也错），是旧方案的一个系统性偏差来源。
> （新方案改用圆点坐标后，这两个尺寸不再参与 PnP。）

---

## 3. 圆心检测：从失败到稳定 54/54

标定图每张用**不同光照**（背光/正光/无光/强光，平均亮度 44~151）重复拍摄，
这是有意为之以增强鲁棒性。检测算法必须对光照不变。

试过并失败的方案：
1. **全局固定阈值找暗斑** → 曝光不足的图白块糊成一团，32 张只稳定检出 17 张。
2. **CLAHE + 自适应阈值** → 反而更差（front 仅 1/32）。
3. **Otsu 分白块 + 块内相对阈值找洞** → 背光图对比度低，Otsu 直接失效（0/32）。

**成功方案**（`dcpam_cv/pnp/circles.py`）：
```
cv2.normalize(im, None, 0, 255, NORM_MINMAX)   # 拉满动态范围，消除光照差异
+ cv2.SimpleBlobDetector(minThreshold=10, maxThreshold=220, thresholdStep=10,
    blobColor=0, minArea=600, maxArea=60000, minCircularity=0.6,
    minConvexity=0.85, minInertiaRatio=0.4, minDistBetweenBlobs=40)
```
结果：**front 32/32、rear 22/22 全部精确检出 5 点**，跨图 std 仅 0.2~0.68px
（证明同一姿态重复拍摄、检测极稳）。

**关键教训**：不要盲调阈值参数；先实际看不同光照的图长什么样，发现"黑圆相对
所在白块总是够暗"这个光照不变量，才找到 normalize + 多阈值扫描这个正解。

---

## 4. 弯路一：front/rear 配对反了（源头数据问题）

首次跑 PnP，reproj 高达 **front 90px / rear 49px**，比旧方案还差。

排查：枚举全部 5!=120 种点对应取 reproj 最小，front 图×front 点最优也才 90px。
用"5 点两两距离比"这个形状不变量对比，发现 **front 图像的点分布 = rear CSV 的点分布**
（反之亦然）。交叉配对验证：

| 配对 | reproj |
|---|---|
| front 图 × front 点 | 90.85px ❌ |
| front 图 × **rear** 点 | **1.61px** ✅ |
| rear 图 × **front** 点 | **1.85px** ✅ |
| rear 图 × rear 点 | 49.51px ❌ |

**根因**：物理安装时 1 号镜装在后、2 号镜装在前，与最初口述相反 → 影像仪表格的
前/后标注反了。用户确认后修正：xlsx 表头改按镜编号，转换脚本映射
**1 号 → rear、2 号 → front**，重新生成 CSV。修正后 front 配 front、rear 配 rear
即得 1.6/1.9px。

---

## 5. 弯路二：reproj 好了，但测量 σ 反而变差（核心谜题）

新标定 reproj 降到 1.5px（好一个数量级），但把 samples 全部重跑 pipeline 后，
**组内重复度 σ 从旧的 174μm 恶化到 469μm**，越远（D200）越差（1000μm+）。

这是整个实验最花时间的部分。逐一排查假设：

### 5.1 被排除的假设
- **法线手性**：孤立地翻 object points 的 X 或 Y，σ 都是 469μm 不变
  → 一度误判"手性无关"（后面证明这个判断本身有坑，见 5.3）。
- **object points 尺度**：5 点最大间距 22/20mm，在 25×20 框内，合理。
- **不是像素问题**：同一批像素、只换 config 就能复现 σ 差异。
- **两成像面间距**：新标定量出精确 80mm、旧的 77.68mm。

### 5.2 两个"看似更准、其实是无效论据"的错误（已纠正）
排查中我两次拿"其实是人为指定的量"当成"标定质量指标"，都是错的：

1. **"新标定间距精确 80mm 所以更准"** ——错。80mm 是
   `pnp.toml` 里 `rear_frame.point=[80,0,0]` **写死的设计约定**，
   `_camera_to_device` 直接拿它去拼，写进去 80、量出来当然 80，
   不能证明标定质量。旧标定量出 77.68mm 只是因为它解出的两成像面法线更不平行、
   投影间距被压缩。

2. **"新标定两法线夹角 0.66°、更平行所以更准"** ——也错。设备坐标系下两成像面
   `normal=[0,0,1]` 是**人为规定**、必然平行，标定不会改它。我实际算的是
   两成像面**在各自相机坐标系下**的法线夹角——那是两个不同相机的安装姿态差，
   与"设备系里平行"是两码事，不能用来论证标定好坏。

   **真正由标定决定、能衡量好坏的只有两类量：reproj 和测量 σ。**

### 5.3 定位真根因：X 轴左右镜像
把关注点收敛到测量 σ 本身，分解虚拟点在设备系的离散：x 恒定、y 抖 3~4mm、
**z 抖 0.2~3.3mm**。算出**组内「虚拟点 z_std」与「距离 σ」相关系数 = 0.944**——
σ 主要由近端虚拟点的 z 抖动、经激光线 ~740mm 杠杆臂放大贡献。

> 这里我一度得出错误结论："这是单姿态标定对 z 角度约束弱的固有敏感度问题。"
> 后来证明是错的——真凶是一个具体 bug，不是固有弱点。

翻查设备规格 `docs/device-physical-spec.md`：
- **Z 正方向 = 远离相机方向**（反射镜 `point=[…,23]`、承接屏都在 +z 侧）。
- 而新标定解出的成像面 **normal.z = −0.9999**，与规格 Z 正方向**相反**。

这提示 object points 的手性有问题。正式实验（改 pnp.toml → 重标定 → 重跑 pipeline，
而非孤立翻点）：

| object points 手性 | normal.z | 平均 σ |
|---|---|---|
| 原始 | −1.0（❌与规格相反） | 469μm |
| 翻 Y | +1.0 | 469μm |
| **翻 X** | **+1.0（✓符合规格）** | **206μm** |

**翻 X 让 σ 从 469 降到 206μm，且 normal.z 变正符合规格。** 翻 Y 虽也让 normal.z=+1
但 σ 没修好——证明**只有翻 X（左右镜像）是物理正确的**。

（注：5.2 里"孤立翻点 σ 都一样"的观察之所以误导，是因为那时没走完整
`_camera_to_device` + 镜像反射链路；正式端到端重标定才暴露出翻 X 与翻 Y 的差别。）

---

## 6. 真根因与修正

**真根因**：从影像仪坐标转换 object points 时，漏了"相机透过成像面从另一侧拍摄
产生的左右镜像"。影像仪从圆点面正上方（Z 向上）测量，相机从另一侧拍摄，两个视角
对面内 X 方向的感知恰好**左右镜像**。X 轴反了导致 PnP 解出的成像面法线指向 −Z
（与设备规格 Z 正相反），进而使镜像反射、虚拟点 z 计算错误，z 噪声经杠杆臂被
异常放大 → σ 恶化。

**修正**（固化到源头 `_device_axes`）：把 X 轴取到相机视角方向（翻 X），
同步翻 Z 保持右手系（等价绕 Y 转 180°）。产出的 CSV / pnp.toml / config 全链路一致。

修正后端到端验证：

| 指标 | 旧方案（矩形拟合） | 新方案（5 圆点，修正后） |
|---|---|---|
| reproj front / rear | 20~39px | **1.49px / 1.80px** |
| 成像面法线 normal.z | +1（符合规格） | **+1（符合规格）** |
| 平均测量 σ | 174μm（混合标定来源） | **206μm** |
| σ 分布 | — | 各组 110~318μm，均匀无爆炸组 |

新方案 reproj 好一个数量级、法线符合规格；σ 与旧方案同级（旧的 174 是"每组配各自
合适标定"的乐观值，新方案是统一标定）。

---

## 7. 关键教训

1. **reproj 低 ≠ 测量精度高**。reproj 是近场 2D 拟合残差，管不到远端 z 杠杆臂放大。
   终极指标永远是测量 σ。
2. **别把人为指定的量当质量指标**。间距 80mm、设备系法线平行都是配置里写死的，
   量出来符合只是"没写错"，不能证明标定准。这个错我犯了两次。
3. **坐标系镜像要显式处理**。影像仪视角 ↔ 相机视角存在左右镜像，转换时必须翻 X，
   否则法线朝向、镜像反射、虚拟点全错。物理规格里"Z 正=远离相机"是校验这一点的
   独立标尺。
4. **端到端验证不可省**。孤立地翻点看 reproj 会漏掉下游镜像链路的差异，
   必须走完整 pipeline 看 σ 才能分辨翻 X 与翻 Y。
5. **光照不变量优于调参**。先看图找到"黑圆相对白块恒暗"这个不变量，
   才有 normalize + 多阈值这个稳定解。

---

## 8. 代码改动清单

| 文件 | 动作 |
|---|---|
| `pnp.toml` | 删 `[frame]`；`[front_frame]/[rear_frame]` 各加 `points`（5×3，翻 X 修正后） |
| `dcpam_cv/pnp/device_convention.py` | 去 `frame_width/height_mm`；`DeviceFrameConvention` 加 `object_points` |
| `dcpam_cv/pnp/pose.py` | `FramePoseEstimator` 改通用 PnP + `estimate_unordered`（120 排列择优对应） |
| `dcpam_cv/pnp/circles.py` | 新增：normalize + SimpleBlobDetector 圆心检测 + 多图平均 |
| `dcpam_cv/pnp/__init__.py` | 移除 rectangle 导出，加 circles 导出 |
| `dcpam_cv/pnp/rectangle.py` | 删除 |
| `scripts/pnp/pnp_影像仪转换.py` | `_device_axes` 加相机视角翻 X（+翻 Z 保右手系）；镜编号映射 1→rear/2→front |
| `scripts/pnp/pnp_定位.py` | 主流程改为 5 圆心检测 → 平均 → 同名配对 PnP → 写 config |

## 9. 复现步骤

```bash
# 1. 影像仪数据 → object points CSV（openpyxl 未入依赖，用 --with 临时装）
uv run --with openpyxl python scripts/pnp/pnp_影像仪转换.py \
    --xlsx dataset/pnp/20260702.xlsx --out dataset/pnp/imaging_plane_points_device.csv

# 2. 重新标定（预期 front 1.49px / rear 1.80px，normal.z≈+1）
uv run python scripts/pnp/pnp_定位.py --frame-dir dataset/pnp --config config.toml --pnp pnp.toml

# 3. 提圆心 → 反投影
uv run python scripts/00_extract_dataset_centers.py --dataset dataset/samples --output dataset/samples/1-Spot-Center.csv
uv run python scripts/20_project_spot_centers.py --input dataset/samples/1-Spot-Center.csv \
    --output dataset/samples/spot-measurements.csv --config config.toml

# 4. 重复度：按样本名前缀分组看 distance_mm 组内 σ（预期平均 ~206μm）
```
