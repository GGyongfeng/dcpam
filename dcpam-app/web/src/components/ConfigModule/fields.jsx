import React, { useEffect, useRef, useState } from "react";

import { coerce } from "./utils.js";

/**
 * 可折叠 section（如 pipeline.spot_extraction、device.geometry、calibration）。
 */
export function Section({ title, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="config-section">
      <button
        type="button"
        className={`config-section-header ${open ? "open" : ""}`}
        onClick={() => setOpen(!open)}
      >
        <span className="caret">{open ? "▾" : "▸"}</span>
        <span>{title}</span>
      </button>
      {open && <div className="config-section-body">{children}</div>}
    </div>
  );
}

export function Subsection({ title, children }) {
  return (
    <div className="config-subsection">
      <div className="config-subsection-title">{title}</div>
      {children}
    </div>
  );
}

/**
 * 单元格：未聚焦时用 span 显示（可省略号 + hover 看完整），点击/聚焦时切 input 编辑。
 */
function EditableCell({ type, value, onChange, align = "left" }) {
  const [editing, setEditing] = useState(false);
  const inputRef = useRef(null);
  const display = value === undefined || value === null ? "" : String(value);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  if (!editing) {
    return (
      <span
        className={`config-cell config-cell-display config-cell-${align}`}
        tabIndex={0}
        title={display}
        onClick={() => setEditing(true)}
        onFocus={() => setEditing(true)}
      >
        {display || <span className="config-cell-placeholder">—</span>}
      </span>
    );
  }

  return (
    <input
      ref={inputRef}
      className={`config-cell config-cell-input config-cell-${align}`}
      type={type === "text" ? "text" : "number"}
      step={type === "int" ? 1 : "any"}
      value={display}
      onChange={(event) => onChange(coerce(event.target.value, type))}
      onBlur={() => setEditing(false)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === "Escape") {
          event.currentTarget.blur();
        }
      }}
    />
  );
}

/**
 * 单字段：窄 label + 弹性宽输入框。
 */
export function Field({ label, type, value, onChange }) {
  return (
    <label className="config-field">
      <span className="config-label" title={label}>{label}</span>
      <EditableCell type={type} value={value} onChange={onChange} align="left" />
    </label>
  );
}

/**
 * 向量字段：label + 多个 EditableCell 等分剩余空间。
 */
export function VectorField({ label, length, type = "float", value, onChange }) {
  const arr = Array.isArray(value) ? value : new Array(length).fill(0);
  return (
    <div className="config-vector">
      <span className="config-label" title={label}>{label}</span>
      <div className="config-vector-inputs" style={{ "--n": length }}>
        {arr.slice(0, length).map((v, i) => (
          <EditableCell
            key={i}
            type={type}
            value={v}
            onChange={(nv) => {
              const next = [...arr];
              next[i] = nv;
              onChange(next);
            }}
            align="right"
          />
        ))}
      </div>
    </div>
  );
}

/**
 * 矩阵字段：3×3 旋转矩阵专用。
 */
export function MatrixField({ label, rows, cols, value, onChange }) {
  const mat = Array.isArray(value)
    ? value
    : Array.from({ length: rows }, () => new Array(cols).fill(0));
  return (
    <div className="config-matrix">
      <span className="config-label" title={label}>{label}</span>
      <div className="config-matrix-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {mat.slice(0, rows).map((row, i) => (
          (Array.isArray(row) ? row : new Array(cols).fill(0)).slice(0, cols).map((v, j) => (
            <EditableCell
              key={`${i}-${j}`}
              type="float"
              value={v}
              onChange={(nv) => {
                const next = mat.map((r) => [...(Array.isArray(r) ? r : new Array(cols).fill(0))]);
                next[i][j] = nv;
                onChange(next);
              }}
              align="right"
            />
          ))
        ))}
      </div>
    </div>
  );
}
