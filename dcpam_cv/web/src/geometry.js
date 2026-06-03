import * as THREE from "three";

export const COLORS = {
  frontVirtual: 0xe7c59a,
  rearVirtual: 0xf3f3f3,
  real: 0x8a8a8a,
  imagePlane: 0x949494,
  reflectionPlane: 0x5a5a5a,
  virtualPlane: 0xc1c1c1,
  cameraFront: 0xe7c59a,
  cameraRear: 0xc1c1c1,
};

export function buildGeometry(config) {
  const calibration = config.calibration || config;
  const transform = calibration.transform || {};
  const rotation = transform.r_rear_from_front || identity3();
  const translation = transform.t_rear_from_front || [0, 0, 0];
  const rearToFront = (point) => matrixVectorMul(transpose3(rotation), subtract(point, translation));
  const rearNormalToFront = (normal) => matrixVectorMul(transpose3(rotation), normal);

  const raw = calibration.planes || {};
  const planes = [];
  if (raw.front_image_real) planes.push(makePlane("front image", "image", raw.front_image_real));
  if (raw.front_reflection) planes.push(makePlane("front reflection", "reflection", raw.front_reflection));
  if (raw.rear_image_real) {
    planes.push(makePlane("rear image", "image", transformPlane(raw.rear_image_real, rearToFront, rearNormalToFront)));
  }
  if (raw.rear_reflection) {
    planes.push(makePlane("rear reflection", "reflection", transformPlane(raw.rear_reflection, rearToFront, rearNormalToFront)));
  }
  if (raw.front_image_real && raw.front_reflection) {
    planes.push(makePlane("front virtual image", "virtual", mirrorPlane(raw.front_image_real, raw.front_reflection)));
  }
  if (raw.rear_image_real && raw.rear_reflection) {
    const rearVirtual = mirrorPlane(raw.rear_image_real, raw.rear_reflection);
    planes.push(makePlane("rear virtual image", "virtual", transformPlane(rearVirtual, rearToFront, rearNormalToFront)));
  }

  return {
    planes,
    cameras: [
      { name: "C1", position: { x: 0, y: 0, z: 0 }, color: COLORS.cameraFront },
      { name: "C2", position: toPoint(rearToFront([0, 0, 0])), color: COLORS.cameraRear },
    ],
  };
}

export function pointFromRow(row, prefix, suffix) {
  const x = Number(row[`${prefix}_x_${suffix}`]);
  const y = Number(row[`${prefix}_y_${suffix}`]);
  const z = Number(row[`${prefix}_z_${suffix}`]);
  if (![x, y, z].every(Number.isFinite)) return null;
  return { x, y, z };
}

export function toVector3(point) {
  return new THREE.Vector3(point.x, point.y, point.z);
}

export function planeColor(kind) {
  if (kind === "image") return COLORS.imagePlane;
  if (kind === "reflection") return COLORS.reflectionPlane;
  return COLORS.virtualPlane;
}

function makePlane(label, kind, plane) {
  const point = toPoint(plane.point);
  const normal = unit(plane.normal);
  const axes = planeAxes(normal);
  const size = kind === "reflection" ? 12 : 9;
  const corners = [
    add3(add3(plane.point, scale3(axes.u, -size)), scale3(axes.v, -size)),
    add3(add3(plane.point, scale3(axes.u, size)), scale3(axes.v, -size)),
    add3(add3(plane.point, scale3(axes.u, size)), scale3(axes.v, size)),
    add3(add3(plane.point, scale3(axes.u, -size)), scale3(axes.v, size)),
  ].map(toPoint);
  return { label, kind, point, normal: toPoint(normal), corners };
}

function transformPlane(plane, transformPoint, transformNormal) {
  const point = transformPoint(plane.point);
  const normal = unit(transformNormal(plane.normal));
  return { point, normal, d: -dot(normal, point) };
}

function mirrorPlane(imagePlane, reflectionPlane) {
  const point = mirrorPoint(imagePlane.point, reflectionPlane);
  const normal = reflectVector(imagePlane.normal, reflectionPlane.normal);
  return { point, normal, d: -dot(normal, point) };
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
  return vector.map((value) => value / length);
}

function toPoint(vector) {
  return { x: vector[0], y: vector[1], z: vector[2] };
}
