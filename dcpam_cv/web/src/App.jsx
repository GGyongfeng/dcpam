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
  axes: true,
  cameras: true,
  imagePlanes: true,
  reflectionPlanes: true,
  virtualPlanes: true,
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
  const [version, setVersion] = useState("V2");
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
  const versions = useMemo(
    () => [...new Set(rows.map((row) => sampleVersion(row.name)).filter(Boolean))].sort(),
    [rows],
  );
  const filteredRows = useMemo(
    () => version === "all" ? rows : rows.filter((row) => sampleVersion(row.name) === version),
    [rows, version],
  );
  const selectedRows = useMemo(
    () => filteredRows.filter((row) => selected.has(row.name)),
    [filteredRows, selected],
  );

  useEffect(() => {
    if (!rows.length) {
      setSelected(new Set());
      return;
    }
    const nextVersion = versions.includes("V2") ? "V2" : versions[0] || "all";
    setVersion(nextVersion);
    setSelected(new Set(rows.filter((row) => sampleVersion(row.name) === nextVersion).map((row) => row.name)));
  }, [csvText, rows.length, versions.join("|")]);

  const onFile = async (event, setter, nameSetter) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setter(await file.text());
    nameSetter(file.name);
  };
  const setLayer = (key, value) => setLayers((current) => ({ ...current, [key]: value }));
  const clearCache = () => {
    setCsvText("");
    setTomlText("");
    setCsvName("");
    setTomlName("");
    setSelected(new Set());
  };

  return (
    <main className={`app ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => setSidebarOpen((current) => !current)}
      >
        {sidebarOpen ? "收起" : "展开"}
      </button>
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
        />
        <section className="section">
          <h2>样本选择</h2>
          <div className="sample-tools">
            <select value={version} onChange={(event) => setVersion(event.target.value)}>
              <option value="all">全部版本</option>
              {versions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <button type="button" onClick={() => setSelected(new Set(filteredRows.map((row) => row.name)))}>
              全选
            </button>
            <button type="button" onClick={() => setSelected(new Set())}>清空</button>
            <button
              type="button"
              className="primary"
              disabled={!versions.includes("V2")}
              onClick={() => setSelected(new Set(rows.filter((row) => sampleVersion(row.name) === "V2").map((row) => row.name)))}
            >
              V2
            </button>
          </div>
          <LayerSection layers={layers} setLayer={setLayer} />
          <button type="button" className="ghost-button" onClick={clearCache}>清除缓存</button>
        </section>
        <section className="section">
          <h2>样本</h2>
          <SampleTable rows={filteredRows} selected={selected} setSelected={setSelected} />
          <div className="stats">
            <Stat value={rows.length} label="CSV 行" />
            <Stat value={selectedRows.length} label="已选择" />
            <Stat value={geometry?.planes.length || 0} label="平面" />
            <Stat value={geometry?.cameras.length || 0} label="相机" />
          </div>
        </section>
      </aside>
      <section className="viewer">
        <SceneView rows={selectedRows} geometry={geometry} layers={layers} />
        {!rows.length && !geometry && <div className="empty">上传 CSV 和 config.toml 后显示 3D 场景</div>}
        <div className="corner-help">
          CAD 视角操作：左键旋转，滚轮缩放，右键平移。上传 config.toml 后会显示实像面、反射面、虚像面和相机位。
        </div>
        <div className="hud">
          <LegendChip color="var(--green)" label="前虚像点" />
          <LegendChip color="var(--orange)" label="后虚像点" />
          <LegendChip color="var(--blue)" label="实像面" />
          <LegendChip color="var(--purple)" label="反射面" />
          <LegendChip color="var(--cyan)" label="虚像面" />
        </div>
      </section>
    </main>
  );
}

function FileSection({ csvName, tomlName, onCsv, onToml }) {
  return (
    <section className="section">
      <h2>文件</h2>
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

function LayerSection({ layers, setLayer }) {
  const items = [
    ["axes", "右下角坐标系"],
    ["cameras", "相机位置"],
    ["imagePlanes", "实像面"],
    ["reflectionPlanes", "反射面"],
    ["virtualPlanes", "虚像面"],
    ["frontVirtual", "前虚像点"],
    ["rearVirtual", "后虚像点"],
    ["realPoints", "实像点"],
    ["laserLines", "激光点连线"],
    ["labels", "标签"],
  ];
  return (
    <div className="layer-panel">
      <h3>显示图层</h3>
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

function Stat({ value, label }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function LegendChip({ color, label }) {
  return <span className="chip" style={{ "--chip": color }}>{label}</span>;
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

function sampleVersion(name) {
  return name.split("-")[1] || "";
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}
