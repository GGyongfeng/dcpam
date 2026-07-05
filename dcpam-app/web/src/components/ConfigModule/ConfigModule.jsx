import React, { useState } from "react";

import { ConfigActions } from "./ConfigActions.jsx";
import { ConfigForm } from "./ConfigForm.jsx";
import { useConfigController } from "./useConfigController.js";

/**
 * 顶层 UI 组件：折叠头（箭头 + CONFIG 标题 + 4 icon 按钮）+ 表单。
 *
 * @param {object} props
 * @param {boolean} [props.defaultOpen=true]   初始是否展开
 */
export function ConfigModule({ defaultOpen = true } = {}) {
  const [open, setOpen] = useState(defaultOpen);
  const controller = useConfigController();

  return (
    <div className="config-module">
      <div className="config-module-header">
        <button
          type="button"
          className="config-module-toggle"
          onClick={() => setOpen((v) => !v)}
          title={open ? "折叠" : "展开"}
        >
          <span className="caret">{open ? "▾" : "▸"}</span>
          <h3>config</h3>
        </button>
        <ConfigActions controller={controller} />
      </div>
      {open && <ConfigForm controller={controller} />}
    </div>
  );
}
