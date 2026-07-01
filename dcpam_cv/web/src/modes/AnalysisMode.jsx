import React, { useEffect, useMemo, useState } from "react";

import { SceneView } from "../SceneView.jsx";
import { DEFAULT_LAYERS, LayersDrawer } from "../components/LayersDrawer.jsx";
import { ProcessPanel } from "../components/ProcessPanel.jsx";
import { AppShell } from "../layout/AppShell.jsx";
import { buildGeometry } from "../geometry.js";
import { measureRow } from "../pipeline.js";
import { normalizeMeasurementRow, parseCsv } from "../parsers.js";
import { useStoredText } from "../storage.js";

const STORAGE_KEYS = {
  csv: "dcpam.viewer.csvText",
  csvName: "dcpam.viewer.csvName",
};

const DEFAULT_ALGORITHM = {
  imageAlignment: "pnp",
  reflectionSource: "device",
};

const REPO_ROOT = "/Users/guyongfeng/Desktop/dcpam";

export function AnalysisMode({ mode, setMode, mainPanel, setMainPanel, tomlConfig }) {
  const [csvText, setCsvText] = useStoredText(STORAGE_KEYS.csv);
  const [csvName, setCsvName] = useStoredText(STORAGE_KEYS.csvName);
  const [selectedName, setSelectedName] = useState("");
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [filter, setFilter] = useState("");

  const rows = useMemo(
    () => parseCsv(csvText).map(normalizeMeasurementRow).filter((row) => row.name),
    [csvText],
  );
  const geometryState = useMemo(() => {
    if (!tomlConfig) return { error: "", geometry: null };
    try {
      return { error: "", geometry: buildGeometry(tomlConfig, DEFAULT_ALGORITHM) };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error), geometry: null };
    }
  }, [tomlConfig]);
  const geometry = geometryState.geometry;
  const selectedRow = useMemo(
    () => rows.find((row) => row.name === selectedName) || rows[0] || null,
    [rows, selectedName],
  );
  const measurement = useMemo(
    () => measureRow(selectedRow, geometry, tomlConfig),
    [selectedRow, geometry, tomlConfig],
  );

  useEffect(() => {
    if (!rows.length) setSelectedName("");
    else if (!rows.some((row) => row.name === selectedName)) setSelectedName(rows[0].name);
  }, [rows, selectedName]);

  const onCsv = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setCsvText(await file.text());
    setCsvName(file.name);
    event.target.value = "";
  };
  const clearCsv = () => {
    setCsvText("");
    setCsvName("");
    setSelectedName("");
  };

  const filteredRows = filter
    ? rows.filter((row) => row.name.toLowerCase().includes(filter.toLowerCase()))
    : rows;

  const calibration = tomlConfig?.calibration || tomlConfig;
  const resolution = {
    front: calibration?.front_camera?.resolution,
    rear: calibration?.rear_camera?.resolution,
  };
  const images = selectedRow
    ? {
        frontSrc: resolveImageUrl(selectedRow.front_path),
        rearSrc: resolveImageUrl(selectedRow.rear_path),
        frontSpot: measurement?.spots?.front,
        rearSpot: measurement?.spots?.rear,
      }
    : null;
  const steps = calculationSteps(selectedRow, measurement);

  return (
    <AppShell
      mode={mode}
      setMode={setMode}
      mainPanel={mainPanel}
      setMainPanel={setMainPanel}
      brandTitle="DCPAM 分析"
      leftSidebar={
        <LeftSidebar
          csvName={csvName}
          onCsv={onCsv}
          clearCsv={clearCsv}
          rows={filteredRows}
          totalRows={rows.length}
          selectedName={selectedRow?.name || ""}
          setSelectedName={setSelectedName}
          filter={filter}
          setFilter={setFilter}
        />
      }
      sceneSlot={
        <div className="scene-host">
          <SceneView
            rows={selectedRow ? [selectedRow] : []}
            measurement={measurement}
            geometry={geometry}
            layers={layers}
          />
          <LayersDrawer layers={layers} setLayers={setLayers} />
          {geometryState.error && <div className="viewer-error">配置解析失败：{geometryState.error}</div>}
          {!rows.length && !geometry && <div className="empty">上传 CSV 和 config.toml 后显示 3D 场景</div>}
        </div>
      }
      processSlot={
        <ProcessPanel
          title={selectedRow?.name}
          images={images}
          resolution={resolution}
          steps={steps}
        />
      }
    />
  );
}

function LeftSidebar({ csvName, onCsv, clearCsv, rows, totalRows, selectedName, setSelectedName, filter, setFilter }) {
  return (
    <div className="left-stack">
      <section className="section sample-list-section">
        <div className="section-title-row">
          <h3>样本 ({rows.length}{rows.length !== totalRows ? `/${totalRows}` : ""})</h3>
          <div className="csv-actions">
            <label className="csv-upload" title={csvName || "上传 CSV"}>
              {csvName ? "替换 CSV" : "上传 CSV"}
              <input type="file" accept=".csv,text/csv" onChange={onCsv} />
            </label>
            {csvName && (
              <button type="button" className="link-button" onClick={clearCsv}>× 清空</button>
            )}
          </div>
        </div>
        <input
          className="sample-filter"
          type="search"
          placeholder="搜索样本名"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="sample-list">
          {rows.length === 0 ? (
            <div className="sample-empty">{totalRows === 0 ? "尚未上传 CSV" : "无匹配样本"}</div>
          ) : (
            rows.map((row) => (
              <button
                type="button"
                key={row.name}
                className={`sample-item ${row.name === selectedName ? "active" : ""}`}
                onClick={() => setSelectedName(row.name)}
              >
                {row.name}
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}

function formatPoint(point) {
  if (!point) return "(--, --, --)";
  return `(${format(point.x)}, ${format(point.y)}, ${format(point.z)})`;
}

function calculationSteps(row, measurement) {
  if (!row) return [{ title: "等待样本", lines: ["上传 CSV 后选择一个样本"] }];
  if (!measurement) {
    return [{ title: "等待配置", lines: ["请同时加载 config.toml 才能计算后续步骤"] }];
  }
  return [
    {
      title: "1. 提取圆心坐标",
      lines: [
        `前相机圆心：uv=(${format(measurement.spots.front.u)}, ${format(measurement.spots.front.v)})`,
        `后相机圆心：uv=(${format(measurement.spots.rear.u)}, ${format(measurement.spots.rear.v)})`,
      ],
    },
    {
      title: "2. 反投影到 PnP 实像面",
      lines: [
        `前实像点：${formatPoint(measurement.frontRealCamera)}，前相机系 C1`,
        `后实像点：${formatPoint(measurement.rearRealCamera)}，后相机系 C2`,
      ],
    },
    {
      title: "3. 实像点入设备系",
      lines: [
        `前实像点：${formatPoint(measurement.frontReal)}，设备系`,
        `后实像点：${formatPoint(measurement.rearReal)}，设备系`,
      ],
    },
    {
      title: "4. 设备系内镜像反射",
      lines: [
        `前虚像点：${formatPoint(measurement.frontVirtual)}，设备系`,
        `后虚像点：${formatPoint(measurement.rearVirtual)}，设备系`,
      ],
    },
    {
      title: "5. 求解结果",
      lines: [
        `靶点：${formatPoint(measurement.target)}，设备系`,
        `靶点到激光线距离：${format(measurement.distance)} mm`,
      ],
    },
  ];
}

function resolveImageUrl(value) {
  if (!value) return "";
  if (/^(?:https?:|data:|blob:|\/)/.test(value)) return value;
  return `/@fs/${REPO_ROOT}/${value.replace(/^\.\//, "")}`;
}
