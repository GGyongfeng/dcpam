import * as THREE from "three";

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

export function buildGeometry(config) {
  const calibration = config.calibration || config;
  const transform = calibration.transform || {};
  const rotation = transform.r_rear_from_front || identity3();
  const translation = transform.t_rear_from_front || [0, 0, 0];
  const rearToFront = (point) => matrixVectorMul(transpose3(rotation), subtract(point, translation));
  const rearNormalToFront = (normal) => matrixVectorMul(transpose3(rotation), normal);

  const raw = calibration.planes || derivePlanesFromSources(calibration.plane_sources) || {};
  const frontAxis = makeOpticalAxis("C1 光轴", [0, 0, 0], [0, 0, 1], COLORS.cameraFront);
  const rearAxis = makeOpticalAxis("C2 光轴", rearToFront([0, 0, 0]), rearNormalToFront([0, 0, 1]), COLORS.cameraRear);
  const planes = makeOpticalPlanePatches(raw, frontAxis, rearAxis, rearToFront, rearNormalToFront);
  const frames = makeFrames(calibration.frames || {}, rearToFront, rearNormalToFront);

  return {
    planes,
    frames,
    opticalAxes: [frontAxis, rearAxis],
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

function makeOpticalPlanePatches(raw, frontAxis, rearAxis, rearToFront, rearNormalToFront) {
  const planes = [];
  const rearImage = raw.rear_image_real && transformPlane(raw.rear_image_real, rearToFront, rearNormalToFront);
  const rearReflection = raw.rear_reflection && transformPlane(raw.rear_reflection, rearToFront, rearNormalToFront);

  addPlaneSet(planes, "front", raw.front_image_real, raw.front_reflection, frontAxis);
  addPlaneSet(planes, "rear", rearImage, rearReflection, rearAxis);
  return planes;
}

function addPlaneSet(planes, labelPrefix, imagePlane, reflectionPlane, axis) {
  if (imagePlane) {
    planes.push(makePlane(`${labelPrefix} image`, "image", imagePlane, opticalIntersection(axis, imagePlane)));
  }
  if (reflectionPlane) {
    planes.push(makePlane(`${labelPrefix} reflection`, "reflection", reflectionPlane, opticalIntersection(axis, reflectionPlane)));
  }
  if (imagePlane && reflectionPlane) {
    const imagePatch = makePlane(`${labelPrefix} virtual image`, "virtual", imagePlane, opticalIntersection(axis, imagePlane));
    planes.push(mirrorPlanePatch(imagePatch, reflectionPlane));
  }
}

function makePlane(label, kind, plane, centerInput = plane.point) {
  const center = centerInput || plane.point;
  const point = toPoint(center);
  const normal = unit(plane.normal);
  const axes = planeAxes(normal);
  const size = kind === "reflection" ? 7 : 5.5;
  const corners = [
    add3(add3(center, scale3(axes.u, -size)), scale3(axes.v, -size)),
    add3(add3(center, scale3(axes.u, size)), scale3(axes.v, -size)),
    add3(add3(center, scale3(axes.u, size)), scale3(axes.v, size)),
    add3(add3(center, scale3(axes.u, -size)), scale3(axes.v, size)),
  ].map(toPoint);
  return { label, kind, point, normal: toPoint(normal), corners };
}

function mirrorPlanePatch(imagePatch, reflectionPlane) {
  const point = mirrorPoint(fromPoint(imagePatch.point), reflectionPlane);
  const normal = unit(reflectVector(fromPoint(imagePatch.normal), reflectionPlane.normal));
  const corners = imagePatch.corners.map((corner) => toPoint(mirrorPoint(fromPoint(corner), reflectionPlane)));
  return {
    label: imagePatch.label,
    kind: "virtual",
    point: toPoint(point),
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

function makeFrames(raw, rearToFront, rearVectorToFront) {
  const frames = [];
  if (raw.front_frame_pose) frames.push(makeFrame("front frame", raw.front_frame_pose, (point) => point, (vector) => vector));
  if (raw.rear_frame_pose) frames.push(makeFrame("rear frame", raw.rear_frame_pose, rearToFront, rearVectorToFront));
  return frames;
}

function makeFrame(label, pose, transformPoint, transformVector) {
  const width = Number(pose.frame_width_mm || 22);
  const height = Number(pose.frame_height_mm || 17);
  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const localCorners = [
    [-halfWidth, -halfHeight, 0],
    [halfWidth, -halfHeight, 0],
    [halfWidth, halfHeight, 0],
    [-halfWidth, halfHeight, 0],
  ];
  const matrix = pose.matrix_frame_to_camera || composeMatrix(pose.rotation_frame_to_camera, pose.translation_frame_to_camera);
  const corners = localCorners.map((point) => toPoint(transformPoint(applyMatrix(matrix, point))));
  const origin = toPoint(transformPoint(applyMatrix(matrix, [0, 0, 0])));
  const axes = {
    x: toPoint(unit(transformVector(matrixColumn(matrix, 0)))),
    y: toPoint(unit(transformVector(matrixColumn(matrix, 1)))),
    z: toPoint(unit(transformVector(matrixColumn(matrix, 2)))),
  };
  return { label, kind: "frame", width, height, corners, origin, axes };
}

function composeMatrix(rotation, translation) {
  return [
    [rotation[0][0], rotation[0][1], rotation[0][2], translation[0]],
    [rotation[1][0], rotation[1][1], rotation[1][2], translation[1]],
    [rotation[2][0], rotation[2][1], rotation[2][2], translation[2]],
    [0, 0, 0, 1],
  ];
}

function applyMatrix(matrix, point) {
  return matrix.slice(0, 3).map((row) => row[0] * point[0] + row[1] * point[1] + row[2] * point[2] + row[3]);
}

function matrixColumn(matrix, index) {
  return [matrix[0][index], matrix[1][index], matrix[2][index]];
}

function transformPlane(plane, transformPoint, transformNormal) {
  const point = transformPoint(plane.point);
  const normal = unit(transformNormal(plane.normal));
  return { point, normal, d: -dot(normal, point) };
}

function derivePlanesFromSources(sources) {
  const colmap = sources?.colmap;
  if (!colmap?.poses) return null;
  const scale = Number(colmap.translation_scale || 10);
  const imageOffset = Number(colmap.image_z_offset_mm || 2);
  return {
    front_image_real: imagePlaneFromPose(colmap.poses.front_image_real, scale, imageOffset),
    rear_image_real: imagePlaneFromPose(colmap.poses.rear_image_real, scale, imageOffset),
    front_reflection: boardPlaneFromPose(colmap.poses.front_reflection, scale),
    rear_reflection: boardPlaneFromPose(colmap.poses.rear_reflection, scale),
  };
}

function imagePlaneFromPose(pose, scale, imageOffset) {
  const board = boardPlaneFromPose(pose, scale);
  return planeFromPointNormal(add3(board.point, [0, 0, imageOffset]), board.normal);
}

function boardPlaneFromPose(pose, scale) {
  const rotation = rotationFromColmapQuaternion(pose);
  const normal = unit([rotation[0][2], rotation[1][2], rotation[2][2]]);
  const point = [pose.tx, pose.ty, pose.tz].map((value) => Number(value) * scale);
  return planeFromPointNormal(point, normal);
}

function rotationFromColmapQuaternion(pose) {
  const [qw, qx, qy, qz] = unit([pose.qw, pose.qx, pose.qy, pose.qz].map(Number));
  return [
    [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qz * qw, 2 * qx * qz + 2 * qy * qw],
    [2 * qx * qy + 2 * qz * qw, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qx * qw],
    [2 * qx * qz - 2 * qy * qw, 2 * qy * qz + 2 * qx * qw, 1 - 2 * qx * qx - 2 * qy * qy],
  ];
}

function planeFromPointNormal(point, normalInput) {
  const normal = unit(normalInput);
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

function fromPoint(point) {
  return [point.x, point.y, point.z];
}
