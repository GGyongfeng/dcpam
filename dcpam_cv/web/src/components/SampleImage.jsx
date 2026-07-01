import React from "react";

export function SampleImage({ src, title, spot, resolution }) {
  const u = Number(spot?.u);
  const v = Number(spot?.v);
  const width = Number(resolution?.[0]);
  const height = Number(resolution?.[1]);
  const hasOverlay = [u, v, width, height].every(Number.isFinite) && width > 0 && height > 0;
  const inside = hasOverlay && u >= 0 && v >= 0 && u <= width && v <= height;
  const crossArm = Math.max(width, height) * 0.025;
  return (
    <figure className="sample-image">
      <div className="image-frame">
        {src ? (
          <div className="image-stage">
            <img src={src} alt={title} />
            {hasOverlay && (
              <svg
                className="image-overlay"
                viewBox={`0 0 ${width} ${height}`}
                preserveAspectRatio="xMidYMid meet"
              >
                {inside && (
                  <g>
                    <line x1={u - crossArm} y1={v} x2={u + crossArm} y2={v} className="image-cross" />
                    <line x1={u} y1={v - crossArm} x2={u} y2={v + crossArm} className="image-cross" />
                    <circle cx={u} cy={v} r={crossArm * 0.3} className="image-dot" />
                  </g>
                )}
                <text
                  x={inside ? Math.min(u + crossArm * 1.4, width - crossArm * 0.5) : crossArm}
                  y={inside ? Math.max(v - crossArm * 0.6, crossArm * 1.6) : crossArm * 1.6}
                  className="image-label"
                  style={{ fontSize: crossArm * 1.05 }}
                >
                  uv=({u.toFixed(1)}, {v.toFixed(1)})
                </text>
              </svg>
            )}
          </div>
        ) : (
          <span>未找到图片路径</span>
        )}
      </div>
      <figcaption>{title}</figcaption>
    </figure>
  );
}
