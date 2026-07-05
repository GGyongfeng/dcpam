import React from "react";

import { DownloadIcon, RefreshIcon, SaveIcon, UploadIcon } from "./icons.jsx";

/**
 * 4 个 icon 按钮，弹性等分。整块由 CSS 通过 flex 撑满右侧。
 */
export function ConfigActions({ controller }) {
  const { dirty, loading, onSave, onUpload, onDownload, refresh } = controller;
  return (
    <div className="config-actions">
      <label
        className={`config-icon-btn ${loading ? "disabled" : ""}`}
        title="上传本地 .toml 文件（覆盖当前 config.toml）"
      >
        <UploadIcon />
        <input type="file" accept=".toml,text/plain" onChange={onUpload} disabled={loading} />
      </label>
      <button
        type="button"
        className="config-icon-btn"
        title="下载当前 config.toml"
        onClick={onDownload}
      >
        <DownloadIcon />
      </button>
      <button
        type="button"
        className={`config-icon-btn ${dirty && !loading ? "primary" : ""}`}
        title={dirty ? "保存到本地 config.toml" : "无修改"}
        disabled={!dirty || loading}
        onClick={onSave}
      >
        <SaveIcon />
      </button>
      <button
        type="button"
        className="config-icon-btn"
        title="重新从磁盘加载（放弃未保存的修改）"
        onClick={refresh}
      >
        <RefreshIcon />
      </button>
    </div>
  );
}
