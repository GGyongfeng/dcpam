import React, { useState } from "react";

import { MainPanelSwitcher, ModeSwitcher, PreviewSettings } from "../components/Switchers.jsx";
import { SettingsModal } from "../components/SettingsModal.jsx";
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
  setMainPanel,
  leftSidebar,
  sceneSlot,
  processSlot,
  brandTitle = "DCPAM",
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sampleDrawerOpen, setSampleDrawerOpen] = useState(true);
  const { startDrag: startSampleDrag } = useSampleDrawerWidth();
  const { startDrag: startSidebarDrag } = useSidebarWidth();

  const sceneArea = mainPanel === "3d" ? "main" : "right";
  const processArea = mainPanel === "3d" ? "right" : "main";

  return (
    <div
      className={`app workspace ${sidebarOpen ? "" : "sidebar-collapsed"} ${sampleDrawerOpen ? "" : "sample-collapsed"}`}
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
      <button
        type="button"
        className="edge-toggle edge-toggle-right"
        title={sampleDrawerOpen ? "收起右栏" : "展开右栏"}
        aria-label={sampleDrawerOpen ? "收起右栏" : "展开右栏"}
        onClick={() => setSampleDrawerOpen((v) => !v)}
      >
        <span>{sampleDrawerOpen ? "›" : "‹"}</span>
      </button>

      <aside className="sidebar workspace-sidebar">
        <div className="brand-row">
          <div className="brand">
            <h1>{brandTitle}</h1>
          </div>
          <button
            type="button"
            className="brand-settings"
            aria-label="设置"
            onClick={() => setSettingsOpen(true)}
          >
            ⚙
          </button>
        </div>
        {leftSidebar}
        {sidebarOpen && (
          <PanelResizer startDrag={startSidebarDrag} className="sidebar-resizer" />
        )}
      </aside>

      <div className="slot slot-3d" style={{ gridArea: sceneArea }}>
        {sceneArea === "right" && <SampleDrawerResizer startDrag={startSampleDrag} />}
        {sceneSlot}
      </div>
      <div className="slot slot-process" style={{ gridArea: processArea }}>
        {processArea === "right" && <SampleDrawerResizer startDrag={startSampleDrag} />}
        {processSlot}
      </div>

      {settingsOpen && (
        <SettingsModal onClose={() => setSettingsOpen(false)}>
          <ModeSwitcher mode={mode} setMode={setMode} />
          <MainPanelSwitcher mainPanel={mainPanel} setMainPanel={setMainPanel} />
          <PreviewSettings />
        </SettingsModal>
      )}
    </div>
  );
}
