import React, { useEffect, useMemo, useState } from "react";

import { SceneView } from "./SceneView.jsx";
import { buildGeometry, pointFromRow } from "./geometry.js";
import { normalizeMeasurementRow, parseCsv, parseToml } from "./parsers.js";
import { useStoredText } from "./storage.js";

const STORAGE_KEYS = {
  csv: "dcpam.viewer.csvText",
  toml: "dcpam.viewer.tomlText",
  csvName: "dcpam.viewer.csvName",
  tomlName: "dcpam.viewer.tomlName",
};

const DEFAULT_LAYERS = {
  cameras: true,
  frontViewFrame: true,
  rearViewFrame: true,
  frontFrostedGlass: true,
  rearFrostedGlass: true,
  frontReflectionMirror: true,
  rearReflectionMirror: true,
  basePlate: true,
  probeRod: true,
  opticalAxes: true,
  localAxes: true,
  imagePlanes: true,
  reflectionPlanes: true,
  virtualPlanes: true,
  frontVirtual: true,
  rearVirtual: true,
  realPoints: false,
  laserLines: true,
  labels: true,
};

const LAYER_GROUPS = [
  {
    title: "设备结构",
    groups: [
      {
        title: "器件",
        items: [
          ["frontViewFrame", "前取景框"],
          ["rearViewFrame", "后取景框"],
          ["frontFrostedGlass", "前毛玻璃"],
          ["rearFrostedGlass", "后毛玻璃"],
          ["frontReflectionMirror", "前反射镜"],
          ["rearReflectionMirror", "后反射镜"],
          ["basePlate", "底座"],
          ["probeRod", "测量探杆"],
        ],
      },
    ],
  },
  {
    title: "相机坐标系内容",
    groups: [
      {
        title: "面类",
        items: [
          ["imagePlanes", "实像面"],
          ["reflectionPlanes", "反射面"],
          ["virtualPlanes", "虚像面"],
        ],
      },
      {
        title: "点类",
        items: [
          ["realPoints", "实像点"],
          ["frontVirtual", "前虚像点"],
          ["rearVirtual", "后虚像点"],
          ["laserLines", "激光线"],
        ],
      },
      {
        title: "其他",
        items: [
          ["cameras", "相机位置"],
          ["opticalAxes", "光轴"],
          ["localAxes", "局部坐标系"],
          ["labels", "标签"],
        ],
      },
    ],
  },
];

const DEFAULT_ALGORITHM = {
  imageAlignment: "pnp",
  reflectionSource: "device",
};

export function App() {
  const [csvText, setCsvText] = useStoredText(STORAGE_KEYS.csv);
  const [tomlText, setTomlText] = useStoredText(STORAGE_KEYS.toml);
  const [csvName, setCsvName] = useStoredText(STORAGE_KEYS.csvName);
  const [tomlName, setTomlName] = useStoredText(STORAGE_KEYS.tomlName);
  const [selectedName, setSelectedName] = useState("");
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sampleDrawerOpen, setSampleDrawerOpen] = useState(true);

  const rows = useMemo(
    () => parseCsv(csvText).map(normalizeMeasurementRow).filter((row) => row.name),
    [csvText],
  );
  const geometryState = useMemo(() => {
    if (!tomlText) return { error: "", geometry: null };
    try {
      return { error: "", geometry: buildGeometry(parseToml(tomlText), DEFAULT_ALGORITHM) };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error), geometry: null };
    }
  }, [tomlText]);
  const geometry = geometryState.geometry;
  const selectedRow = useMemo(
    () => rows.find((row) => row.name === selectedName) || rows[0] || null,
    [rows, selectedName],
  );
  const visibleLayers = useMemo(() => ({ ...DEFAULT_LAYERS, ...layers }), [layers]);

  useEffect(() => {
    if (!rows.length) setSelectedName("");
    else if (!rows.some((row) => row.name === selectedName)) setSelectedName(rows[0].name);
  }, [rows, selectedName]);

  const onFile = async (event, setter, nameSetter) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setter(await file.text());
    nameSetter(file.name);
    event.target.value = "";
  };
  const setLayer = (key, value) => setLayers((current) => ({ ...current, [key]: value }));
  const setLayerKeys = (keys, value) => {
    setLayers((current) => ({ ...current, ...Object.fromEntries(keys.map((key) => [key, value])) }));
  };
  const setAllLayers = (value) => {
    setLayers(Object.fromEntries(Object.keys(DEFAULT_LAYERS).map((key) => [key, value])));
  };
  const clearCache = () => {
    setCsvText("");
    setTomlText("");
    setCsvName("");
    setTomlName("");
    setSelectedName("");
  };

  return (
    <main className={`app ${sidebarOpen ? "" : "sidebar-collapsed"} ${sampleDrawerOpen ? "" : "sample-collapsed"}`}>
      <IconButton
        className="sidebar-toggle"
        icon={sidebarOpen ? "‹" : "›"}
        label={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
        onClick={() => setSidebarOpen((current) => !current)}
      />
      <IconButton
        className="sample-toggle"
        icon={sampleDrawerOpen ? "›" : "‹"}
        label={sampleDrawerOpen ? "收起样本栏" : "展开样本栏"}
        onClick={() => setSampleDrawerOpen((current) => !current)}
      />
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand">
            <h1>DCPAM 3D Viewer</h1>
          </div>
          <HeaderActions
            clearCache={clearCache}
            csvName={csvName}
            tomlName={tomlName}
            onCsv={(event) => onFile(event, setCsvText, setCsvName)}
            onToml={(event) => onFile(event, setTomlText, setTomlName)}
          />
        </div>
        <section className="section">
          <LayerSection
            layers={visibleLayers}
            setLayer={setLayer}
            setAllLayers={setAllLayers}
            setLayerKeys={setLayerKeys}
          />
        </section>
      </aside>
      <section className="viewer">
        <SceneView
          rows={selectedRow ? [selectedRow] : []}
          geometry={geometry}
          layers={visibleLayers}
        />
        {geometryState.error && <div className="viewer-error">配置解析失败：{geometryState.error}</div>}
        {!rows.length && !geometry && <div className="empty">上传 CSV 和 config.toml 后显示 3D 场景</div>}
      </section>
      <aside className="sample-drawer">
        <SamplePanel
          geometry={geometry}
          row={selectedRow}
          rows={rows}
          selectedName={selectedRow?.name || ""}
          setSelectedName={setSelectedName}
        />
      </aside>
    </main>
  );
}

function HeaderActions({ clearCache, csvName, onCsv, onToml, tomlName }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  return (
    <div className="header-actions">
      <div className="header-action info-action">
        <button type="button" aria-label="操作说明">i</button>
        <div className="info-card">
          <strong>操作说明</strong>
          <span>左键旋转，滚轮缩放，右键平移。</span>
          <span>文件内容会保存在 Local Storage，下次打开自动恢复。</span>
          <span>上传 config.toml 后会显示 C1/C2、PnP 实像面、设备几何反射面、虚像面和设备结构。</span>
        </div>
      </div>
      <div className="header-action">
        <button type="button" className="settings-button" aria-label="文件设置" onClick={() => setSettingsOpen((value) => !value)}>⚙</button>
        {settingsOpen && (
          <div className="settings-popover">
            <div className="settings-title-row">
              <strong>文件</strong>
              <button type="button" onClick={clearCache}>× 清空</button>
            </div>
            <div className="settings-file-actions">
              <label>
                上传 CSV
                <input type="file" accept=".csv,text/csv" onChange={onCsv} />
              </label>
              <label>
                上传配置
                <input type="file" accept=".toml,text/plain" onChange={onToml} />
              </label>
            </div>
            <div className="file-names settings-file-names">
              <span>CSV: {csvName || "未上传"}</span>
              <span>CONFIG: {tomlName || "未上传"}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SamplePanel({ geometry, row, rows, selectedName, setSelectedName }) {
  const images = imagePaths(row);
  const steps = calculationSteps(row, geometry);
  return (
    <section className="section sample-panel">
      <div className="section-title-row">
        <h2>样本</h2>
      </div>
      <select value={selectedName} onChange={(event) => setSelectedName(event.target.value)}>
        {rows.map((item) => <option value={item.name} key={item.name}>{item.name}</option>)}
      </select>
      <div className="sample-images">
        <SampleImage title="前相机照片" src={images.front} />
        <SampleImage title="后相机照片" src={images.rear} />
      </div>
      <div className="process-list">
        {steps.map((step) => (
          <div className="process-step" key={step.title}>
            <strong>{step.title}</strong>
            <div className="process-lines">
              {step.lines.map((line) => <span key={line}>{line}</span>)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SampleImage({ src, title }) {
  return (
    <figure className="sample-image">
      <div className="image-frame">
        {src ? <img src={src} alt={title} /> : <span>未找到图片路径</span>}
      </div>
      <figcaption>{title}</figcaption>
    </figure>
  );
}

function LayerSection({ layers, setLayer, setAllLayers, setLayerKeys }) {
  return (
    <div className="layer-panel">
      <div className="section-title-row">
        <h3>图层</h3>
        <div className="sample-tools">
          <button type="button" className="primary icon-only-control" title="全部显示" onClick={() => setAllLayers(true)}>✓</button>
          <button type="button" className="icon-only-control" title="全部隐藏" onClick={() => setAllLayers(false)}>×</button>
        </div>
      </div>
      <div className="layer-groups">
        {LAYER_GROUPS.map((section) => (
          <div className="layer-section" key={section.title}>
            <div className="layer-module-title">
              <h4>{section.title}</h4>
              <div className="mini-tools">
                <button type="button" title={`${section.title}全部显示`} onClick={() => setLayerKeys(layerKeys(section), true)}>✓</button>
                <button type="button" title={`${section.title}全部隐藏`} onClick={() => setLayerKeys(layerKeys(section), false)}>×</button>
              </div>
            </div>
            {section.groups.map((group) => (
              <div className="layer-subgroup" key={group.title}>
                <span>{group.title}</span>
                <div className="checks">
                  {group.items.map(([key, label]) => (
                    <label className="check" key={key}>
                      <input
                        type="checkbox"
                        checked={Boolean(layers[key])}
                        onChange={(event) => setLayer(key, event.target.checked)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function layerKeys(section) {
  return section.groups.flatMap((group) => group.items.map(([key]) => key));
}

function IconButton({ className = "", icon, text = "", label, onClick }) {
  return (
    <button type="button" className={`icon-button ${className}`} title={label} aria-label={label} onClick={onClick}>
      <span className={text && icon ? "button-icon" : ""}>{icon}</span>
      {text}
    </button>
  );
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}

function calculationSteps(row, geometry) {
  if (!row) return [{ title: "等待样本", lines: ["上传 CSV 后选择一个样本"] }];
  const frontRealCam = pointFromRow(row, "front_real", "cf");
  const rearRealCam = pointFromRow(row, "rear_real", "cr");
  const frontReal = pointFromRow(row, "front_real", "device");
  const rearReal = pointFromRow(row, "rear_real", "device");
  const frontVirtual = pointFromRow(row, "front_virtual", "device") || pointFromRow(row, "front_virtual", "cf");
  const rearVirtual = pointFromRow(row, "rear_virtual", "device") || pointFromRow(row, "rear_virtual", "cf");
  const target = pointFromRow(row, "target", "device") || probeTargetInDevice(geometry);
  const distance = Number.isFinite(Number(row.distance_mm))
    ? Number(row.distance_mm)
    : distanceToLine(target, frontVirtual, rearVirtual);
  return [
    {
      title: "1. 提取圆心坐标",
      lines: [
        `前相机圆心：uv=(${format(row.front_u)}, ${format(row.front_v)})`,
        `后相机圆心：uv=(${format(row.rear_u)}, ${format(row.rear_v)})`,
      ],
    },
    {
      title: "2. 反投影到 PnP 实像面",
      lines: [
        `前实像点：${formatPoint(frontRealCam)}，前相机系 C1`,
        `后实像点：${formatPoint(rearRealCam)}，后相机系 C2`,
      ],
    },
    {
      title: "3. 实像点入设备系",
      lines: [
        `前实像点：${formatPoint(frontReal)}，设备系`,
        `后实像点：${formatPoint(rearReal)}，设备系`,
      ],
    },
    {
      title: "4. 设备系内镜像反射",
      lines: [
        `前虚像点：${formatPoint(frontVirtual)}，设备系`,
        `后虚像点：${formatPoint(rearVirtual)}，设备系`,
      ],
    },
    {
      title: "5. 求解结果",
      lines: [
        `靶点：${formatPoint(target)}，设备系`,
        `靶点到激光线距离：${format(distance)} mm`,
      ],
    },
  ];
}

function imagePaths(row) {
  if (!row) return { front: "", rear: "" };
  const match = row.name.match(/^L109D(\d+)-V(\d+)-(\d+)$/i);
  if (!match) return { front: row.front_path || "", rear: row.rear_path || "" };
  const folder = `L109D${match[1]}${match[2] === "1" ? "" : "-v2"}`;
  const index = Number(match[3]);
  const base = "/@fs/Users/guyongfeng/Desktop/dcpam/reference/archive/dataset";
  return {
    front: row.front_path || `${base}/${folder}/front/${index}.bmp`,
    rear: row.rear_path || `${base}/${folder}/rear/${index}.bmp`,
  };
}

function probeTargetInDevice(geometry) {
  const target = geometry?.device?.probeRod?.target;
  if (!target) return null;
  return { x: target.x, y: target.y, z: target.z, space: "device" };
}

function distanceToLine(point, first, second) {
  if (!point || !first || !second) return NaN;
  const line = subtract(second, first);
  const offset = subtract(point, first);
  const cross = {
    x: line.y * offset.z - line.z * offset.y,
    y: line.z * offset.x - line.x * offset.z,
    z: line.x * offset.y - line.y * offset.x,
  };
  const lineLength = Math.hypot(line.x, line.y, line.z);
  return lineLength > 1e-9 ? Math.hypot(cross.x, cross.y, cross.z) / lineLength : NaN;
}

function subtract(first, second) {
  return { x: first.x - second.x, y: first.y - second.y, z: first.z - second.z };
}

function toPointObject(point) {
  if (Array.isArray(point)) return { x: point[0], y: point[1], z: point[2] };
  return point;
}

function formatPoint(point) {
  if (!point) return "(--, --, --)";
  return `(${format(point.x)}, ${format(point.y)}, ${format(point.z)})`;
}
