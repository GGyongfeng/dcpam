# exp/centroid — 圆心提取方法对比记录

光斑圆心提取是 DCPAM 测量重复度（组内 σ）的**决定性杠杆**（见 `exp/README.md`：
旧窗口重心法 → 连通域法，整体 σ 从 216→106μm）。本目录归档提取方法的对比实验。

产品现役方法：`config.toml [pipeline.spot_extraction] method = "improved_circle_fit"`
（= `contour_ellipse`，连通域外轮廓 `fitEllipse` 取椭圆中心，病态时回退几何形心）。
分发实现见 `dcpam/steps/spot_extraction.py::_locate_by_method`。

脚本：
- `gaussian_repeatability.py` — 高斯裙边法逐图提取 + 富标注（三层边界/拟合裙带/圆心）
  + 组内重复性统计。产物写入 `dataset/spot_extraction/_gaussian_analysis/`。
- `method_compare.py` — 三种方法在同一批图上的重复性横向对比。

运行：`uv run python exp/centroid/<脚本>.py`（项目根）。

---

## 实验：两分钟固定采样下三方法重复性对比（2026-07-14）

**数据**：`dataset/spot_extraction/`，激光在同一位置固定约两分钟连续采样。
- group1：sample-199~251（53 组），group2：sample-252~306（55 组）；
- 每组保留中间一对图像 `cam1_002.png` / `cam2_002.png`；
- 激光不动 → 同组不同时刻的圆心理论上应重合，**组内散布 = 该方法的重复性**。

**指标**：径向 RMS = 各图圆心到组内均值中心距离的 RMS（px，越小越稳）。

| 组·相机 | contour_ellipse(现役) | plateau_centroid | gaussian_skirt | σ_v 备注 |
|---|---|---|---|---|
| group1·cam1 | 0.256 | **0.246** | 0.334 | σ_v≫σ_u |
| group1·cam2 | **0.189** | **0.189** | 0.302 | |
| group2·cam1 | 0.507 | **0.424** | 0.537 | σ_v 极大 |
| group2·cam2 | **0.388** | 0.447 | 0.423 | σ_v 极大 |
| **4 组平均** | 0.335 | **0.327** | 0.399 | |

（σ_u/σ_v/max 明细见 `method_compare.py` 输出。）

## 结论

1. **高斯裙边法在本数据上不占优（最差，平均 0.399px）。** 原因：光斑严重饱和，平台
   r≈115px 而可用裙带只有几像素宽，且这薄薄一圈恰是被高斯模糊污染的过渡带——
   信息最少、噪声最大的区域反成唯一拟合依据。**光斑大而饱和时，别用裙边法。**

2. **连通域这一支（contour_ellipse / plateau_centroid）明显更好，二者近乎打平**
   （0.335 vs 0.327，差异 <3%，无实际意义）。原理：饱和平台又大又近正圆、质心极稳，
   直接避开脏裙边。**现役 `improved_circle_fit` 选型合理，无需切换。**

3. **重复性 0.3–0.5px 已是合理结果。** 光斑直径约 230px，0.3–0.5px 仅占直径 ~0.2%，
   亚像素级。

4. **group2 剩余方差主要在竖直方向（σ_v），且三方法都降不下来** → 这是竖直向的物理
   漂移/抖动，非提取方法问题，换算法榨不出来。group1 尚有提取余量，group2 已触到
   测量端物理地板。

**对产品的影响**：无。本实验为离线对比，未改动 `config.toml`；主 pipeline 仍走
`contour_ellipse`，从未使用裙边法。
