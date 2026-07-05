# DCPAM-CV 架构概览

本文档简述 `dcpam` 模块的模块划分与数据流，与当前代码实现保持同步。
更深入的算法、标定、约束分析见同目录其它文档。


## 1. 模块划分

```
dcpam/
├── dcpam/
│   ├── path.py                  # 项目根目录路径管理（config.toml、captures/）
│   ├── config.py                # Pydantic 配置模型 + TOML 加载
│   ├── defaults.py              # 首次运行时写入默认 config.toml
│   ├── types.py                 # Point2D / Point3D / SpotPair / LaserAxis / MeasurementResult
│   ├── camera.py                # DualCamera 大恒相机采集
│   ├── optical_geometry.py      # OpticalGeometry：装配实像面 / 反射面 / 靶点
│   ├── pipeline.py              # DCPAMPipeline：5 步设备坐标系测量流程
│   ├── steps/                   # back_project / mirror_transform / point_to_line_distance / extract_spots
│   ├── pnp/                     # 5 圆点 PnP 标定：circles 圆心检测 / pose 通用 PnP / device_convention
│   ├── cli.py                   # dcpam CLI 入口
│   ├── startup.py               # 健康检查
│   ├── server/                  # FastAPI 后端
│   └── web/                     # React/Three.js 3D 查看器
├── scripts/                     # 标定与离线处理脚本
└── config.toml                  # 唯一配置入口
```


## 2. 数据流

### 实时测量（`dcpam` CLI）

```
front.png + rear.png
        │
        ▼
extract_spots            # 圆心提取
        │
        ▼
back_project (×2)        # 反投影到各自成像面 PnP 实像面，得到相机系下的实像点
        │
        ▼
camera_to_device (×2)    # 前点：相机系→前取景框局部系(=设备系)；
                         # 后点：相机系→后取景框局部系，再经 rear_to_front 并入设备系
        │
        ▼
mirror_transform (×2)    # 设备系下分别用前/后反射面镜像得到虚像点
        │
        ▼
point_to_line_distance   # 设备系下计算靶点到激光线距离
        │
        ▼
MeasurementResult
```

整个流程在设备坐标系下闭环，不使用前后相机外参做点的统一。

### 离线批处理

`scripts/00_extract_dataset_centers.py` 扫描 `dataset/L{杆长}D{距离}/` 子目录，
对每张前后相机配对图片提取圆心，写入 `dataset/1-Spot-Center.csv`。

`scripts/20_project_spot_centers.py` 读上面那份 CSV，对每行复用 `OpticalGeometry`
跑同一套 5 步流程，把每个中间量（相机系下实像点、设备系下实像点、虚像点、靶点、激光线、距离）
全部写出到 `dataset/spot-measurements.csv` 供分析或 Web 查看。


## 3. 配置布局

`config.toml` 包含三块顶层 section：

```toml
[pipeline.spot_extraction]      # 光斑提取参数
[calibration.front_camera]      # 前相机内参（OpenCV 模型）
[calibration.rear_camera]       # 后相机内参
[calibration.frame_surfaces.front_frame_pnp]  # 前成像面 PnP 位姿（前相机系下）
[calibration.frame_surfaces.rear_frame_pnp]   # 后成像面 PnP 位姿（后相机系下）
[calibration.front_camera_to_frame]  # 前相机系 → 前取景框局部系（=设备系）
[calibration.rear_camera_to_frame]   # 后相机系 → 后取景框局部系
[geometry.front_reflection]     # 设备坐标系下的前反射面
[geometry.rear_reflection]      # 设备坐标系下的后反射面
[geometry.probe_rod]            # 设备坐标系下的探测杆 root + length
[geometry.rear_to_front]        # 后取景框局部系 → 前取景框局部系(=设备系) 的装配变换
```

历史上还存在 `[calibration.transform]`（C2 相对 C1 外参）与 `[calibration.planes]`
（COLMAP 平面），均已废弃。新链路只依赖 `frame_surfaces`、`camera_to_frame` 与
顶层 `geometry`。


## 4. 相关文档

- `docs/dcpam-core-algorithm.md` — 算法模型脉络与公式
- `docs/calibration-toml-geometry.md` — `config.toml` 几何字段约定
- `docs/camera-plane-constraint-model.md` — C1/C2/P1/P2 约束关系
- `docs/design/pnp-5circles-experiment-log.md` — 5 圆点 PnP 标定实验记录
- `docs/pipeline-comparison-report.html` — 旧外参法 vs 设备坐标系法对比报告（历史归档）
