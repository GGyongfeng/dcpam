import React from "react";

import { Field, MatrixField, Section, Subsection, VectorField } from "./fields.jsx";

/**
 * 主表单：把 controller.draft 分区域渲染为可编辑字段。
 */
export function ConfigForm({ controller }) {
  const { draft, loading, error, uploadError, savedAt, path, patch } = controller;
  if (!draft) {
    return (
      <div className="config-form">
        <div className="config-status">
          {loading ? "正在加载 config.toml..." : error || "等待加载..."}
        </div>
      </div>
    );
  }

  return (
    <div className="config-form">
      {(error || uploadError) && <div className="config-error">{error || uploadError}</div>}
      {savedAt && <div className="config-saved">已保存（{new Date(savedAt).toLocaleTimeString()}）</div>}
      <div className="config-path" title={path}>{path}</div>

      <Section title="pipeline.spot_extraction">
        <Field label="method" type="text"
          value={draft.pipeline?.spot_extraction?.method}
          onChange={(v) => patch(["pipeline", "spot_extraction", "method"], v)} />
        <Field label="gaussian_kernel" type="int"
          value={draft.pipeline?.spot_extraction?.gaussian_kernel}
          onChange={(v) => patch(["pipeline", "spot_extraction", "gaussian_kernel"], v)} />
        <Field label="gaussian_sigma" type="float"
          value={draft.pipeline?.spot_extraction?.gaussian_sigma}
          onChange={(v) => patch(["pipeline", "spot_extraction", "gaussian_sigma"], v)} />
        <Field label="centroid_threshold" type="float"
          value={draft.pipeline?.spot_extraction?.centroid_threshold}
          onChange={(v) => patch(["pipeline", "spot_extraction", "centroid_threshold"], v)} />
      </Section>

      <Section title="device.geometry">
        <Subsection title="front_reflection">
          <VectorField label="point" length={3}
            value={draft.device?.geometry?.front_reflection?.point}
            onChange={(v) => patch(["device", "geometry", "front_reflection", "point"], v)} />
          <VectorField label="normal" length={3}
            value={draft.device?.geometry?.front_reflection?.normal}
            onChange={(v) => patch(["device", "geometry", "front_reflection", "normal"], v)} />
        </Subsection>
        <Subsection title="rear_reflection">
          <VectorField label="point" length={3}
            value={draft.device?.geometry?.rear_reflection?.point}
            onChange={(v) => patch(["device", "geometry", "rear_reflection", "point"], v)} />
          <VectorField label="normal" length={3}
            value={draft.device?.geometry?.rear_reflection?.normal}
            onChange={(v) => patch(["device", "geometry", "rear_reflection", "normal"], v)} />
        </Subsection>
        <Subsection title="probe_rod">
          <VectorField label="root" length={3}
            value={draft.device?.geometry?.probe_rod?.root}
            onChange={(v) => patch(["device", "geometry", "probe_rod", "root"], v)} />
          <Field label="length_mm" type="float"
            value={draft.device?.geometry?.probe_rod?.length_mm}
            onChange={(v) => patch(["device", "geometry", "probe_rod", "length_mm"], v)} />
        </Subsection>
      </Section>

      <Section title="calibration（相机标定 / 标定结果）" defaultOpen={false}>
        {["front_camera", "rear_camera"].map((cam) => (
          <Subsection title={cam} key={cam}>
            <Field label="model" type="text"
              value={draft.calibration?.[cam]?.model}
              onChange={(v) => patch(["calibration", cam, "model"], v)} />
            <VectorField label="focal_lengths" length={2}
              value={draft.calibration?.[cam]?.focal_lengths}
              onChange={(v) => patch(["calibration", cam, "focal_lengths"], v)} />
            <VectorField label="principal_point" length={2}
              value={draft.calibration?.[cam]?.principal_point}
              onChange={(v) => patch(["calibration", cam, "principal_point"], v)} />
            <VectorField label="distortion_coeffs" length={4}
              value={draft.calibration?.[cam]?.distortion_coeffs}
              onChange={(v) => patch(["calibration", cam, "distortion_coeffs"], v)} />
            <VectorField label="resolution" length={2} type="int"
              value={draft.calibration?.[cam]?.resolution}
              onChange={(v) => patch(["calibration", cam, "resolution"], v)} />
          </Subsection>
        ))}
        {["front_frame_pnp", "rear_frame_pnp"].map((surface) => (
          <Subsection title={`frame_surfaces.${surface}`} key={surface}>
            <Field label="method" type="text"
              value={draft.calibration?.frame_surfaces?.[surface]?.method}
              onChange={(v) => patch(["calibration", "frame_surfaces", surface, "method"], v)} />
            <VectorField label="point" length={3}
              value={draft.calibration?.frame_surfaces?.[surface]?.point}
              onChange={(v) => patch(["calibration", "frame_surfaces", surface, "point"], v)} />
            <VectorField label="normal" length={3}
              value={draft.calibration?.frame_surfaces?.[surface]?.normal}
              onChange={(v) => patch(["calibration", "frame_surfaces", surface, "normal"], v)} />
            <Field label="d" type="float"
              value={draft.calibration?.frame_surfaces?.[surface]?.d}
              onChange={(v) => patch(["calibration", "frame_surfaces", surface, "d"], v)} />
          </Subsection>
        ))}
        {["front_camera_to_frame", "rear_camera_to_frame", "rear_to_front"].map((key) => (
          <Subsection title={key} key={key}>
            <MatrixField label="rotation" rows={3} cols={3}
              value={draft.calibration?.[key]?.rotation}
              onChange={(v) => patch(["calibration", key, "rotation"], v)} />
            <VectorField label="translation" length={3}
              value={draft.calibration?.[key]?.translation}
              onChange={(v) => patch(["calibration", key, "translation"], v)} />
          </Subsection>
        ))}
      </Section>
    </div>
  );
}
