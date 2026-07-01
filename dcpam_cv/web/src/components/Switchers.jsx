import React from "react";

export function ModeSwitcher({ mode, setMode }) {
  return (
    <div className="settings-section">
      <div className="settings-title-row">
        <strong>模式</strong>
      </div>
      <div className="mode-segmented">
        <button
          type="button"
          className={`segment-btn ${mode === "analysis" ? "active" : ""}`}
          onClick={() => setMode("analysis")}
        >
          分析模式
        </button>
        <button
          type="button"
          className={`segment-btn ${mode === "measurement" ? "active" : ""}`}
          onClick={() => setMode("measurement")}
        >
          测量模式
        </button>
      </div>
    </div>
  );
}

export function MainPanelSwitcher({ mainPanel, setMainPanel }) {
  return (
    <div className="settings-section">
      <div className="settings-title-row">
        <strong>主面板内容</strong>
      </div>
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
    </div>
  );
}
