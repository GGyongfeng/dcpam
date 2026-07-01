import React, { useCallback, useEffect, useRef } from "react";

/**
 * 通用面板宽度 hook。为 CSS 变量 (cssVar) 提供拖动 + localStorage 持久化。
 *
 * @param {object} opts
 * @param {string} opts.storageKey    localStorage key
 * @param {string} opts.cssVar        CSS 变量名（如 "--sample-width"）
 * @param {number} opts.defaultWidth
 * @param {number} opts.minWidth
 * @param {number} opts.maxWidth
 * @param {"right"|"left"} opts.side  面板贴哪一边：右栏往左拖变宽（dx<0 → w+）；左栏往右拖变宽（dx>0 → w+）
 */
export function usePanelWidth({
  storageKey,
  cssVar,
  defaultWidth,
  minWidth,
  maxWidth,
  side = "right",
}) {
  const widthRef = useRef(defaultWidth);

  const applyWidth = useCallback((width) => {
    document.documentElement.style.setProperty(cssVar, `${width}px`);
  }, [cssVar]);

  const setWidth = useCallback((next) => {
    const clamped = Math.min(maxWidth, Math.max(minWidth, next));
    widthRef.current = clamped;
    applyWidth(clamped);
    localStorage.setItem(storageKey, String(Math.round(clamped)));
  }, [applyWidth, storageKey, minWidth, maxWidth]);

  useEffect(() => {
    const raw = Number(localStorage.getItem(storageKey));
    const initial = Number.isFinite(raw)
      ? Math.min(maxWidth, Math.max(minWidth, raw))
      : defaultWidth;
    widthRef.current = initial;
    applyWidth(initial);
  }, [applyWidth, storageKey, defaultWidth, minWidth, maxWidth]);

  const startDrag = useCallback((event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthRef.current;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const sign = side === "right" ? -1 : 1;
    const onMove = (e) => {
      const dx = e.clientX - startX;
      setWidth(startWidth + sign * dx);
    };
    const onUp = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, [setWidth, side]);

  return { startDrag };
}

export function PanelResizer({ startDrag, className = "panel-resizer" }) {
  return (
    <div
      className={className}
      role="separator"
      aria-orientation="vertical"
      aria-label="拖动调整宽度"
      onPointerDown={startDrag}
    />
  );
}

// 兼容旧 import
export const useSampleDrawerWidth = () =>
  usePanelWidth({
    storageKey: "dcpam.viewer.sampleWidth",
    cssVar: "--sample-width",
    defaultWidth: 388,
    minWidth: 320,
    maxWidth: 720,
    side: "right",
  });

export const SampleDrawerResizer = ({ startDrag }) => (
  <PanelResizer startDrag={startDrag} className="sample-drawer-resizer" />
);

export const useSidebarWidth = () =>
  usePanelWidth({
    storageKey: "dcpam.viewer.sidebarWidth",
    cssVar: "--left-width",
    defaultWidth: 360,
    minWidth: 320,
    maxWidth: 640,
    side: "left",
  });
