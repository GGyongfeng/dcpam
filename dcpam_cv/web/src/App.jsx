import React, { useEffect, useMemo, useState } from "react";

import { SceneView } from "./SceneView.jsx";
import { buildGeometry } from "./geometry.js";
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
  deviceModel: true,
  opticalAxes: true,
  imagePlanes: true,
  reflectionPlanes: true,
  virtualPlanes: true,
  frames: true,
  frontVirtual: true,
  rearVirtual: true,
  realPoints: false,
  laserLines: true,
  labels: true,
};

export function App() {
  const [csvText, setCsvText] = useStoredText(STORAGE_KEYS.csv);
  const [tomlText, setTomlText] = useStoredText(STORAGE_KEYS.toml);
  const [csvName, setCsvName] = useStoredText(STORAGE_KEYS.csvName);
  const [tomlName, setTomlName] = useStoredText(STORAGE_KEYS.tomlName);
  const [selected, setSelected] = useState(new Set());
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const rows = useMemo(
    () => parseCsv(csvText).map(normalizeMeasurementRow).filter((row) => row.name),
    [csvText],
  );
  const geometry = useMemo(() => {
    if (!tomlText) return null;
    try {
      return buildGeometry(parseToml(tomlText));
    } catch {
      return null;
    }
  }, [tomlText]);
  const selectedRows = useMemo(
    () => rows.filter((row) => selected.has(row.name)),
    [rows, selected],
  );

  useEffect(() => {
    setSelected(new Set(rows.map((row) => row.name)));
  }, [csvText, rows.length]);

  const onFile = async (event, setter, nameSetter) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setter(await file.text());
    nameSetter(file.name);
  };
  const setLayer = (key, value) => setLayers((current) => ({ ...current, [key]: value }));
  const setAllLayers = (value) => {
    setLayers(Object.fromEntries(Object.keys(DEFAULT_LAYERS).map((key) => [key, value])));
  };
  const clearCache = () => {
    setCsvText("");
    setTomlText("");
    setCsvName("");
    setTomlName("");
    setSelected(new Set());
  };

  return (
    <main className={`app ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <IconButton
        className="sidebar-toggle"
        icon={sidebarOpen ? "‹" : "›"}
        label={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
        onClick={() => setSidebarOpen((current) => !current)}
      />
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand">
            <h1>DCPAM 3D Viewer</h1>
            <p>文件内容会保存在 Local Storage，下次打开自动恢复。</p>
          </div>
        </div>
        <FileSection
          csvName={csvName}
          tomlName={tomlName}
          onCsv={(event) => onFile(event, setCsvText, setCsvName)}
          onToml={(event) => onFile(event, setTomlText, setTomlName)}
          clearCache={clearCache}
        />
        <section className="section">
          <LayerSection layers={layers} setLayer={setLayer} setAllLayers={setAllLayers} />
        </section>
        <section className="section">
          <div className="section-title-row">
            <h2>样本</h2>
            <div className="sample-tools">
              <button type="button" className="primary" onClick={() => setSelected(new Set(rows.map((row) => row.name)))}>
                <span className="button-icon">✓</span>
                全选
              </button>
              <button type="button" onClick={() => setSelected(new Set())}>
                <span className="button-icon">×</span>
                清空
              </button>
            </div>
          </div>
          <SampleTable rows={rows} selected={selected} setSelected={setSelected} />
          <div className="stats">
            <Stat value={rows.length} label="CSV 行" />
            <Stat value={selectedRows.length} label="已选择" />
            <Stat value={geometry?.planes.length || 0} label="平面" />
            <Stat value={geometry?.frames.length || 0} label="框" />
          </div>
        </section>
      </aside>
      <section className="viewer">
        <SceneView rows={selectedRows} geometry={geometry} layers={layers} />
        {!rows.length && !geometry && <div className="empty">上传 CSV 和 config.toml 后显示 3D 场景</div>}
        <div className="corner-help">
          CAD 视角操作：左键旋转，滚轮缩放，右键平移。上传 config.toml 后会显示光轴、实像面、反射面、虚像面、取景框和相机位。
        </div>
      </section>
    </main>
  );
}

function FileSection({ csvName, tomlName, onCsv, onToml, clearCache }) {
  return (
    <section className="section">
      <div className="section-title-row">
        <h2>文件</h2>
        <IconButton
          className="clear-button"
          icon="×"
          text="清空"
          label="清空上传文件"
          onClick={clearCache}
        />
      </div>
      <div className="file-actions">
        <label className="file-button">
          上传 CSV
          <input type="file" accept=".csv,text/csv" onChange={onCsv} />
        </label>
        <label className="file-button">
          上传配置
          <input type="file" accept=".toml,text/plain" onChange={onToml} />
        </label>
      </div>
      <div className="file-names">
        <span>CSV: {csvName || "未上传"}</span>
        <span>CONFIG: {tomlName || "未上传"}</span>
      </div>
    </section>
  );
}

function LayerSection({ layers, setLayer, setAllLayers }) {
  const items = [
    ["cameras", "相机位置"],
    ["deviceModel", "设备结构"],
    ["opticalAxes", "光轴"],
    ["imagePlanes", "实像面"],
    ["reflectionPlanes", "反射面"],
    ["virtualPlanes", "虚像面"],
    ["frames", "取景框"],
    ["frontVirtual", "前虚像点"],
    ["rearVirtual", "后虚像点"],
    ["realPoints", "实像点"],
    ["laserLines", "激光点连线"],
    ["labels", "标签"],
  ];
  return (
    <div className="layer-panel">
      <div className="section-title-row">
        <h3>图层</h3>
        <div className="sample-tools">
          <button type="button" className="primary" onClick={() => setAllLayers(true)}>
            <span className="button-icon">✓</span>
            全选
          </button>
          <button type="button" onClick={() => setAllLayers(false)}>
            <span className="button-icon">×</span>
            清空
          </button>
        </div>
      </div>
      <div className="checks">
        {items.map(([key, label]) => (
          <label className="check" key={key}>
            <input type="checkbox" checked={layers[key]} onChange={(event) => setLayer(key, event.target.checked)} />
            {label}
          </label>
        ))}
      </div>
    </div>
  );
}

function IconButton({ className = "", icon, text = "", label, onClick }) {
  return (
    <button type="button" className={`icon-button ${className}`} title={label} aria-label={label} onClick={onClick}>
      <span className={text && icon ? "button-icon" : ""}>{icon}</span>
      {text}
    </button>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SampleTable({ rows, selected, setSelected }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>选</th>
            <th>name</th>
            <th>front_u</th>
            <th>rear_u</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(row.name)}
                  onChange={(event) => {
                    const next = new Set(selected);
                    if (event.target.checked) next.add(row.name);
                    else next.delete(row.name);
                    setSelected(next);
                  }}
                />
              </td>
              <td>{row.name}</td>
              <td>{format(row.front_u)}</td>
              <td>{format(row.rear_u)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}
