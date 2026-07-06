import React, { useState } from "react";

import { ModeSwitcher } from "../components/Switchers.jsx";
import {
  PanelResizer,
  SampleDrawerResizer,
  useSampleDrawerWidth,
  useSidebarWidth,
} from "./usePanelWidth.jsx";

/**
 * 三区骨架：左栏 | 主区 | 右栏。
 * 主区与右栏分别通过 grid-area 互换位置；3D 与 过程 各自始终挂在固定 React 节点上，
 * 保证 SceneView 不被 unmount。
 */
export function AppShell({
  mode,
  setMode,
  mainPanel,
  leftSidebar,
  sceneSlot,
  processSlot,
  mainSlot,
  brandTitle = "DCPAM",
}) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sampleDrawerOpen, setSampleDrawerOpen] = useState(true);
  const { startDrag: startSampleDrag } = useSampleDrawerWidth();
  const { startDrag: startSidebarDrag } = useSidebarWidth();

  // mainSlot 存在 → 单列主区模式（测量模式）：只有左栏 + 主区，无右列 / 无 3D↔过程互换。
  const single = Boolean(mainSlot);
  const sceneArea = mainPanel === "3d" ? "main" : "right";
  const processArea = mainPanel === "3d" ? "right" : "main";

  return (
    <div
      className={`app workspace ${single ? "mode-measurement" : ""} ${sidebarOpen ? "" : "sidebar-collapsed"} ${!single && !sampleDrawerOpen ? "sample-collapsed" : ""}`}
    >
      <button
        type="button"
        className="edge-toggle edge-toggle-left"
        title={sidebarOpen ? "收起左栏" : "展开左栏"}
        aria-label={sidebarOpen ? "收起左栏" : "展开左栏"}
        onClick={() => setSidebarOpen((v) => !v)}
      >
        <span>{sidebarOpen ? "‹" : "›"}</span>
      </button>
      {!single && (
        <button
          type="button"
          className="edge-toggle edge-toggle-right"
          title={sampleDrawerOpen ? "收起右栏" : "展开右栏"}
          aria-label={sampleDrawerOpen ? "收起右栏" : "展开右栏"}
          onClick={() => setSampleDrawerOpen((v) => !v)}
        >
          <span>{sampleDrawerOpen ? "›" : "‹"}</span>
        </button>
      )}

      <aside className="sidebar workspace-sidebar">
        <div className="brand-row">
          <div className="brand">
            <h1>{brandTitle}</h1>
          </div>
          <div className="brand-actions">
            <ModeSwitcher mode={mode} setMode={setMode} />
          </div>
        </div>
        {leftSidebar}
        {sidebarOpen && (
          <PanelResizer startDrag={startSidebarDrag} className="sidebar-resizer" />
        )}
      </aside>

      {single ? (
        <div className="slot slot-main" style={{ gridArea: "main" }}>
          {mainSlot}
        </div>
      ) : (
        <>
          <div className="slot slot-3d" style={{ gridArea: sceneArea }}>
            {sceneArea === "right" && <SampleDrawerResizer startDrag={startSampleDrag} />}
            {sceneSlot}
          </div>
          <div className="slot slot-process" style={{ gridArea: processArea }}>
            {processArea === "right" && <SampleDrawerResizer startDrag={startSampleDrag} />}
            {processSlot}
          </div>
        </>
      )}
    </div>
  );
}
