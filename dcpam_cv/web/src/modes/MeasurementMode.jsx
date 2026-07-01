import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SceneView } from "../SceneView.jsx";
import { DEFAULT_LAYERS, LayersDrawer } from "../components/LayersDrawer.jsx";
import { ProcessPanel } from "../components/ProcessPanel.jsx";
import { AppShell } from "../layout/AppShell.jsx";
import { buildGeometry } from "../geometry.js";
import { measureRow } from "../pipeline.js";
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

  const geometryState = useMemo(() => {
    if (!tomlConfig) return { error: "", geometry: null };
    try {
      return { error: "", geometry: buildGeometry(tomlConfig, DEFAULT_ALGORITHM) };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error), geometry: null };
    }
  }, [tomlConfig]);
  const geometry = geometryState.geometry;

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

  useEffect(() => {
    refreshRecords();
    refreshHealth();
  }, [refreshRecords, refreshHealth]);

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
  const measurement = useMemo(
    () => measureRow(measurementRow, geometry, tomlConfig),
    [measurementRow, geometry, tomlConfig],
  );

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
      setStatus({ kind: "ok", text: `已采样 ${payload.id}（${payload.valid_n}/${payload.n} 帧）` });
      setRecords((current) => [...current, payload]);
      setSelectedId(payload.id);
      setSampleIndex(index + 1);
      refreshHealth();
    } catch (error) {
      setStatus({ kind: "error", text: `拍照失败：${error.message}` });
    } finally {
      setCapturing(false);
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
  const steps = measurementSteps(selectedRecord, measurement);

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
}) {
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
        />
      </section>

      <section className="section sample-list-section">
        <div className="section-title-row">
          <h3>历史 ({records.length})</h3>
        </div>
        <div className="sample-list">
          {records.length === 0 ? (
            <div className="sample-empty">尚无采样记录</div>
          ) : (
            [...records].reverse().map((record) => (
              <button
                type="button"
                key={record.id}
                className={`sample-item ${record.id === selectedId ? "active" : ""}`}
                onClick={() => setSelectedId(record.id)}
              >
                <span>{record.id}</span>
                <span className="sample-item-meta">n={record.valid_n ?? record.n}</span>
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function CameraModule({
  health, onReconnect, onRefresh, previewOn, setPreviewOn,
  captureN, setCaptureN, sampleName, setSampleName, sampleIndex, setSampleIndex,
  capturing, onCapture, status,
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
          className="capture-button"
          disabled={capturing}
          onClick={onCapture}
        >
          {capturing ? "正在拍..." : `拍照 + 测量（${(sampleName || "sample").trim() || "sample"}-${String(sampleIndex).padStart(3, "0")}）`}
        </button>
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

function measurementSteps(record, measurement) {
  if (!record) return [{ title: "等待样本", lines: ["上传 config.toml 后按下\"拍照 + 测量\"开始采样"] }];
  const frontMean = record.front_uv_mean || [];
  const rearMean = record.rear_uv_mean || [];
  const frontStd = record.front_uv_std || [];
  const rearStd = record.rear_uv_std || [];
  const stats = [
    {
      title: `1. 圆心提取（n=${record.valid_n ?? record.n}）`,
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
      lines: [
        `靶点：${formatPoint(measurement.target)}，设备系`,
        `靶点到激光线距离：${format(measurement.distance)} mm`,
      ],
    },
  ]);
}
