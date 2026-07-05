import React from "react";

import { AnalysisMode } from "./modes/AnalysisMode.jsx";
import { MeasurementMode } from "./modes/MeasurementMode.jsx";
import { useConfig } from "./layout/useConfig.jsx";
import { useMainPanelLayout } from "./layout/useMainPanelLayout.js";
import { useStoredText } from "./storage.js";

const MODE_KEY = "dcpam.viewer.mode";

export function App() {
  const [rawMode, setMode] = useStoredText(MODE_KEY);
  const [mainPanel, setMainPanel] = useMainPanelLayout();
  const { data: tomlConfig } = useConfig();
  const mode = rawMode === "measurement" ? "measurement" : "analysis";
  const Mode = mode === "measurement" ? MeasurementMode : AnalysisMode;
  return (
    <Mode
      mode={mode}
      setMode={setMode}
      mainPanel={mainPanel}
      setMainPanel={setMainPanel}
      tomlConfig={tomlConfig}
    />
  );
}
