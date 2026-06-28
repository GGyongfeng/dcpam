import * as THREE from "three";

import visualToml from "./device_visual.toml?raw";
import { parseToml } from "./parsers.js";

const DEVICE_VISUAL = parseToml(visualToml).device_visual || {};

export const COLORS = {
  frontVirtual: 0xd97706,
  rearVirtual: 0x111114,
  real: 0x6b7280,
  imagePlane: 0x2563eb,
  reflectionPlane: 0x7c3aed,
  virtualPlane: 0x0891b2,
  frame: 0xd97706,
  cameraFront: 0xd97706,
  cameraRear: 0x374151,
};

export function buildGeometry(config, algorithm = {}) {
  const calibration = config.calibration || config;
  const frontAxis = makeOpticalAxis("C1 光轴", [0, 0, 0], [0, 0, 1], COLORS.cameraFront);
  const device = makeDeviceGeometry(config.device?.geometry || {});
  const deviceAlignment = makeDeviceAlignment(
    algorithm.imageAlignment || "pnp",
    calibration,
    device,
  );
  const rearDisplayTransform = makeRearCameraDisplayTransform(
    calibration,
    device,
    deviceAlignment,
  );
  const rearAxis = makeOpticalAxis(
    "C2 光轴",
    rearDisplayTransform.transformPoint([0, 0, 0]),
    rearDisplayTransform.transformNormal([0, 0, 1]),
    COLORS.cameraRear,
  );
  const frames = makeFrames(calibration, rearDisplayTransform);
  const cameras = [
    {
      name: "C1",
      position: { x: 0, y: 0, z: 0 },
      color: COLORS.cameraFront,
      axes: axesFromColumns([1, 0, 0], [0, 1, 0], [0, 0, 1]),
    },
    {
      name: "C2",
      position: toPoint(rearDisplayTransform.transformPoint([0, 0, 0])),
      color: COLORS.cameraRear,
      axes: axesFromColumns(
        rearDisplayTransform.transformNormal([1, 0, 0]),
        rearDisplayTransform.transformNormal([0, 1, 0]),
        rearDisplayTransform.transformNormal([0, 0, 1]),
      ),
    },
  ];
  const planes = makeOpticalPlanePatches(
    calibration,
    device,
    deviceAlignment,
    frontAxis,
    rearAxis,
    rearDisplayTransform,
  );

  return {
    device,
    deviceAlignment,
    planes,
    frames,
    rearCameraDisplayTransform: rearDisplayTransform,
    opticalAxes: [frontAxis, rearAxis],
    cameras,
    coordinateFrames: makeCoordinateFrames(deviceAlignment, cameras, frames),
  };
}

function axesFromColumns(xAxis, yAxis, zAxis) {
  return {
    x: toPoint(unit(xAxis)),
    y: toPoint(unit(yAxis)),
    z: toPoint(unit(zAxis)),
  };
}

function makeCoordinateFrames(deviceAlignment, cameras, frames) {
  const localFrame = frames[1] || frames[0];
  return [
    {
      name: "设备坐标系",
      origin: toPoint(deviceAlignment.transformPoint([0, 0, 0])),
      axes: axesFromColumns(
        deviceAlignment.transformNormal([1, 0, 0]),
        deviceAlignment.transformNormal([0, 1, 0]),
        deviceAlignment.transformNormal([0, 0, 1]),
      ),
      length: 11,
    },
    {
      name: "C1 坐标系",
      origin: cameras[0].position,
      axes: cameras[0].axes,
      length: 11,
    },
    {
      name: "C2 坐标系",
      origin: cameras[1].position,
      axes: cameras[1].axes,
      length: 11,
    },
    localFrame ? {
      name: "局部坐标系(P2)",
      origin: localFrame.origin,
      axes: localFrame.axes,
      length: 9,
    } : null,
  ].filter(Boolean);
}

function makeDeviceAlignment(mode, calibration, device) {
  const frontFrame = device.frames?.[0];
  const sourcePoint = fromPoint(frontFrame?.center || { x: 0, y: 0, z: 0 });
  if (mode === "pnp" && calibration.frame_surfaces?.front_frame_pnp) {
    return makeTransformFromAxes(
      "PnP",
      sourcePoint,
      calibration.frame_surfaces.front_frame_pnp.point,
      calibration.frame_surfaces.front_frame_pnp.x_axis,
      calibration.frame_surfaces.front_frame_pnp.y_axis,
      calibration.frame_surfaces.front_frame_pnp.normal,
    );
  }
  return makeTransformFromAxes("PnP", sourcePoint, sourcePoint, [1, 0, 0], [0, 1, 0], [0, 0, 1]);
}

function makeRearCameraDisplayTransform(calibration, device, alignment) {
  const rearFrame = device.frames?.[1];
  const surface = calibration.frame_surfaces?.rear_frame_pnp;
  if (!rearFrame || !surface) {
    throw new Error("config.toml 缺少 rear_frame_pnp 或 device.geometry.rear_frame，无法构建后相机显示变换");
  }
  const targetPoint = alignment.transformPoint(fromPoint(rearFrame.center));
  const targetAxes = {
    x: alignment.transformNormal([1, 0, 0]),
    y: alignment.transformNormal([0, 1, 0]),
    z: alignment.transformNormal(fromPoint(rearFrame.normal)),
  };
  return makeTransformBetweenAxes(
    "P2 PnP-设备面对齐",
    surface.point || [0, 0, 0],
    [surface.x_axis || [1, 0, 0], surface.y_axis || [0, 1, 0], surface.normal || [0, 0, 1]],
    targetPoint,
    [targetAxes.x, targetAxes.y, targetAxes.z],
  );
}

function makeTransformFromAxes(label, sourcePoint, targetPoint, xAxis, yAxis, zAxis) {
  const x = unit(xAxis);
  const y = unit(yAxis);
  const z = unit(zAxis);
  const target = targetPoint.map(Number);
  const source = sourcePoint.map(Number);
  const transformVector = (vector) => add3(add3(scale3(x, vector[0]), scale3(y, vector[1])), scale3(z, vector[2]));
  const transformPoint = (point) => add3(target, transformVector(subtract(point, source)));
  return {
    label,
    matrix: [
      [x[0], y[0], z[0], target[0] - dot([x[0], y[0], z[0]], source)],
      [x[1], y[1], z[1], target[1] - dot([x[1], y[1], z[1]], source)],
      [x[2], y[2], z[2], target[2] - dot([x[2], y[2], z[2]], source)],
      [0, 0, 0, 1],
    ],
    transformNormal: (normal) => unit(transformVector(normal)),
    transformPoint,
  };
}

function makeTransformBetweenAxes(label, sourcePoint, sourceAxes, targetPoint, targetAxes) {
  const sourceBasis = basisMatrix(sourceAxes);
  const targetBasis = basisMatrix(targetAxes);
  const rotation = matrixMul3(targetBasis, transpose3(sourceBasis));
  const source = sourcePoint.map(Number);
  const target = targetPoint.map(Number);
  const offset = subtract(target, matrixVectorMul(rotation, source));
  const transformPoint = (point) => add3(matrixVectorMul(rotation, point), offset);
  const transformNormal = (normal) => unit(matrixVectorMul(rotation, normal));
  return {
    label,
    matrix: [
      [rotation[0][0], rotation[0][1], rotation[0][2], offset[0]],
      [rotation[1][0], rotation[1][1], rotation[1][2], offset[1]],
      [rotation[2][0], rotation[2][1], rotation[2][2], offset[2]],
      [0, 0, 0, 1],
    ],
    transformNormal,
    transformPoint,
  };
}

function basisMatrix(axes) {
  const x = unit(axes[0]);
  const ySeed = unit(axes[1]);
  const z = unit(axes[2]);
  const y = unit(cross(z, x));
  if (Math.abs(dot(y, ySeed)) < 0.5) return [x, ySeed, z].map((_, row) => [x[row], ySeed[row], z[row]]);
  return [x, y, z].map((_, row) => [x[row], y[row], z[row]]);
}

function makeDeviceGeometry(raw) {
  const visual = DEVICE_VISUAL;
  const viewFrame = makeViewFrameSpec(raw.view_frame || {}, visual.view_frame || {});
  return {
    basePlate: makeBasePlateSpec(visual.base_plate || {}),
    frostedGlass: { thickness: numberOr(visual.frosted_glass?.thickness_mm, 3) },
    frames: [
      makeDeviceFrame("front", raw.front_frame || {}, viewFrame, 0),
      makeDeviceFrame("rear", raw.rear_frame || {}, viewFrame, 80),
    ],
    probeRod: makeProbeRodSpec(raw.probe_rod || {}, visual.probe_rod || {}),
    reflections: [
      makeReflectionSpec("front", raw.front_reflection || {}, visual.reflection || {}, 0),
      makeReflectionSpec("rear", raw.rear_reflection || {}, visual.reflection || {}, 80),
    ],
    viewFrame,
  };
}

function makeViewFrameSpec(raw, visual) {
  return {
    innerHeight: numberOr(raw.height_mm, 17),
    innerRadius: numberOr(visual.inner_radius_mm, 1.5),
    innerWidth: numberOr(raw.width_mm, 22),
    outerHeight: numberOr(visual.outer_height_mm, 47),
    outerRadius: numberOr(visual.outer_radius_mm, 2.5),
    outerWidth: numberOr(visual.outer_width_mm, 46),
    thickness: numberOr(visual.thickness_mm, 2),
  };
}

function makeBasePlateSpec(raw) {
  return {
    cornerRadius: numberOr(raw.corner_radius_mm, 3),
    xMin: numberOr(raw.x_range?.[0], -23),
    xMax: numberOr(raw.x_range?.[1], 105),
    yMin: numberOr(raw.y_range?.[0], 23.5),
    yMax: numberOr(raw.y_range?.[1], 29.5),
    zMin: numberOr(raw.z_range?.[0], -132),
    zMax: numberOr(raw.z_range?.[1], 42),
  };
}

function makeDeviceFrame(label, raw, viewFrame, fallbackX) {
  const center = pointFromArray(raw.point, [fallbackX, 0, 0]);
  const normal = pointFromArray(raw.normal, [0, 0, 1]);
  return {
    center,
    d: -dot(fromPoint(normal), fromPoint(center)),
    label,
    normal,
    outerCorners: frameCorners(center, viewFrame.outerWidth, viewFrame.outerHeight).map(toPoint),
    rectCorners: pointListFromArray(raw.rect_corners, frameCorners(center, viewFrame.innerWidth, viewFrame.innerHeight)),
  };
}

function makeProbeRodSpec(raw, visual) {
  const root = pointFromArray(raw.root, [41, 37, -132]);
  const direction = unit(fromPoint(pointFromArray(visual.direction, [0, 0, -1])));
  const length = numberOr(raw.length_mm, 109);
  const target = toPoint(add3(fromPoint(root), scale3(direction, length)));
  return {
    connectorLength: numberOr(visual.connector_length_mm, 8),
    connectorRadius: numberOr(visual.connector_radius_mm, 13),
    length,
    rodRadius: numberOr(visual.rod_radius_mm, 0.9),
    root,
    target,
    tipHeight: numberOr(visual.tip_height_mm, 5),
  };
}

function makeReflectionSpec(label, raw, visual, fallbackX) {
  const point = pointFromArray(raw.point, [fallbackX, 0, 23]);
  const normal = pointFromArray(raw.normal, [1 / Math.SQRT2, 0, 1 / Math.SQRT2]);
  return {
    d: -dot(fromPoint(normal), fromPoint(point)),
    height: numberOr(visual.height_mm, 47),
    label,
    normal,
    point,
    thickness: numberOr(visual.thickness_mm, 1),
    thicknessDirection: pointFromArray(visual.thickness_direction, [0, 0, 1]),
    width: numberOr(visual.width_mm, 21.2),
  };
}

function frameCorners(center, width, height) {
  const halfWidth = width / 2;
  const halfHeight = height / 2;
  return [
    [center.x - halfWidth, center.y - halfHeight, center.z],
    [center.x + halfWidth, center.y - halfHeight, center.z],
    [center.x + halfWidth, center.y + halfHeight, center.z],
    [center.x - halfWidth, center.y + halfHeight, center.z],
  ];
}

export function pointFromRow(row, prefix, suffix) {
  const jsonCell = row[`${prefix}_point_device_mm`];
  if (typeof jsonCell === "string" && jsonCell.trim().startsWith("[")) {
    try {
      const parsed = JSON.parse(jsonCell);
      if (Array.isArray(parsed) && parsed.length >= 3 && parsed.every((value) => Number.isFinite(Number(value)))) {
        return { x: Number(parsed[0]), y: Number(parsed[1]), z: Number(parsed[2]), space: "device" };
      }
    } catch {
      // fall through to legacy column layout
    }
  }
  const x = Number(row[`${prefix}_x_${suffix}`]);
  const y = Number(row[`${prefix}_y_${suffix}`]);
  const z = Number(row[`${prefix}_z_${suffix}`]);
  if (![x, y, z].every(Number.isFinite)) return null;
  return { x, y, z, space: suffix === "cr" ? "camera_rear" : "camera_front" };
}

export function toVector3(point) {
  return new THREE.Vector3(point.x, point.y, point.z);
}

export function planeColor(kind) {
  if (kind === "image") return COLORS.imagePlane;
  if (kind === "reflection") return COLORS.reflectionPlane;
  return COLORS.virtualPlane;
}

function makeOpticalAxis(label, origin, direction, color) {
  const unitDirection = unit(direction);
  const length = 48;
  return {
    label,
    color,
    origin: toPoint(origin),
    direction: toPoint(unitDirection),
    end: toPoint(add3(origin, scale3(unitDirection, length))),
  };
}

function makeOpticalPlanePatches(
  calibration,
  device,
  deviceAlignment,
  frontAxis,
  rearAxis,
  rearDisplayTransform,
) {
  const planes = [];
  const imagePlanes = makeImagePlanePair(
    calibration,
    rearDisplayTransform,
  );
  const reflectionPlanes = makeReflectionPlanePair(
    device,
    deviceAlignment,
  );

  addPlaneSet(planes, "P1", "C1", imagePlanes.front, reflectionPlanes.front, frontAxis);
  addPlaneSet(planes, "P2", "C2", imagePlanes.rear, reflectionPlanes.rear, rearAxis);
  return planes;
}

function makeImagePlanePair(calibration, rearTransform) {
  return {
    front: frameSurfaceToPlane(calibration.frame_surfaces?.front_frame_pnp, "pnp_frame_pose"),
    rear: transformOptionalPlane(
      frameSurfaceToPlane(calibration.frame_surfaces?.rear_frame_pnp, "pnp_frame_pose"),
      rearTransform.transformPoint,
      rearTransform.transformNormal,
    ),
  };
}

function makeReflectionPlanePair(device, alignment) {
  return {
    front: deviceReflectionToPlane(device.reflections?.[0], alignment),
    rear: deviceReflectionToPlane(device.reflections?.[1], alignment),
  };
}

function frameSurfaceToPlane(surface, method) {
  if (!surface) return null;
  const normal = unit(surface.normal || [0, 0, 1]);
  const point = (surface.point || [0, 0, 0]).map(Number);
  const corners = pointListFromArray(surface.corners, []);
  return {
    corners: corners.length === 4 && corners.every(isFinitePoint) ? corners : null,
    d: Number.isFinite(Number(surface.d)) ? Number(surface.d) : -dot(normal, point),
    height: Number(surface.height_mm || 17),
    method,
    normal,
    point,
    reprojectionErrorPx: Number(surface.reprojection_error_px || 0),
    width: Number(surface.width_mm || 22),
    xAxis: surface.x_axis ? toPoint(unit(surface.x_axis)) : null,
    yAxis: surface.y_axis ? toPoint(unit(surface.y_axis)) : null,
  };
}

function deviceFrameToPlane(frame, alignment) {
  if (!frame) return null;
  const point = alignment.transformPoint(fromPoint(frame.center));
  const normal = alignment.transformNormal(fromPoint(frame.normal));
  return {
    d: -dot(normal, point),
    method: "dcpam_device_geometry",
    normal,
    point,
  };
}

function deviceReflectionToPlane(reflection, alignment) {
  if (!reflection) return null;
  const point = alignment.transformPoint(fromPoint(reflection.point));
  const normal = alignment.transformNormal(fromPoint(reflection.normal));
  return {
    d: -dot(normal, point),
    method: "dcpam_reflection_geometry",
    normal,
    point,
  };
}

function transformOptionalPlane(plane, transformPoint, transformNormal) {
  return plane ? transformPlane(plane, transformPoint, transformNormal) : null;
}

function addPlaneSet(planes, planeId, cameraId, imagePlane, reflectionPlane, axis) {
  if (imagePlane) {
    planes.push(makePlane(`${planeId} ${planeSourceName(imagePlane.method)}实像面`, "image", imagePlane, opticalIntersection(axis, imagePlane)));
  }
  if (reflectionPlane) {
    planes.push(makePlane(`${cameraId} ${reflectionSourceName(reflectionPlane.method)}反射面`, "reflection", reflectionPlane, opticalIntersection(axis, reflectionPlane)));
  }
  if (imagePlane && reflectionPlane) {
    const imagePatch = makePlane(`${planeId} 虚像面`, "virtual", imagePlane, opticalIntersection(axis, imagePlane));
    planes.push(mirrorPlanePatch(imagePatch, reflectionPlane));
  }
}

function planeSourceName(method) {
  if (method === "pnp_frame_pose") return "PnP ";
  if (method === "dcpam_device_geometry") return "设备 ";
  return "PnP ";
}

function reflectionSourceName(method) {
  if (method === "dcpam_reflection_geometry") return "设备几何 ";
  return "设备几何 ";
}

function makePlane(label, kind, plane, centerInput = plane.point) {
  const center = centerInput || plane.point;
  const point = toPoint(center);
  const normal = unit(plane.normal);
  const axes = {
    u: plane.xAxis ? unit(fromPoint(plane.xAxis)) : planeAxes(normal).u,
    v: plane.yAxis ? unit(fromPoint(plane.yAxis)) : planeAxes(normal).v,
  };
  const size = kind === "reflection" ? 11 : 8.5;
  const corners = plane.corners || planePatchCorners(center, axes, size);
  return {
    axes: {
      x: toPoint(axes.u),
      y: toPoint(axes.v),
      z: toPoint(normal),
    },
    d: plane.d,
    height: plane.height,
    label,
    kind,
    method: plane.method || null,
    point,
    normal: toPoint(normal),
    corners,
    reprojectionErrorPx: plane.reprojectionErrorPx,
    width: plane.width,
  };
}

function mirrorPlanePatch(imagePatch, reflectionPlane) {
  const point = mirrorPoint(fromPoint(imagePatch.point), reflectionPlane);
  const normal = unit(reflectVector(fromPoint(imagePatch.normal), reflectionPlane.normal));
  const corners = imagePatch.corners.map((corner) => toPoint(mirrorPoint(fromPoint(corner), reflectionPlane)));
  return {
    axes: {
      x: toPoint(unit(subtract(fromPoint(corners[1]), fromPoint(corners[0])))),
      y: toPoint(unit(subtract(fromPoint(corners[3]), fromPoint(corners[0])))),
      z: toPoint(normal),
    },
    label: imagePatch.label,
    point: toPoint(point),
    d: -dot(normal, point),
    kind: "virtual",
    method: "mirror_reflection",
    normal: toPoint(normal),
    corners,
  };
}

function opticalIntersection(axis, plane) {
  const origin = fromPoint(axis.origin);
  const direction = fromPoint(axis.direction);
  const normal = unit(plane.normal);
  const denominator = dot(normal, direction);
  if (Math.abs(denominator) < 1e-8) return plane.point;
  const distance = -(dot(normal, origin) + plane.d) / denominator;
  return add3(origin, scale3(direction, distance));
}

function makeFrames(calibration, rearTransform) {
  const frames = [];
  const surfaces = calibration.frame_surfaces || {};
  if (surfaces.front_frame_pnp) {
    frames.push(makeFrameSurface("P1 PnP 实像面", surfaces.front_frame_pnp, (point) => point, (vector) => vector));
  }
  if (surfaces.rear_frame_pnp) {
    frames.push(makeFrameSurface("P2 PnP 实像面", surfaces.rear_frame_pnp, rearTransform.transformPoint, rearTransform.transformNormal));
  }
  return frames;
}

function makeFrameSurface(label, surface, transformPoint, transformVector) {
  const corners = pointListFromArray(surface.corners, []).map((point) => fromPoint(point));
  const transformedCorners = corners.map((point) => transformPoint(point));
  const origin = transformPoint(surface.point || averagePoints(corners));
  const normal = unit(transformVector(surface.normal || [0, 0, 1]));
  const xAxis = surface.x_axis
    ? unit(transformVector(surface.x_axis))
    : transformedCorners.length > 1
      ? unit(subtract(transformedCorners[1], transformedCorners[0]))
      : [1, 0, 0];
  const yAxis = surface.y_axis
    ? unit(transformVector(surface.y_axis))
    : transformedCorners.length > 3
      ? unit(subtract(transformedCorners[3], transformedCorners[0]))
      : [0, 1, 0];
  return {
    axes: { x: toPoint(xAxis), y: toPoint(yAxis), z: toPoint(normal) },
    corners: transformedCorners.map(toPoint),
    height: Number(surface.height_mm || 17),
    kind: "frame",
    label,
    method: surface.method || "pnp_frame_pose",
    origin: toPoint(origin),
    reprojectionErrorPx: Number(surface.reprojection_error_px || 0),
    width: Number(surface.width_mm || 22),
  };
}

function averagePoints(points) {
  if (!points.length) return [0, 0, 0];
  const sum = points.reduce((acc, point) => add3(acc, point), [0, 0, 0]);
  return scale3(sum, 1 / points.length);
}

function transformPlane(plane, transformPoint, transformNormal) {
  const point = transformPoint(plane.point);
  const normal = unit(transformNormal(plane.normal));
  return {
    corners: plane.corners?.map((corner) => toPoint(transformPoint(fromPoint(corner)))) || null,
    d: -dot(normal, point),
    height: plane.height,
    method: plane.method || null,
    normal,
    point,
    reprojectionErrorPx: plane.reprojectionErrorPx,
    width: plane.width,
    xAxis: plane.xAxis ? toPoint(unit(transformNormal(fromPoint(plane.xAxis)))) : null,
    yAxis: plane.yAxis ? toPoint(unit(transformNormal(fromPoint(plane.yAxis)))) : null,
  };
}

function planePatchCorners(center, axes, size) {
  return [
    add3(add3(center, scale3(axes.u, -size)), scale3(axes.v, -size)),
    add3(add3(center, scale3(axes.u, size)), scale3(axes.v, -size)),
    add3(add3(center, scale3(axes.u, size)), scale3(axes.v, size)),
    add3(add3(center, scale3(axes.u, -size)), scale3(axes.v, size)),
  ].map(toPoint);
}

function mirrorPoint(point, plane) {
  const normal = unit(plane.normal);
  const signed = dot(normal, point) + plane.d;
  return subtract(point, scale3(normal, 2 * signed));
}

function reflectVector(vector, normalInput) {
  const normal = unit(normalInput);
  return subtract(vector, scale3(normal, 2 * dot(vector, normal)));
}

function planeAxes(normal) {
  const n = unit(normal);
  const helper = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  const u = unit(cross(helper, n));
  const v = unit(cross(n, u));
  return { u, v };
}

function identity3() {
  return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
}

function transpose3(matrix) {
  return matrix[0].map((_, col) => matrix.map((row) => row[col]));
}

function matrixVectorMul(matrix, vector) {
  return matrix.map((row) => dot(row, vector));
}

function matrixMul3(first, second) {
  return first.map((row) => second[0].map((_, col) => dot(row, [second[0][col], second[1][col], second[2][col]])));
}

function add3(first, second) {
  return first.map((value, index) => value + second[index]);
}

function subtract(first, second) {
  return first.map((value, index) => value - second[index]);
}

function scale3(vector, scale) {
  return vector.map((value) => value * scale);
}

function dot(first, second) {
  return first.reduce((sum, value, index) => sum + value * second[index], 0);
}

function cross(first, second) {
  return [
    first[1] * second[2] - first[2] * second[1],
    first[2] * second[0] - first[0] * second[2],
    first[0] * second[1] - first[1] * second[0],
  ];
}

function unit(vector) {
  const length = Math.hypot(...vector);
  if (!Number.isFinite(length) || length < 1e-12) {
    throw new Error(`无效方向向量: ${JSON.stringify(vector)}`);
  }
  return vector.map((value) => value / length);
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function pointFromArray(value, fallback) {
  const source = Array.isArray(value) ? value : fallback;
  if (!Array.isArray(source)) {
    throw new Error(`缺少三维点: ${JSON.stringify(value)}`);
  }
  return toPoint(source.map((item) => Number(item)));
}

function pointListFromArray(value, fallback) {
  const source = Array.isArray(value) && value.length ? value : fallback;
  return source.map((point) => pointFromArray(point, point));
}

function isFinitePoint(point) {
  return [point.x, point.y, point.z].every(Number.isFinite);
}

function toPoint(vector) {
  const point = { x: Number(vector[0]), y: Number(vector[1]), z: Number(vector[2]) };
  if (!isFinitePoint(point)) {
    throw new Error(`无效三维点: ${JSON.stringify(vector)}`);
  }
  return point;
}

function fromPoint(point) {
  if (!isFinitePoint(point)) {
    throw new Error(`无效三维点: ${JSON.stringify(point)}`);
  }
  return [point.x, point.y, point.z];
}
