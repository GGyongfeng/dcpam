import React, { useEffect, useRef, useState } from "react";

export function ModeSwitcher({ mode, setMode }) {
  return (
    <div className="mode-segmented mode-segmented-compact">
      <button
        type="button"
        className={`segment-btn ${mode === "analysis" ? "active" : ""}`}
        onClick={() => setMode("analysis")}
      >
        分析
      </button>
      <button
        type="button"
        className={`segment-btn ${mode === "measurement" ? "active" : ""}`}
        onClick={() => setMode("measurement")}
      >
        测量
      </button>
    </div>
  );
}

export function MainPanelSwitcher({ mainPanel, setMainPanel }) {
  return (
    <div className="mode-segmented">
      <button
        type="button"
        className={`segment-btn ${mainPanel === "3d" ? "active" : ""}`}
        onClick={() => setMainPanel("3d")}
      >
        3D 模型
      </button>
      <button
        type="button"
        className={`segment-btn ${mainPanel === "process" ? "active" : ""}`}
        onClick={() => setMainPanel("process")}
      >
        计算过程
      </button>
    </div>
  );
}

const PREVIEW_FIELDS = [
  {
    key: "interval_ms",
    label: "预览间隔",
    unit: "ms",
    min: 0,
    max: 500,
    step: 1,
    hint: "越小越快；0 表示不主动限速，取决于相机 fps",
  },
  {
    key: "max_side",
    label: "最长边",
    unit: "px",
    min: 200,
    max: 2600,
    step: 10,
    hint: "缩小可显著降低 JPEG 编码开销",
  },
  {
    key: "quality",
    label: "JPEG 质量",
    unit: "",
    min: 1,
    max: 100,
    step: 1,
    hint: "质量↓ → 编码更快、字节更小",
  },
];

export function PreviewSettings() {
  const [values, setValues] = useState(null); // { interval_ms, max_side, quality } | null=loading
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const debounceRef = useRef(null);
  const inflightRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/preview/config")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setValues(data);
      })
      .catch((exc) => {
        if (!cancelled) setError(String(exc.message || exc));
      });
    return () => {
      cancelled = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (inflightRef.current) inflightRef.current.abort();
    };
  }, []);

  const scheduleCommit = (next) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      debounceRef.current = null;
      if (inflightRef.current) inflightRef.current.abort();
      const controller = new AbortController();
      inflightRef.current = controller;
      setPending(true);
      setError("");
      try {
        const response = await fetch("/api/preview/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
          signal: controller.signal,
        });
        if (!response.ok) {
          const body = await response.text();
          throw new Error(body || `HTTP ${response.status}`);
        }
        const data = await response.json();
        setValues(data);
      } catch (exc) {
        if (exc.name === "AbortError") return;
        setError(String(exc.message || exc));
      } finally {
        if (inflightRef.current === controller) inflightRef.current = null;
        setPending(false);
      }
    }, 250);
  };

  const updateField = (key, raw, field) => {
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed)) return;
    const clamped = Math.max(field.min, Math.min(field.max, parsed));
    setValues((prev) => {
      if (!prev) return prev;
      const next = { ...prev, [key]: clamped };
      scheduleCommit(next);
      return next;
    });
  };

  return (
    <div className="settings-section">
      <div className="settings-title-row">
        <strong>预览采集</strong>
        <span className="preview-settings-status">
          {pending ? "保存中…" : error ? `⚠ ${error}` : values ? "已同步" : "加载中…"}
        </span>
      </div>
      {PREVIEW_FIELDS.map((field) => {
        const value = values ? values[field.key] : field.min;
        return (
          <div key={field.key} className="preview-settings-row">
            <div className="preview-settings-label">
              <span>{field.label}</span>
              <span className="preview-settings-hint">{field.hint}</span>
            </div>
            <div className="preview-settings-controls">
              <input
                type="range"
                min={field.min}
                max={field.max}
                step={field.step}
                value={value}
                disabled={!values}
                onChange={(e) => updateField(field.key, e.target.value, field)}
              />
              <input
                type="number"
                min={field.min}
                max={field.max}
                step={field.step}
                value={value}
                disabled={!values}
                onChange={(e) => updateField(field.key, e.target.value, field)}
              />
              {field.unit && <span className="preview-settings-unit">{field.unit}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
