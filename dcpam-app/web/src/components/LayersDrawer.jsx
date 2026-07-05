import React, { useState } from "react";

const LAYER_GROUPS = [
  {
    title: "设备结构",
    groups: [
      {
        title: "器件",
        items: [
          ["frontViewFrame", "前取景框"],
          ["rearViewFrame", "后取景框"],
          ["frontFrostedGlass", "前毛玻璃"],
          ["rearFrostedGlass", "后毛玻璃"],
          ["frontReflectionMirror", "前反射镜"],
          ["rearReflectionMirror", "后反射镜"],
          ["basePlate", "底座"],
          ["probeRod", "测量探杆"],
        ],
      },
    ],
  },
  {
    title: "相机坐标系内容",
    groups: [
      {
        title: "面类",
        items: [
          ["imagePlanes", "实像面"],
          ["reflectionPlanes", "反射面"],
          ["virtualPlanes", "虚像面"],
        ],
      },
      {
        title: "点类",
        items: [
          ["realPoints", "实像点"],
          ["frontVirtual", "前虚像点"],
          ["rearVirtual", "后虚像点"],
          ["laserLines", "激光线"],
        ],
      },
      {
        title: "其他",
        items: [
          ["cameras", "相机位置"],
          ["opticalAxes", "光轴"],
          ["localAxes", "局部坐标系"],
          ["labels", "标签"],
        ],
      },
    ],
  },
];

export const DEFAULT_LAYERS = {
  cameras: true,
  frontViewFrame: true,
  rearViewFrame: true,
  frontFrostedGlass: true,
  rearFrostedGlass: true,
  frontReflectionMirror: true,
  rearReflectionMirror: true,
  basePlate: true,
  probeRod: true,
  opticalAxes: true,
  localAxes: true,
  imagePlanes: true,
  reflectionPlanes: true,
  virtualPlanes: true,
  frontVirtual: true,
  rearVirtual: true,
  realPoints: false,
  laserLines: true,
  labels: true,
};

export function LayersDrawer({ layers, setLayers }) {
  const [open, setOpen] = useState(false);
  const setLayer = (key, value) => setLayers((current) => ({ ...current, [key]: value }));
  const setLayerKeys = (keys, value) =>
    setLayers((current) => ({ ...current, ...Object.fromEntries(keys.map((key) => [key, value])) }));
  const setAllLayers = (value) =>
    setLayers(Object.fromEntries(Object.keys(DEFAULT_LAYERS).map((key) => [key, value])));

  if (!open) {
    return (
      <button
        type="button"
        className="layers-drawer-toggle"
        aria-label="打开图层面板"
        onClick={() => setOpen(true)}
      >
        ⊞
      </button>
    );
  }
  return (
    <div className="layers-drawer">
      <div className="layers-drawer-header">
        <h3>图层</h3>
        <button
          type="button"
          className="layers-drawer-close"
          aria-label="关闭"
          onClick={() => setOpen(false)}
        >×</button>
      </div>
      <div className="layers-drawer-actions">
        <button type="button" onClick={() => setAllLayers(true)}>全部显示</button>
        <button type="button" onClick={() => setAllLayers(false)}>全部隐藏</button>
      </div>
      <div className="layer-groups">
        {LAYER_GROUPS.map((section) => (
          <div className="layer-section" key={section.title}>
            <div className="layer-module-title">
              <h4>{section.title}</h4>
              <div className="mini-tools">
                <button type="button" title={`${section.title}全部显示`} onClick={() => setLayerKeys(layerKeys(section), true)}>✓</button>
                <button type="button" title={`${section.title}全部隐藏`} onClick={() => setLayerKeys(layerKeys(section), false)}>×</button>
              </div>
            </div>
            {section.groups.map((group) => (
              <div className="layer-subgroup" key={group.title}>
                <span>{group.title}</span>
                <div className="checks">
                  {group.items.map(([key, label]) => (
                    <label className="check" key={key}>
                      <input
                        type="checkbox"
                        checked={Boolean(layers[key])}
                        onChange={(event) => setLayer(key, event.target.checked)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function layerKeys(section) {
  return section.groups.flatMap((group) => group.items.map(([key]) => key));
}
