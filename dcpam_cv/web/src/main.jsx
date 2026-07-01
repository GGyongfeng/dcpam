import React from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.jsx";
import { ConfigProvider } from "./layout/useConfig.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <ConfigProvider>
    <App />
  </ConfigProvider>,
);
