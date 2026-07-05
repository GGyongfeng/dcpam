---
标题: 点到激光基准轴距离测量方法综述
用途: 论文 Related Work 章节的原始素材，非最终成稿
生成方式: deep-research 工作流（5 路并行搜索 + 3 票对抗验证）
生成时间: 2026-03-15
---

# 点到激光基准轴距离测量方法综述

## 0. 问题定义

给定空间中一条由激光定义的三维直线（激光基准轴 $\mathcal{L}$）
和一个目标点 $P_T$，如何精确测量 $P_T$ 到 $\mathcal{L}$ 的垂直距离 $H$？

典型精度需求为 $\pm 15\,\mu\mathrm{m}$（理想）到 $\pm 50\,\mu\mathrm{m}$（工程可接受），量程数米到数十米。

这个问题的一个重要来源是大型旋转设备（汽轮机、发电机、压缩机等）的轴线对中：需要测量的物理量正是待对中轴上多个采样点到某条"理想基准轴"的距离。传统钢丝找中法用一根张紧的钢丝作为基准，通过百分表测量轴到钢丝的距离，但钢丝存在下垂与振动敏感的问题。用激光基准线替换钢丝是自然的替代思路，但如何精确测量"空间任意点到激光轴的距离"并没有成熟的通用方案。

**本综述的核心结论**：现有商业方案与学术方法中，没有一个直接解决"空间中任意目标点到激光基准轴的垂直距离 $H$"这个测量问题。它们要么只能读取激光斑落在自身探测器上的位置（PSD 类）、要么需要合作反射器并测的是 3D 坐标（激光跟踪仪）、要么测的是完全不同的物理量（激光三角、激光干涉），要么精度停留在毫米级达不到工程要求（学术双目激光线重建）。这一空白正是本文提出的 DCPAM 方法要填补的位置。

---

## 1. 位置敏感探测器（PSD）与 CMOS/CCD 靶板系工业对中仪

### 1.1 原理

在一根被测轴上装激光发射器、在另一根被测轴上装 PSD 或 CCD 接收器（对中仪的典型形态是"双端 sensALIGN"或"reversed measurement"——两端各装一套发射-接收单元）。激光斑落在探测器感光面上，读取斑点的 $(x, y)$ 坐标；配合旋转轴的多角度旋转数据，反算两根轴之间的偏移（offset）与角度偏差。

### 1.2 代表产品与规格

**Easy-Laser XT770**（Easy-Laser AB，瑞典）
- 探测器：2 轴 TruePSD，$20 \times 20\,\mathrm{mm}$
- 分辨率：$0.001\,\mathrm{mm}$（1 μm）
- 测量精度：$\pm 1\,\mu\mathrm{m} \pm 1\%$
- 量程：达 20 m
- 激光：630–680 nm 二极管激光，$<1\,\mathrm{mW}$，Class 2
- 测量方法：双光束点激光 + 双 2 轴 PSD，reversed measurement method
- 引文：<https://easylaser.com/en-us/products/shaft-alignment/xt770-dot-laser>，
  <https://easylaser.com/Files/Files/Downloads/Broschure/XT770/XT770_brochure_05-0914_rev5.1_eng.pdf>

**Fixturlaser NXA Pro**（Fixturlaser，ACOEM 集团）
- 探测器：30 mm CCD/PSD 感光面（M3 + S3 传感器单元）
- 分辨率：1 μm
- 总体精度：$0.3\%\, \pm 7\,\mu\mathrm{m}$（分销商规格；Finning 官方 spec 表列 $0.2\%\, \pm 7\,\mu\mathrm{m}$）
- 量程：达 10 m
- 输出：shaft-to-shaft offset (μm)、angular misalignment、VertiZontal Moves 校正量
- 引文：<https://www.primeanalyzerstore.com/product/fixturlaser-nxa-pro-shaft-alignment-system/>，
  <https://www.finning.com/content/dam/finning/en_ca/Documents/Products/Rental/PowerSystems/Instrumentation/VibrationLaserAlignment/nxa-pro-specs.pdf>

**Prüftechnik Optalign Touch**（Prüftechnik，Fluke 旗下）
- 传感器：sensALIGN 5，内含两个 HD 大尺寸 PSD + MEMS 倾角仪
- InfiniRange 技术扩展 PSD 靶面有限量程的问题
- 引文：<https://www.primeanalyzerstore.com/product/pruftechnik-optalign-touch-laser-shaft-alignment-system/>

### 1.3 精度补充说明

工业 PSD 主流为 duolateral PSD，全靶面线性度优于 0.1%；位置分辨率经验值优于 0.5 μm；靶板绝对精度经验法则约为传感器直径的 1/500（1 英寸 PSD 对应约 ±50 μm）。厂商标称的 μm 级精度是**激光斑在感光面上的定位精度**或**重复精度**，不是最终测得的轴对中量的绝对精度；在 10 m 量程下 $0.3\%$ 项即为 30 mm，与 μm 级不是同一个物理概念。

### 1.4 相关性判断：**与 $H$ 不相关**

PSD 与 CCD 靶板本质上只能读取激光斑**落在自身感光面上的 $(x, y)$ 坐标**，即"探测器坐标系下的斑点位置"，不是"空间任意目标点到激光轴的距离"。要用 PSD 测某个空间点到激光的距离，只能把 PSD 物理装到该点上——一旦点变了，就得移动 PSD 重装。这与本文要解决的"对空间任意目标点计算 $H$"是不同的语义。此外，PSD 对中仪的最终输出是两根旋转轴的相对偏移与角度，而非"点到轴距离"这个几何量本身。

### 1.5 相比 DCPAM 的优劣

- **优势**：单点精度极高（μm 级探测器读数）；商业化成熟；无需相机标定。
- **局限**：只能测激光斑击中的那一个点；换点要移动传感器；不能对不在光路上的目标点做非接触式距离测量。

---

## 2. 激光跟踪仪 / 全站仪

### 2.1 原理

激光跟踪仪用两个角度编码器（方位角 $\theta$、俯仰角 $\phi$）加上距离测量单元（绝对距离仪 ADM 或干涉仪 IFM），跟踪一个合作反射器（Spherically Mounted Retroreflector, SMR）在空间中的位置，输出 SMR 球心的 3D 坐标 $(X, Y, Z)$。

### 2.2 代表产品

**API Radian**（Automated Precision Inc.）
- 工作量程：达 100 m
- 角度精度：3.5 μm/m（厂商标称）
- IFM 分辨率：$\pm 10\,\mu\mathrm{m}$
- ADM Lock-on 精度：$\pm 10\,\mu\mathrm{m}$ 或 1 ppm
- SMR 光学定心：$\pm 2.5\,\mu\mathrm{m}$
- 引文：<https://apimetrology.com/radian-laser-tracker/>

**Leica Absolute Tracker AT960**（Hexagon）
- 测量球体：直径达 160 m
- AIFM 原理：绝对干涉测距
- 引文：<https://www.exactmetrology.com/metrology-equipment/leica-geosystems/leica-laser-tracker-at960>

（注：验证阶段否决了原始声明的 "0.7 μm/m 精度"；实际最新代规格需查厂家 datasheet。）

### 2.3 相关性判断：**与 $H$ 不相关（但可间接构造）**

激光跟踪仪测的是**合作反射器的 3D 坐标**，不是"点到激光轴的距离"。使用它来得到 $H$ 有两种间接路径：
- **A. 双点重建法**：用 SMR 分别测激光轴上两点得到轴的方程，再用 SMR 测目标点得到其坐标，最后算叉积距离。此时激光跟踪仪的激光根本没有充当基准，而是内部测距载体；"激光基准"只是几何概念，不是物理实体。
- **B. Shoot Line 法**：文献中有把跟踪仪定义的方向作为空间参考线的用法（如 Lockheed Martin 的 SpatialAnalyzer 案例），把该线作为参考、再用 SMR 巡测目标点算距离。但这条参考线也不是激光，是数学定义的。
- 引文：<https://www.kinematics.com/about/newsletterarticlelockheedmartin.php>

两种路径都必须把 SMR 物理放到被测点上——**跟踪仪无法测非合作、无反射器的空间点**。因此当目标点是"设备上某个几何特征位置"而不是可以贴 SMR 的位置时，跟踪仪并不适用；即使可以贴 SMR，测的语义也是"两个 3D 坐标之差在空间轴上的正交分量"，而不是"用一条真实激光作为基准"。

### 2.4 相比 DCPAM 的优劣

- **优势**：3D 定位精度极高（大部分场景下优于 DCPAM 目标）；量程大；技术成熟。
- **局限**：需要合作靶标；单价高（数十万美元级）；不能对非合作点直接测量；跟踪仪本身不是"激光基准 + 目标点"的语义，是"3D 坐标 + 数学基准"。

---

## 3. 双目 / 多目立体视觉重建激光空间直线（学术）

这一类是学术上最接近 DCPAM 思路的方向，也是需要在论文中重点区分的方向。

### 3.1 Point-then-Direction（PtD, Sensors 2021）

- 论文：Guo, Xu, et al., "An Accurate Linear Method for 3D Line Reconstruction for Binocular or Multiple View Stereo Vision," *Sensors* 21(2):658, 2021. DOI 10.3390/s21020658.
- 引文：<https://pmc.ncbi.nlm.nih.gov/articles/PMC7832884/>
- **方法**：先由一对对应点用交会法求线上一点，再最小化图像角度残差（Image Angle Residual, IAR）求线方向；适用于双目与多目。
- **实验精度**：3 相机重建 30 cm 长棋盘格边线，Table 5 良性几何条件下距离误差之和 5.0 mm（PtD），即约 **1.25–1.6 mm/线**——与 DCPAM 目标 15–50 μm 相差 20–100 倍。
- **相关性**：**间接可推 $H$**（重建了三维直线后可以对任意点算叉积距离）；但精度差距证明该问题在文献中并未被解决到工程实用精度。

### 3.2 Xu / Jia 双相机 + 3D 参考板系列

- Xu et al., "Optimization reconstruction of projective point of laser line coordinated by orthogonal reference," *Scientific Reports* 7:15106, 2017.
- 引文：<https://www.nature.com/articles/s41598-017-15399-1>
- Jia et al. (2021), *Scientific Reports*——chained-form system with laser plane + 3D orientation board + internal + external cameras.
- 引文：<https://pmc.ncbi.nlm.nih.gov/articles/PMC7887214/>
- **方法**：以双相机 + 3D 定向板 + 激光面构建 3D 重建管线；重建量是**激光面与被测物表面的交点**，需要物体表面接收激光。
- **精度**：2017 论文的初解绝对误差 1.07 mm，优化后 1.01 mm，相对误差 3.86%。
- **相关性**：**与 $H$ 不相关但读者易混淆**——这两篇论文里激光扮演的是**主动结构光投影平面**的角色，不是可解析的空间基准直线。重建的是"某个位置的 3D 坐标"，不计算"点到激光轴垂直距离"。**Related Work 需显式区分**。

### 3.3 相比 DCPAM 的优劣

DCPAM 与这一类工作的核心不同点有三：
- **激光的角色**：DCPAM 把激光视为**待重建的三维基准直线**，不是结构光投影平面。
- **接收方式**：DCPAM 用**接收屏 + 镜面反射的虚像重建**方法，避免了直接从三维空间中提取"看不见的激光"。
- **精度水平**：DCPAM 目标 15–50 μm，比 PtD/Xu 系列的 1 mm 级高 1–2 个数量级。

---

## 4. 激光三角测距 / 激光位移传感器

### 4.1 原理

激光二极管在传感器内部发射一束聚焦激光打到目标表面，漫反射光通过接收透镜聚焦到线阵 CMOS 或 PSD 上，由已知的基线三角几何算出**传感器到目标表面的距离**。

### 4.2 代表产品

**Keyence LK-G5000**
- 原理：laser triangulation displacement sensor
- 重复精度：0.005 μm（sub-μm 级）
- 线性度：0.02% F.S.
- 采样率：392 kHz
- 引文：<https://www.keyence.com/products/measure/laser-1d/lk-g5000/>

**Micro-Epsilon optoNCDT**
- 原理：laser triangulation
- 量程：2–1000 mm（不同型号）
- 典型应用：非接触位移测量（step、thickness、vibration、displacement）
- 引文：<https://www.micro-epsilon.com/fileadmin/download/products/cat--optoNCDT--en.pdf>，
  <https://www.micro-epsilon.com/wiki/laser-triangulation/>

### 4.3 相关性判断：**与 $H$ 不相关**

激光三角测距测的是"**传感器本体到目标表面的距离**"（单点、沿传感器光轴方向）。激光只是传感器内部的照明光源，不是空间中一条外部基准轴。这与"空间中任意点到外部激光基准的垂直距离"完全不是同一个物理量。

**这一方向在 Related Work 里必须澄清**——不澄清的话，审稿人可能会问"你为什么不直接用 Keyence"，而实际上 Keyence 根本不解决这个问题。

---

## 5. 激光干涉测长

### 5.1 原理

激光干涉仪利用光的干涉条纹计数测量位移；测量对象是**移动的光学部件**（回射镜、Wollaston 棱镜等）相对光路基准的位移或几何误差。

### 5.2 代表产品

**Renishaw XL-80**
- 线性测量精度：$\pm 0.5\,\mathrm{ppm}$（全环境范围）
- 分辨率：1 nm
- 读数速率：50 kHz
- 最大测量速度：4 m/s
- 量程：达 80 m
- 支持模式：linear、angular、straightness、squareness、flatness、rotary
- 引文：<https://www.renishaw.com/en/xl-80-laser-interferometer-system-for-machine-calibration--8268>

官方明示："All measurement options, not limited to linear, rely on interferometric measurements"；"Unlike laser tracker systems, the XL-80 laser interferometer independently measures geometric errors"。straightness 模式用 Wollaston 棱镜分束，测棱镜相对光路的横向偏移——"The measurements are possible ONLY with the WP2 movement"。

### 5.3 相关性判断：**与 $H$ 不相关**

XL-80 无法对不装 Wollaston 棱镜的静态空间点计算 $H$。所有测量模式都必须把移动的光学部件（棱镜或回射镜）物理装在被测运动件上。典型应用是机床、CMM、运动系统的性能校准与几何误差补偿——与"点到激光轴距离"的语义完全不同。

需要澄清的原因与激光三角测距类似：审稿人可能因"激光 + 直线"这几个字误认为竞品，实际上测的是完全不同的量。

---

## 6. 光电准直仪 / 自准直仪 / 光幕对中

### 6.1 自准直仪（Autocollimator）

自准直仪测的是**反射镜的角度变化**（arc-second 级），不是位置。测量方式是激光/准直光射向被测反射镜，反射光在自准直仪内部的分划板上成像，由像的位移反算镜面转角。
- 例：Taylor Hobson Ultra 自准直仪，用于直线度测量时是记录导轨上滑车的角度变化，再积分推出直线度——不是"点到激光轴距离"。
- 引文：<https://www.spectrum-metrology.co.uk/news/high-accuracy-straightness.php>

### 6.2 光幕对中 / 电接触对中（传统方法）

传统钢丝找中法（steel-wire alignment）用电接触方式测量：钢丝接地，触针接指示灯回路，触针轻触钢丝即点亮指示灯，由此确定轴的高度。这本质上就是"测量轴上一点到钢丝这条基准直线的垂直距离"——**它是与 $H$ 语义完全一致的传统方法**，也是本文要替代的传统方法。
- 引文：<https://alfidelfi.com/class%202/1TRAN%20TO%20WEB/AMEN/113-SHAFT%20ALIGNMENT.htm>

### 6.3 相关性判断

- 自准直仪：**与 $H$ 不相关**（测角度不测位置）
- 传统钢丝找中：**直接测 $H$**（正是本文要替代的方法，痛点是下垂与振动敏感）

---

## 7. 其他方向（激光雷达 / 结构光 / 多站法）

- **激光雷达 (LiDAR) / 结构光扫描**：测的是**目标表面点云**，需要被测物体表面漫反射激光；无法把外部一根不可见的激光作为基准来测某点到它的距离。**与 $H$ 不相关**。
- **多站法 (Multilateration)**：用多台跟踪仪或多个已知位置的距离传感器交会定位一个点。可以得到点的 3D 坐标，再间接算到某条已知基准直线的距离。相关性同激光跟踪仪一节，属于"间接可推但需要额外基准的定义"。

这些方向未在本次调研中收集深度可验证数据，排除主要基于测量语义不匹配的原理判断。

---

## 8. 对比总表

| 方法 | 代表产品 / 论文 | 精度 | 量程 | 与 $H$ 的相关性 | 主要局限 |
|---|---|---|---|---|---|
| PSD 轴对中仪 | Easy-Laser XT770、Fixturlaser NXA Pro、Prüftechnik Optalign Touch | 探测器读数 ±1 μm ±1%；对中输出 μm–mm 级 | ≤ 20 m | **不相关**（测激光斑在 PSD/CCD 感光面上的 $(x,y)$；输出 offset+angle） | 只能测激光击中传感器那一个点；无法测空间任意点 |
| 激光跟踪仪 | API Radian、Leica AT960 | 3.5 μm/m 角度、±10 μm ADM、SMR ±2.5 μm | 30–160 m | **不相关**（测 SMR 的 3D 坐标）；**间接可推**（配合 SMR 巡测多点） | 需合作反射器；不能测非合作点；单价高 |
| 双目激光线重建 (PtD) | Sensors 2021 21(2):658 | ~1.25–1.6 mm/线（30 cm 目标） | 数米 | **间接可推**（重建 3D 线后可算距离），但**精度不够** | 精度停留在毫米级，达不到 μm 级工程需求 |
| 双目 + 3D 定向板 + 激光面 (Xu/Jia) | Sci. Rep. 2017 (s41598-017-15399-1)、2021 (PMC7887214) | ~1.01 mm 绝对；相对 3.86% | 数米 | **不相关**（激光是投影平面不是基准轴；重建的是面-物交点） | 语义不匹配；精度约 1 mm |
| 激光三角测距 | Keyence LK-G5000、Micro-Epsilon optoNCDT | 亚 μm 重复精度；0.02% F.S. 线性度 | 几十 mm – 1 m | **不相关**（测传感器→目标表面距离） | 激光是内部光源不是外部基准；测的是位移 |
| 激光干涉 | Renishaw XL-80 | ±0.5 ppm 精度；1 nm 分辨率 | ≤ 80 m | **不相关**（需要移动的回射镜/Wollaston 棱镜；测机床几何误差） | 无法对静态非合作点计算 $H$ |
| 自准直仪 | Taylor Hobson Ultra | arc-second 级角度 | 数米 | **不相关**（测角度不测位置） | 测的是角度 |
| 钢丝找中法 | 传统工装 | mm 级；受下垂与振动限制 | 数米 | **直接测 $H$** | 钢丝下垂、振动敏感、量程受限 |
| **DCPAM（本文）** | 双相机 + 前后接收屏 + 镜面虚像重建 | 目标 ±15–50 μm | 数米 – 数十米 | **直接测 $H$（对任意目标点）** | 依赖 PnP 与镜面装配精度 |

---

## 9. 关键结论（可直接引入论文正文）

1. **在"空间任意点到激光基准轴垂直距离 $H$"这个测量问题上，现有方案存在明显空白**：
   - 语义直接匹配、精度足够的方法：钢丝找中法。但下垂与振动限制其精度与量程。
   - 语义直接匹配、精度不够的方法：学术双目激光线重建。精度停留在 1 mm 级。
   - 语义不完全匹配但精度极高的方法：PSD 对中仪（只测激光击中的那一点）、激光跟踪仪（测 SMR 坐标）。
   - 语义完全不匹配的方法：激光三角、激光干涉、自准直、结构光。
2. **DCPAM 的定位**：用双相机 + 接收屏 + 镜面反射虚像重建的方式，把激光轴变成设备坐标系下**可解析的三维直线**，然后对空间任意目标点算叉积距离——这在文献与商业产品中处于空白位置。
3. **需在 Related Work 中显式澄清**的易混淆方向：激光三角（Keyence 类）、激光干涉（Renishaw XL-80）、结构光双相机（Xu/Jia）。这三类都会被审稿人下意识地认为是竞品，但测的物理量与 $H$ 不同。

---

## 10. 未决问题与调研局限

- **激光跟踪仪具体精度**：验证阶段否决了 "0.7 μm/m" 的具体精度声明，实际 API Radian 当代规格需查厂家最新数据表；"与 $H$ 不直接相关" 的相关性判断仍成立。
- **Fixturlaser NXA Pro 探测器类型**（PSD 还是 CCD）在验证阶段有分歧，此处采用 "CCD/PSD 系" 的中性表述；具体到型号可再查厂商官方规格页确认。
- **未深度调研的方向**：光电准直、激光雷达、结构光扫描、光幕对中、多站法。排除主要基于测量语义不匹配的原理判断，未做深度文献查证。
- **未系统检索的会议**：ICRA / IROS / CVPR / IEEE T-IM 等会议期刊中可能存在的其他双目激光线重建工作。DCPAM 的核心新颖点（双相机 + 镜面反射虚像重建激光轴）尚未在这些渠道充分对标——建议投稿前再补一轮针对性检索。
- **未覆盖的应用场景**：粒子加速器束流轴对中、大型天线基准轴对中、隧道掘进机（TBM）导向等大尺寸场景是否有专门的"激光基准 + 目标点定位"系统——若确认存在，值得作为额外竞品讨论。
- **产品规格时效性**：商业产品页规格属于时效性信息（价格、精度、量程可能随代际更新），论文发表前建议 recheck 主要引用页最新规格。

---

## 附录：主要引文清单

**PSD / CCD 系工业对中仪**
- Easy-Laser XT770 官方产品页：<https://easylaser.com/en-us/products/shaft-alignment/xt770-dot-laser>
- Easy-Laser XT770 官方 brochure：<https://easylaser.com/Files/Files/Downloads/Broschure/XT770/XT770_brochure_05-0914_rev5.1_eng.pdf>
- Fixturlaser NXA Pro：<https://www.primeanalyzerstore.com/product/fixturlaser-nxa-pro-shaft-alignment-system/>
- Prüftechnik Optalign Touch：<https://www.primeanalyzerstore.com/product/pruftechnik-optalign-touch-laser-shaft-alignment-system/>
- PSD 原理综述（Laser Focus World）：<https://www.laserfocusworld.com/detectors-imaging/article/16546909/position-sensing-detectors-fill-photonics-test-and-measurement-needs>

**激光跟踪仪**
- API Radian 产品页：<https://apimetrology.com/radian-laser-tracker/>
- Leica AT960：<https://www.exactmetrology.com/metrology-equipment/leica-geosystems/leica-laser-tracker-at960>
- 跟踪仪工作原理综述：<https://apimetrology.com/how-do-laser-trackers-work/>
- Lockheed Martin SpatialAnalyzer 案例（shoot line 用法）：<https://www.kinematics.com/about/newsletterarticlelockheedmartin.php>

**学术双目激光线重建**
- PtD (Sensors 2021)：<https://pmc.ncbi.nlm.nih.gov/articles/PMC7832884/>
- Xu 2017 (Sci. Rep.)：<https://www.nature.com/articles/s41598-017-15399-1>
- Jia 2021 (Sci. Rep.)：<https://pmc.ncbi.nlm.nih.gov/articles/PMC7887214/>

**激光三角与位移传感器**
- Keyence LK-G5000：<https://www.keyence.com/products/measure/laser-1d/lk-g5000/>
- Micro-Epsilon optoNCDT 产品目录：<https://www.micro-epsilon.com/fileadmin/download/products/cat--optoNCDT--en.pdf>
- Micro-Epsilon 三角测距原理：<https://www.micro-epsilon.com/wiki/laser-triangulation/>

**激光干涉与直线度**
- Renishaw XL-80：<https://www.renishaw.com/en/xl-80-laser-interferometer-system-for-machine-calibration--8268>

**传统对中方法**
- 钢丝找中原理综述：<https://alfidelfi.com/class%202/1TRAN%20TO%20WEB/AMEN/113-SHAFT%20ALIGNMENT.htm>
