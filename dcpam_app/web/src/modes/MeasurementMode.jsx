import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SamplingHistory } from "../components/SamplingHistory.jsx";
import { PreviewSettings } from "../components/Switchers.jsx";
import { AppShell } from "../layout/AppShell.jsx";
import { useStoredText } from "../storage.js";

const STORAGE_KEYS = {
  captureN: "dcpam.measure.captureN",
  sampleName: "dcpam.measure.sampleName",
};


export function MeasurementMode({ mode, setMode }) {
  const [captureN, setCaptureN] = useStoredText(STORAGE_KEYS.captureN);
  const [sampleName, setSampleName] = useStoredText(STORAGE_KEYS.sampleName);
  const [sampleIndex, setSampleIndex] = useState(1);
  const [previewOn, setPreviewOn] = useState(true);

  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
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
    setLoading(true);
    try {
      const response = await fetch("/api/measurements");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setRecords(Array.isArray(data) ? data : []);
    } catch (error) {
      setStatus({ kind: "error", text: `读取记录失败：${error.message}` });
    } finally {
      setLoading(false);
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
    if (!records.length) {
      setSelectedId((current) => (current ? "" : current));
      return;
    }
    if (!records.some((record) => record.id === selectedId)) {
      setSelectedId(records[records.length - 1].id);
    }
  }, [records, selectedId]);

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
      if (payload.valid_n === 0) {
        // 图已留存、记录已生成，但圆心提取全失败 —— 提醒但不算失败
        const firstErr = payload.extraction_errors?.[0] || "圆心提取失败";
        setStatus({
          kind: "error",
          text: `已保存 ${payload.id}，但提取失败（0/${payload.n} 帧）：${firstErr}`,
        });
      } else {
        setStatus({
          kind: "ok",
          text: `已采样 ${payload.id}（${payload.valid_n}/${payload.n} 帧，用时 ${formatElapsed(elapsed)}）`,
        });
      }
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
    if (reconnecting) return;
    setReconnecting(true);
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
    } finally {
      setReconnecting(false);
    }
  };

  // 未连接时点 ⚡ 走这里：主动探测一次健康（区别于后台 3s 轮询，带加载态）
  const connectCamera = async () => {
    if (reconnecting) return;
    setReconnecting(true);
    setStatus({ kind: "info", text: "正在连接相机..." });
    try {
      await refreshHealth();
    } finally {
      setReconnecting(false);
    }
  };

  return (
    <AppShell
      mode={mode}
      setMode={setMode}
      brandTitle="DCPAM 测量"
      leftSidebar={
        <SamplingHistory
          records={filteredRecords}
          totalRecords={orderedRecords.length}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          filter={filter}
          setFilter={setFilter}
          onRefresh={refreshRecords}
          loading={loading}
          exportSelection={exportSelection}
          toggleExportSelection={toggleExportSelection}
          setAllExportSelection={setAllExportSelection}
          onExportZip={handleExportZip}
          exporting={exporting}
          onDeleteRecords={handleDeleteRecords}
          listStatus={listStatus}
        />
      }
      mainSlot={
        <div className="camera-main">
          <CameraModule
            health={cameraHealth}
            onReconnect={reconnectCamera}
            onRefresh={connectCamera}
            reconnecting={reconnecting}
            previewOn={previewOn}
            setPreviewOn={setPreviewOn}
            captureN={captureN}
            setCaptureN={setCaptureN}
            sampleName={sampleName}
            setSampleName={setSampleName}
            sampleIndex={sampleIndex}
            setSampleIndex={setSampleIndex}
            capturing={capturing}
            onCapture={handleCapture}
            status={status}
            liveElapsedMs={liveElapsedMs}
            captureElapsedMs={captureElapsedMs}
          />
        </div>
      }
    />
  );
}

function CameraModule({
  health, onReconnect, onRefresh, reconnecting,
  previewOn, setPreviewOn,
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
      {reconnecting && (
        <div className="camera-loading-overlay">
          <div className="camera-spinner" />
          <span>{isConnected ? "重新连接相机…" : "正在连接相机…"}</span>
        </div>
      )}
      <div className="section-title-row">
        <h3>相机</h3>
        <div className="camera-actions">
          <button
            type="button"
            className={`config-icon-btn ${isConnected ? "" : "primary"}`}
            title={connectTitle}
            onClick={connectAction}
            disabled={reconnecting}
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

      <div className="camera-preview-settings">
        <PreviewSettings />
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
    case "nopasswd_missing":
      return net.message || "未安装免密规则，请在启动 dcpam 的终端按提示执行安装命令";
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

