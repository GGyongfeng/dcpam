import React from "react";

export function SettingsModal({ onClose, children }) {
  return (
    <div className="settings-modal-backdrop" onClick={onClose}>
      <div className="settings-modal" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="settings-modal-close" aria-label="关闭" onClick={onClose}>×</button>
        {children}
      </div>
    </div>
  );
}
