import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SceneView } from "../SceneView.jsx";
import { DEFAULT_LAYERS, LayersDrawer } from "../components/LayersDrawer.jsx";
import { ProcessPanel } from "../components/ProcessPanel.jsx";
import { AppShell } from "../layout/AppShell.jsx";
import { buildGeometry } from "../geometry.js";
import { measureRow, aggregateDistance } from "../pipeline.js";
import { useStoredText } from "../storage.js";

const STORAGE_KEYS = {
  captureN: "dcpam.measure.captureN",
  sampleName: "dcpam.measure.sampleName",
};

const DEFAULT_ALGORITHM = {
  imageAlignment: "pnp",
  reflectionSource: "device",
};

const REPO_ROOT = "/Users/guyongfeng/Desktop/dcpam";

export function MeasurementMode({ mode, setMode, mainPanel, setMainPanel, tomlConfig }) {
  const [captureN, setCaptureN] = useStoredText(STORAGE_KEYS.captureN);
  const [sampleName, setSampleName] = useStoredText(STORAGE_KEYS.sampleName);
  const [sampleIndex, setSampleIndex] = useState(1);
  const [previewOn, setPreviewOn] = useState(true);
  const [layers, setLayers] = useState(DEFAULT_LAYERS);

  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [capturing, setCapturing] = useState(false);
  const [status, setStatus] = useState({ kind: "idle", text: "" });
  const [cameraHealth, setCameraHealth] = useState({ ok: null, message: "" });
  const [captureElapsedMs, setCaptureElapsedMs] = useState(null);
  const [captureStartAt, setCaptureStartAt] = useState(null);
  const [nowTs, setNowTs] = useState(0);
  const [exportSelection, setExportSelection] = useState(() => new Set());
  const [exporting, setExporting] = useState(false);
  const [listStatus, setListStatus] = useState({ kind: "idle", text: "" });

  useEffect(() => {
    if (!capturing || captureStartAt == null) return;
    const tick = () => setNowTs(Date.now());
    tick();
    const id = setInterval(tick, 100);
    return () => clearInterval(id);
  }, [capturing, captureStartAt]);

  const liveElapsedMs = capturing && captureStartAt != null ? Math.max(0, nowTs - captureStartAt) : null;

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

  const refreshRecords = useCallback(async () => {
    try {
      const response = await fetch("/api/measurements");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setRecords(data);
    } catch (error) {
      setStatus({ kind: "error", text: `读取记录失败：${error.message}` });
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch("/api/health");
      const data = await response.json();
      setCameraHealth({ ok: data.camera === "ok", message: data.message || "" });
    } catch (error) {
      setCameraHealth({ ok: false, message: error.message });
    }
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
    } catch (error) {
      setListStatus({ kind: "error", text: `导出失败：${error.message}` });
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
      } catch (error) {
        failed.push(`${id}:${error.message}`);
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

  const geometryState = useMemo(() => {
    if (!tomlConfig) return { error: "", geometry: null };
    try {
      return { error: "", geometry: buildGeometry(tomlConfig, DEFAULT_ALGORITHM) };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error), geometry: null };
    }
  }, [tomlConfig]);
  const geometry = geometryState.geometry;

  useEffect(() => {
    refreshRecords();
    refreshHealth();
  }, [refreshRecords, refreshHealth]);

  useEffect(() => {
    if (capturing) return;
    const id = setInterval(() => {
      refreshHealth();
    }, 3000);
    return () => clearInterval(id);
  }, [refreshHealth, capturing]);

  useEffect(() => {
    if (!records.length) {
      setSelectedId((current) => (current ? "" : current));
      return;
    }
    if (!records.some((record) => record.id === selectedId)) {
      setSelectedId(records[records.length - 1].id);
    }
  }, [records, selectedId]);

  const selectedRecord = useMemo(
    () => records.find((record) => record.id === selectedId) || records[records.length - 1] || null,
    [records, selectedId],
  );
  const measurementRow = useMemo(() => recordToMeasurementRow(selectedRecord), [selectedRecord]);
  const aggregate = useMemo(
    () => aggregateDistance(selectedRecord, geometry, tomlConfig),
    [selectedRecord, geometry, tomlConfig],
  );
  // 3D 场景 & 中间步骤展示：优先用 aggregate 的代表帧（保证与最终距离一致）；
  // 缺 frames 数据的旧样本回退到 mean-UV pipeline。
  const measurement = useMemo(() => {
    if (aggregate?.representative) return aggregate.representative;
    return measureRow(measurementRow, geometry, tomlConfig);
  }, [aggregate, measurementRow, geometry, tomlConfig]);

  // 名称变化 → 查询该 name 在磁盘上的下一个可用 index
  useEffect(() => {
    const name = (sampleName || "sample").trim();
    if (!name) return;
    let cancelled = false;
    fetch(`/api/measurements/next-index?name=${encodeURIComponent(name)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!cancelled && data && Number.isFinite(data.next_index)) {
          setSampleIndex(data.next_index);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [sampleName]);

  const handleCapture = async () => {
    if (capturing) return;
    const n = parseCaptureN(captureN);
    const name = (sampleName || "sample").trim() || "sample";
    const index = Math.max(1, parseInt(sampleIndex, 10) || 1);
    const startAt = Date.now();
    setCaptureStartAt(startAt);
    setNowTs(startAt);
    setCaptureElapsedMs(null);
    setCapturing(true);
    setStatus({ kind: "info", text: `正在拍 ${name}-${String(index).padStart(3, "0")}（${n} 张）...` });
    try {
      const response = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ n, name, index }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload?.detail || `HTTP ${response.status}`;
        throw new Error(detail);
      }
      const elapsed = Date.now() - startAt;
      setCaptureElapsedMs(elapsed);
      setStatus({
        kind: "ok",
        text: `已采样 ${payload.id}（${payload.valid_n}/${payload.n} 帧，用时 ${formatElapsed(elapsed)}）`,
      });
      setRecords((current) => [...current, payload]);
      setSelectedId(payload.id);
      setSampleIndex(index + 1);
      refreshHealth();
    } catch (error) {
      setCaptureElapsedMs(Date.now() - startAt);
      setStatus({ kind: "error", text: `拍照失败：${error.message}` });
    } finally {
      setCapturing(false);
      setCaptureStartAt(null);
    }
  };

  const reconnectCamera = async () => {
    setStatus({ kind: "info", text: "重新连接相机..." });
    try {
      const response = await fetch("/api/camera/reconnect", { method: "POST" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        // 后端 detail 可能是 string 或 {message, net}
        const raw = payload?.detail;
        const message = typeof raw === "string" ? raw : raw?.message || `HTTP ${response.status}`;
        const netHint = formatNetHint(typeof raw === "object" ? raw?.net : null);
        throw new Error(netHint ? `${message}\n${netHint}` : message);
      }
      const netHint = formatNetHint(payload?.net);
      setStatus({ kind: "ok", text: netHint ? `相机已连接（${netHint}）` : "相机已连接" });
      setCameraHealth({ ok: true, message: "" });
    } catch (error) {
      setStatus({ kind: "error", text: `连接失败：${error.message}` });
      setCameraHealth({ ok: false, message: error.message });
    }
  };

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
  const steps = measurementSteps(selectedRecord, measurement, aggregate);

  return (
    <AppShell
      mode={mode}
      setMode={setMode}
      mainPanel={mainPanel}
      setMainPanel={setMainPanel}
      brandTitle="DCPAM 测量"
      leftSidebar={
        <LeftSidebar
          captureN={captureN}
          setCaptureN={setCaptureN}
          sampleName={sampleName}
          setSampleName={setSampleName}
          sampleIndex={sampleIndex}
          setSampleIndex={setSampleIndex}
          previewOn={previewOn}
          setPreviewOn={setPreviewOn}
          capturing={capturing}
          onCapture={handleCapture}
          status={status}
          cameraHealth={cameraHealth}
          onReconnect={reconnectCamera}
          onRefreshHealth={refreshHealth}
          records={records}
          selectedId={selectedRecord?.id || ""}
          setSelectedId={setSelectedId}
          liveElapsedMs={liveElapsedMs}
          captureElapsedMs={captureElapsedMs}
          exportSelection={exportSelection}
          toggleExportSelection={toggleExportSelection}
          setAllExportSelection={setAllExportSelection}
          onExportZip={handleExportZip}
          exporting={exporting}
          onDeleteRecords={handleDeleteRecords}
          listStatus={listStatus}
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
          <LayersDrawer layers={layers} setLayers={setLayers} />
          {geometryState.error && <div className="viewer-error">配置解析失败：{geometryState.error}</div>}
          {!geometry && <div className="empty">上传 config.toml 后开始测量</div>}
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

function LeftSidebar({
  captureN, setCaptureN,
  sampleName, setSampleName, sampleIndex, setSampleIndex,
  previewOn, setPreviewOn, capturing, onCapture, status,
  cameraHealth, onReconnect, onRefreshHealth,
  records, selectedId, setSelectedId,
  liveElapsedMs, captureElapsedMs,
  exportSelection, toggleExportSelection, setAllExportSelection,
  onExportZip, exporting,
  onDeleteRecords,
  listStatus,
}) {
  const allIds = useMemo(() => records.map((r) => r.id), [records]);
  const selectedCount = exportSelection.size;
  const allSelected = allIds.length > 0 && selectedCount === allIds.length;

  return (
    <div className="left-stack">
      <section className="section">
        <CameraModule
          health={cameraHealth}
          onReconnect={onReconnect}
          onRefresh={onRefreshHealth}
          previewOn={previewOn}
          setPreviewOn={setPreviewOn}
          captureN={captureN}
          setCaptureN={setCaptureN}
          sampleName={sampleName}
          setSampleName={setSampleName}
          sampleIndex={sampleIndex}
          setSampleIndex={setSampleIndex}
          capturing={capturing}
          onCapture={onCapture}
          status={status}
          liveElapsedMs={liveElapsedMs}
          captureElapsedMs={captureElapsedMs}
        />
      </section>

      <section className="section sample-list-section">
        <div className="section-title-row">
          <h3>历史 ({records.length})</h3>
          <div className="sample-list-actions">
            <button
              type="button"
              className="link-button"
              disabled={!allIds.length}
              onClick={() => setAllExportSelection(allSelected ? [] : allIds)}
              title={allSelected ? "取消全选" : "全选当前列表"}
            >
              {allSelected ? "清除" : "全选"}
            </button>
            <button
              type="button"
              className="export-zip-button"
              disabled={exporting || selectedCount === 0}
              onClick={onExportZip}
              title={selectedCount === 0 ? "先勾选要导出的采样" : `导出 ${selectedCount} 个采样为 zip`}
            >
              {exporting ? "打包中..." : `导出 ZIP (${selectedCount})`}
            </button>
            <button
              type="button"
              className="delete-batch-button"
              disabled={selectedCount === 0}
              onClick={() => onDeleteRecords([...exportSelection])}
              title={selectedCount === 0 ? "先勾选要删除的采样" : `删除选中的 ${selectedCount} 个采样`}
            >
              {`删除 (${selectedCount})`}
            </button>
          </div>
        </div>
        <div className="sample-list">
          {records.length === 0 ? (
            <div className="sample-empty">尚无采样记录</div>
          ) : (
            [...records].reverse().map((record) => {
              const active = record.id === selectedId;
              const picked = exportSelection.has(record.id);
              return (
                <div
                  key={record.id}
                  className={`sample-item-row${active ? " active" : ""}${picked ? " picked" : ""}`}
                >
                  <label
                    className="sample-item-check"
                    title="勾选后可批量导出或删除"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={picked}
                      onChange={() => toggleExportSelection(record.id)}
                    />
                  </label>
                  <button
                    type="button"
                    className="sample-item"
                    onClick={() => setSelectedId(record.id)}
                  >
                    <span>{record.id}</span>
                    <span className="sample-item-meta">n={record.valid_n ?? record.n}</span>
                  </button>
                  <button
                    type="button"
                    className="sample-item-delete"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteRecords([record.id]);
                    }}
                    title={`删除 ${record.id}`}
                    aria-label={`删除 ${record.id}`}
                  >
                    <TrashIcon />
                  </button>
                </div>
              );
            })
          )}
        </div>
        {listStatus && listStatus.text && (
          <div className={`capture-status status-${listStatus.kind}`}>{listStatus.text}</div>
        )}
      </section>
    </div>
  );
}

function CameraModule({
  health, onReconnect, onRefresh, previewOn, setPreviewOn,
  captureN, setCaptureN, sampleName, setSampleName, sampleIndex, setSampleIndex,
  capturing, onCapture, status, liveElapsedMs, captureElapsedMs,
}) {
  const isConnected = health.ok === true;
  const isDetecting = health.ok === null;
  const connectAction = isConnected ? onReconnect : onRefresh;
  const connectTitle = isConnected
    ? "断开后重新连接（更换配置 / 恢复卡住的连接）"
    : "尝试连接相机";

  return (
    <div className="camera-module">
      <div className="section-title-row">
        <h3>相机</h3>
        <div className="camera-actions">
          <button
            type="button"
            className={`config-icon-btn ${isConnected ? "" : "primary"}`}
            title={connectTitle}
            onClick={connectAction}
          >
            {isConnected ? <RefreshIcon /> : <BoltIcon />}
          </button>
          <button
            type="button"
            className={`config-icon-btn ${previewOn ? "primary" : ""}`}
            title={previewOn ? "关闭实时预览" : "打开实时预览（需要相机已连接）"}
            onClick={() => setPreviewOn(!previewOn)}
          >
            <EyeIcon open={previewOn} />
          </button>
        </div>
      </div>

      {/* 已连接 + 预览开 → 画面；否则显示状态文字（未连接则消息内联） */}
      {isConnected && previewOn ? (
        <PreviewBlock active />
      ) : (
        <div className={`camera-line camera-${isConnected ? "ok" : isDetecting ? "muted" : "error"}`}>
          <span className="dot" />
          {isConnected ? (
            <span>已连接</span>
          ) : isDetecting ? (
            <span>检测中...</span>
          ) : (
            <span>
              未连接
              {health.message && <span className="camera-inline-message">:{health.message}</span>}
            </span>
          )}
        </div>
      )}

      {/* 采样控件 */}
      <div className="capture-controls">
        <label className="capture-field">
          <span className="capture-field-label">采样名称:</span>
          <div className="capture-name-group">
            <input
              type="text"
              className="capture-name-input"
              value={sampleName || "sample"}
              onChange={(event) => setSampleName(event.target.value)}
              title="采样名称（英文/数字/._-）"
            />
            <span className="capture-name-dash">-</span>
            <input
              type="number"
              className="capture-index-input"
              min={1}
              max={999}
              value={sampleIndex}
              onChange={(event) => setSampleIndex(Math.max(1, parseInt(event.target.value, 10) || 1))}
              title="下一次采样的序号（自动 +1，可手动调）"
            />
          </div>
        </label>
        <label className="capture-field">
          <span className="capture-field-label">重复采样数:</span>
          <input
            type="number"
            className="capture-n-input"
            min={1}
            max={50}
            value={captureN || "10"}
            onChange={(event) => setCaptureN(event.target.value)}
            title="每次采样连拍张数，对多次结果的 uv 取均值以提升重复度"
          />
        </label>
        <button
          type="button"
          className={`capture-button${isConnected ? " is-connected" : ""}`}
          disabled={capturing || !isConnected}
          onClick={onCapture}
          title={
            !isConnected
              ? "相机未连接，先点左上角按钮尝试连接"
              : "开始一次拍照 + 测量"
          }
        >
          {capturing
            ? `正在拍...${liveElapsedMs != null ? ` ${formatElapsed(liveElapsedMs)}` : ""}`
            : `拍照 + 测量（${(sampleName || "sample").trim() || "sample"}-${String(sampleIndex).padStart(3, "0")}）`}
        </button>
        {(capturing || captureElapsedMs != null) && (
          <div className="capture-timing">
            {capturing ? (
              <>
                <span>本次采样用时:</span>
                <span className="timing-value">{formatElapsed(liveElapsedMs ?? 0)}</span>
              </>
            ) : (
              <>
                <span>上次采样用时:</span>
                <span className="timing-value">{formatElapsed(captureElapsedMs)}</span>
              </>
            )}
          </div>
        )}
        {status.text && <div className={`capture-status status-${status.kind}`}>{status.text}</div>}
      </div>
    </div>
  );
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function EyeIcon({ open }) {
  if (open) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function PreviewBlock({ active }) {
  const tokenRef = useRef(0);
  const [token, setToken] = useState(0);

  useEffect(() => {
    if (!active) return;
    tokenRef.current += 1;
    setToken(tokenRef.current);
  }, [active]);

  if (!active) {
    return (
      <div className="preview-block preview-paused">
        <span>预览已关闭</span>
      </div>
    );
  }
  return (
    <div className="preview-block">
      <PreviewImage label="前相机" cam="front" token={token} />
      <PreviewImage label="后相机" cam="rear" token={token} />
    </div>
  );
}

function PreviewImage({ label, cam, token }) {
  const [errored, setErrored] = useState(false);
  const src = `/api/preview.mjpeg?cam=${cam}&t=${token}`;
  return (
    <figure className="preview-figure">
      <div className="image-frame">
        {errored ? (
          <span>预览失败（检查相机连接）</span>
        ) : (
          <img src={src} alt={label} onError={() => setErrored(true)} />
        )}
      </div>
      <figcaption>{label}</figcaption>
    </figure>
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

function parseCaptureN(value) {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n)) return 10;
  return Math.max(1, Math.min(50, n));
}

function formatElapsed(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "--";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m} min ${s.toFixed(1)} s`;
}

function formatNetHint(net) {
  if (!net || typeof net !== "object") return "";
  switch (net.status) {
    case "ok":
      return net.interface ? `已重配 ${net.interface}` : "已重配网卡";
    case "sudo_expired":
      return net.message || "sudo 密码已过期，请在终端执行 sudo -v 后重试";
    case "no_interface":
      return net.message || "未检测到千兆网口";
    case "not_darwin":
      return "";
    case "error":
      return net.message ? `网卡配置失败：${net.message}` : "网卡配置失败";
    default:
      return "";
  }
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "";
}

function formatPoint(point) {
  if (!point) return "(--, --, --)";
  return `(${format(point.x)}, ${format(point.y)}, ${format(point.z)})`;
}

function measurementSteps(record, measurement, aggregate) {
  if (!record) return [{ title: "等待样本", lines: ["上传 config.toml 后按下\"拍照 + 测量\"开始采样"] }];
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
