import React, { useCallback, useEffect, useMemo, useState } from "react";

import { SceneView } from "../SceneView.jsx";
import { DEFAULT_LAYERS, LayersDrawer } from "../components/LayersDrawer.jsx";
import { ProcessPanel } from "../components/ProcessPanel.jsx";
import { SamplingHistory } from "../components/SamplingHistory.jsx";
import { AppShell } from "../layout/AppShell.jsx";
import { buildGeometry } from "../geometry.js";
import { measureRow, aggregateDistance } from "../pipeline.js";

const DEFAULT_ALGORITHM = {
  imageAlignment: "pnp",
  reflectionSource: "device",
};

const REPO_ROOT = "/Users/guyongfeng/Desktop/dcpam";

export function AnalysisMode({ mode, setMode, mainPanel, setMainPanel, tomlConfig }) {
  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState("");
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exportSelection, setExportSelection] = useState(() => new Set());
  const [exporting, setExporting] = useState(false);
  const [listStatus, setListStatus] = useState({ kind: "idle", text: "" });
  const [groups, setGroups] = useState([]);

  const refreshGroups = useCallback(async () => {
    try {
      const response = await fetch("/api/measurements/groups");
      if (!response.ok) return;
      const data = await response.json();
      setGroups(Array.isArray(data?.groups) ? data.groups : []);
    } catch (_) {
      // 组列表拉取失败不阻塞主流程，静默处理
    }
  }, []);

  const refreshRecords = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/measurements");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setRecords(Array.isArray(data) ? data : []);
      setError("");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleExportSelection = useCallback((id) => {
    setExportSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setAllExportSelection = useCallback((ids) => {
    setExportSelection(new Set(ids));
  }, []);

  const handleExportZip = useCallback(async () => {
    if (exporting) return;
    const ids = [...exportSelection];
    if (!ids.length) {
      setListStatus({ kind: "error", text: "请先勾选要导出的采样" });
      return;
    }
    setExporting(true);
    setListStatus({ kind: "info", text: `正在打包 ${ids.length} 个采样...` });
    try {
      const response = await fetch("/api/measurements/export-zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload?.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const disposition = response.headers.get("Content-Disposition") || "";
      const nameMatch = disposition.match(/filename="?([^";]+)"?/i);
      const filename = nameMatch ? nameMatch[1] : `measurements_${ids.length}.zip`;
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setListStatus({ kind: "ok", text: `已导出 ${ids.length} 个采样：${filename}` });
    } catch (err) {
      setListStatus({ kind: "error", text: `导出失败：${err.message}` });
    } finally {
      setExporting(false);
    }
  }, [exportSelection, exporting]);

  const handleDeleteRecords = useCallback(async (idsToDelete, { silent } = {}) => {
    const ids = [...new Set(idsToDelete || [])].filter(Boolean);
    if (!ids.length) return;
    if (!silent) {
      const label = ids.length === 1 ? ids[0] : `${ids.length} 个采样`;
      const confirmed = window.confirm(`确认删除 ${label} 吗？此操作不可撤销。`);
      if (!confirmed) return;
    }
    setListStatus({ kind: "info", text: `正在删除 ${ids.length} 个采样...` });
    const failed = [];
    for (const id of ids) {
      try {
        const response = await fetch(`/api/measurements/${encodeURIComponent(id)}`, {
          method: "DELETE",
        });
        if (!response.ok) {
          let detail = `HTTP ${response.status}`;
          try {
            const payload = await response.json();
            detail = payload?.detail || detail;
          } catch (_) {}
          failed.push(`${id}:${detail}`);
        }
      } catch (err) {
        failed.push(`${id}:${err.message}`);
      }
    }
    setRecords((current) => current.filter((r) => !ids.includes(r.id)));
    setExportSelection((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
    setSelectedId((current) => (ids.includes(current) ? "" : current));
    if (failed.length) {
      setListStatus({ kind: "error", text: `删除失败：${failed.slice(0, 3).join("; ")}` });
    } else {
      setListStatus({ kind: "ok", text: `已删除 ${ids.length} 个采样` });
    }
    refreshRecords();
  }, [refreshRecords]);

  const handleAssignGroup = useCallback(async (ids, group) => {
    const targetIds = [...new Set(ids || [])].filter(Boolean);
    if (!targetIds.length) return;
    const label = group ? `「${group}」` : "未分组";
    setListStatus({ kind: "info", text: `正在把 ${targetIds.length} 个采样归入${label}...` });
    try {
      const response = await fetch("/api/measurements/group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: targetIds, group }),
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload?.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const payload = await response.json().catch(() => null);
      const updated = payload?.updated?.length ?? targetIds.length;
      setListStatus({ kind: "ok", text: `已把 ${updated} 个采样归入${label}` });
    } catch (err) {
      setListStatus({ kind: "error", text: `分组失败：${err.message}` });
    }
    refreshRecords();
    refreshGroups();
  }, [refreshRecords, refreshGroups]);

  const handleCreateGroup = useCallback(async (name) => {
    const groupName = (name || "").trim();
    if (!groupName) return;
    setListStatus({ kind: "info", text: `正在新建分组「${groupName}」...` });
    try {
      const response = await fetch("/api/measurements/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: groupName }),
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload?.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      setListStatus({ kind: "ok", text: `已新建分组「${groupName}」，把勾选的采样拖进去即可` });
    } catch (err) {
      setListStatus({ kind: "error", text: `新建分组失败：${err.message}` });
    }
    refreshGroups();
  }, [refreshGroups]);

  useEffect(() => {
    refreshRecords();
    refreshGroups();
  }, [refreshRecords, refreshGroups]);

  useEffect(() => {
    if (!records.length) {
      setExportSelection((prev) => (prev.size ? new Set() : prev));
      return;
    }
    setExportSelection((prev) => {
      const validIds = new Set(records.map((r) => r.id));
      let changed = false;
      const next = new Set();
      for (const id of prev) {
        if (validIds.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [records]);

  const orderedRecords = useMemo(
    () => [...records].sort((a, b) => (b.ts || "").localeCompare(a.ts || "")),
    [records],
  );
  const filteredRecords = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return orderedRecords;
    return orderedRecords.filter((record) =>
      (record.id || "").toLowerCase().includes(needle)
      || (record.name || "").toLowerCase().includes(needle),
    );
  }, [orderedRecords, filter]);

  useEffect(() => {
    if (!filteredRecords.length) {
      setSelectedId("");
      return;
    }
    if (!filteredRecords.some((record) => record.id === selectedId)) {
      setSelectedId(filteredRecords[0].id);
    }
  }, [filteredRecords, selectedId]);

  const selectedRecord = useMemo(
    () => filteredRecords.find((r) => r.id === selectedId) || filteredRecords[0] || null,
    [filteredRecords, selectedId],
  );

  const geometryState = useMemo(() => {
    if (!tomlConfig) return { error: "", geometry: null };
    try {
      return { error: "", geometry: buildGeometry(tomlConfig, DEFAULT_ALGORITHM) };
    } catch (err) {
      return { error: err instanceof Error ? err.message : String(err), geometry: null };
    }
  }, [tomlConfig]);
  const geometry = geometryState.geometry;

  // 为历史表格「计算结果」列预算好每条记录的距离（需要几何 + config）。
  const resultsById = useMemo(() => {
    if (!geometry || !tomlConfig) return {};
    const out = {};
    for (const record of orderedRecords) {
      const agg = aggregateDistance(record, geometry, tomlConfig);
      if (agg && agg.nUsed > 0 && Number.isFinite(agg.distanceMean)) {
        out[record.id] = {
          distanceMean: agg.distanceMean,
          distanceStd: agg.distanceStd,
          nUsed: agg.nUsed,
          nTotal: agg.nTotal,
        };
      }
    }
    return out;
  }, [orderedRecords, geometry, tomlConfig]);

  const measurementRow = useMemo(() => recordToMeasurementRow(selectedRecord), [selectedRecord]);
  const aggregate = useMemo(
    () => aggregateDistance(selectedRecord, geometry, tomlConfig),
    [selectedRecord, geometry, tomlConfig],
  );
  const measurement = useMemo(() => {
    if (aggregate?.representative) return aggregate.representative;
    return measureRow(measurementRow, geometry, tomlConfig);
  }, [aggregate, measurementRow, geometry, tomlConfig]);

  const calibration = tomlConfig?.calibration || tomlConfig;
  const resolution = {
    front: calibration?.front_camera?.resolution,
    rear: calibration?.rear_camera?.resolution,
  };
  const images = selectedRecord
    ? {
        frontSrc: lastFrameUrl(selectedRecord, "front"),
        rearSrc: lastFrameUrl(selectedRecord, "rear"),
        frontSpot: measurement?.spots?.front,
        rearSpot: measurement?.spots?.rear,
      }
    : null;
  const steps = analysisSteps(selectedRecord, measurement, aggregate);

  return (
    <AppShell
      mode={mode}
      setMode={setMode}
      mainPanel={mainPanel}
      brandTitle="DCPAM 分析"
      leftSidebar={
        <SamplingHistory
          records={filteredRecords}
          totalRecords={orderedRecords.length}
          selectedId={selectedRecord?.id || ""}
          setSelectedId={setSelectedId}
          filter={filter}
          setFilter={setFilter}
          onRefresh={refreshRecords}
          loading={loading}
          error={error}
          exportSelection={exportSelection}
          toggleExportSelection={toggleExportSelection}
          setAllExportSelection={setAllExportSelection}
          onExportZip={handleExportZip}
          exporting={exporting}
          onDeleteRecords={handleDeleteRecords}
          onAssignGroup={handleAssignGroup}
          onCreateGroup={handleCreateGroup}
          groups={groups}
          listStatus={listStatus}
          resultsById={resultsById}
        />
      }
      sceneSlot={
        <div className="scene-host">
          <SceneView
            rows={measurementRow ? [measurementRow] : []}
            measurement={measurement}
            geometry={geometry}
            layers={layers}
          />
          <LayersDrawer
            layers={layers}
            setLayers={setLayers}
            mainPanel={mainPanel}
            setMainPanel={setMainPanel}
          />
          {geometryState.error && <div className="viewer-error">配置解析失败：{geometryState.error}</div>}
          {!orderedRecords.length && !geometry && (
            <div className="empty">尚无采样记录，切到"拍照测量"采集，或加载 config.toml</div>
          )}
        </div>
      }
      processSlot={
        <ProcessPanel
          title={selectedRecord?.id}
          images={images}
          resolution={resolution}
          steps={steps}
        />
      }
    />
  );
}

function recordToMeasurementRow(record) {
  if (!record) return null;
  const front = record.front_uv_mean;
  const rear = record.rear_uv_mean;
  const lastFront = record.frames?.[record.frames.length - 1]?.front_path || "";
  const lastRear = record.frames?.[record.frames.length - 1]?.rear_path || "";
  if (!Array.isArray(front) || !Array.isArray(rear)) return null;
  return {
    name: record.id,
    front_u: front[0],
    front_v: front[1],
    rear_u: rear[0],
    rear_v: rear[1],
    front_path: lastFront,
    rear_path: lastRear,
  };
}

function lastFrameUrl(record, side) {
  const path = record?.frames?.[record.frames.length - 1]?.[`${side}_path`];
  if (!path) return "";
  if (path.startsWith("/")) return `/@fs${path}`;
  return `/@fs/${REPO_ROOT}/${path.replace(/^\.\//, "")}`;
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}

function formatPoint(point) {
  if (!point) return "(--, --, --)";
  return `(${format(point.x)}, ${format(point.y)}, ${format(point.z)})`;
}

function analysisSteps(record, measurement, aggregate) {
  if (!record) {
    return [{ title: "等待采样", lines: ["请在左侧选择一条采样记录"] }];
  }
  const frontMean = record.front_uv_mean || [];
  const rearMean = record.rear_uv_mean || [];
  const frontStd = record.front_uv_std || [];
  const rearStd = record.rear_uv_std || [];
  const nTotal = aggregate?.nTotal ?? (record.valid_n ?? record.n);
  const nUsed = aggregate?.nUsed ?? nTotal;
  const stats = [
    {
      title: `1. 圆心提取（n=${nTotal}${aggregate ? `，有效 ${nUsed}` : ""}）`,
      lines: [
        `前相机均值 uv=(${format(frontMean[0])}, ${format(frontMean[1])})  std=(${format(frontStd[0])}, ${format(frontStd[1])})`,
        `后相机均值 uv=(${format(rearMean[0])}, ${format(rearMean[1])})  std=(${format(rearStd[0])}, ${format(rearStd[1])})`,
      ],
    },
  ];
  if (!measurement) {
    stats.push({ title: "等待配置", lines: ["上传 config.toml 才能计算 3D 量"] });
    return stats;
  }
  return stats.concat([
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
      lines: buildResultLines(measurement, aggregate),
    },
  ]);
}

function buildResultLines(measurement, aggregate) {
  const lines = [`靶点：${formatPoint(measurement.target)}，设备系`];
  if (aggregate && aggregate.nUsed > 0) {
    const std = Number.isFinite(aggregate.distanceStd) ? aggregate.distanceStd : 0;
    lines.push(
      `靶点到激光线距离：${format(aggregate.distanceMean)} ± ${format(std)} mm` +
      `  (n=${aggregate.nUsed}/${aggregate.nTotal})`,
    );
    const dropped = aggregate.nTotal - aggregate.nUsed;
    if (dropped > 0) {
      const bits = [];
      if (aggregate.nDroppedByConfidence > 0) {
        bits.push(`置信度 ${aggregate.nDroppedByConfidence}`);
      }
      if (aggregate.nDroppedByMAD > 0) {
        bits.push(`距离离群 ${aggregate.nDroppedByMAD}`);
      }
      lines.push(`已剔除 ${dropped} 帧：${bits.join("，")}`);
    }
  } else if (aggregate) {
    lines.push(`靶点到激光线距离：无有效帧 (n=0/${aggregate.nTotal})`);
  } else {
    lines.push(`靶点到激光线距离：${format(measurement.distance)} mm`);
  }
  return lines;
}
