// 把 Python 端 dcpam_cv.pipeline 的 2-6 步搬到 Web。
// 只依赖 TOML 里的标定/设备几何 + CSV 里的圆心像素坐标。

const UNDISTORT_ITERATIONS = 8;

export function measureRow(row, geometry, tomlConfig) {
  if (!row || !geometry || !tomlConfig) return null;

  const spots = pixelSpotsFromRow(row);
  if (!spots) return null;

  const calibration = tomlConfig.calibration || tomlConfig;
  const frontIntrinsics = calibration.front_camera;
  const rearIntrinsics = calibration.rear_camera;
  const frontImagePlane = calibration.frame_surfaces?.front_frame_pnp;
  const rearImagePlane = calibration.frame_surfaces?.rear_frame_pnp;
  if (!frontIntrinsics || !rearIntrinsics || !frontImagePlane || !rearImagePlane) return null;

  const frontRealCamera = backProject(spots.front, frontIntrinsics, frontImagePlane);
  const rearRealCamera = backProject(spots.rear, rearIntrinsics, rearImagePlane);
  if (!frontRealCamera || !rearRealCamera) return null;

  const frontToDevice = geometry.frontCameraToDevice;
  const rearToDevice = geometry.rearCameraToDevice;
  if (!frontToDevice || !rearToDevice) return null;

  const frontReal = withSpace(frontToDevice([frontRealCamera.x, frontRealCamera.y, frontRealCamera.z]), "device");
  const rearReal = withSpace(rearToDevice([rearRealCamera.x, rearRealCamera.y, rearRealCamera.z]), "device");

  const frontReflection = geometry.device?.reflections?.[0];
  const rearReflection = geometry.device?.reflections?.[1];
  if (!frontReflection || !rearReflection) return null;

  const frontVirtual = withSpace(
    mirrorPoint(
      [frontReal.x, frontReal.y, frontReal.z],
      asTriple(frontReflection.point),
      asTriple(frontReflection.normal),
    ),
    "device",
  );
  const rearVirtual = withSpace(
    mirrorPoint(
      [rearReal.x, rearReal.y, rearReal.z],
      asTriple(rearReflection.point),
      asTriple(rearReflection.normal),
    ),
    "device",
  );
  if (!frontVirtual || !rearVirtual) return null;

  const probeTarget = geometry.device?.probeRod?.target;
  const target = probeTarget ? withSpace([probeTarget.x, probeTarget.y, probeTarget.z], "device") : null;
  const distance = target
    ? pointToLineDistance(
        [target.x, target.y, target.z],
        [frontVirtual.x, frontVirtual.y, frontVirtual.z],
        [rearVirtual.x, rearVirtual.y, rearVirtual.z],
      )
    : NaN;

  return {
    spots,
    frontRealCamera: { ...frontRealCamera, space: "camera_front" },
    rearRealCamera: { ...rearRealCamera, space: "camera_rear" },
    frontReal,
    rearReal,
    frontVirtual,
    rearVirtual,
    target,
    distance,
  };
}

function pixelSpotsFromRow(row) {
  const fu = Number(row.front_u);
  const fv = Number(row.front_v);
  const ru = Number(row.rear_u);
  const rv = Number(row.rear_v);
  if (![fu, fv, ru, rv].every(Number.isFinite)) return null;
  return { front: { u: fu, v: fv }, rear: { u: ru, v: rv } };
}

export function backProject(pixel, intrinsics, imagePlane) {
  const focal = intrinsics.focal_lengths;
  const principal = intrinsics.principal_point;
  const distortion = intrinsics.distortion_coeffs;
  if (!Array.isArray(focal) || !Array.isArray(principal) || !Array.isArray(distortion)) return null;
  const fx = Number(focal[0]);
  const fy = Number(focal[1]);
  const cx = Number(principal[0]);
  const cy = Number(principal[1]);
  if (![fx, fy, cx, cy].every(Number.isFinite) || fx === 0 || fy === 0) return null;

  // 归一化平面坐标 (K^-1 * [u v 1]^T)
  const xDist = (Number(pixel.u) - cx) / fx;
  const yDist = (Number(pixel.v) - cy) / fy;

  // OpenCV k1, k2, p1, p2 迭代去畸变
  const undistorted = undistortOpenCV([xDist, yDist], distortion.map(Number));

  const ray = [undistorted[0], undistorted[1], 1];
  const intersection = intersectRayWithPlane(ray, imagePlane);
  if (!intersection) return null;
  return { x: intersection[0], y: intersection[1], z: intersection[2] };
}

function undistortOpenCV(distorted, coeffs) {
  const k1 = Number.isFinite(coeffs[0]) ? coeffs[0] : 0;
  const k2 = Number.isFinite(coeffs[1]) ? coeffs[1] : 0;
  const p1 = Number.isFinite(coeffs[2]) ? coeffs[2] : 0;
  const p2 = Number.isFinite(coeffs[3]) ? coeffs[3] : 0;
  let x = distorted[0];
  let y = distorted[1];
  for (let i = 0; i < UNDISTORT_ITERATIONS; i += 1) {
    const r2 = x * x + y * y;
    const radial = 1 + k1 * r2 + k2 * r2 * r2;
    const tx = 2 * p1 * x * y + p2 * (r2 + 2 * x * x);
    const ty = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y;
    x = (distorted[0] - tx) / radial;
    y = (distorted[1] - ty) / radial;
  }
  return [x, y];
}

function intersectRayWithPlane(ray, plane) {
  const normal = asTriple(plane.normal);
  if (!normal) return null;
  const denominator = normal[0] * ray[0] + normal[1] * ray[1] + normal[2] * ray[2];
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-12) return null;
  const scale = -Number(plane.d) / denominator;
  if (!Number.isFinite(scale)) return null;
  return [scale * ray[0], scale * ray[1], scale * ray[2]];
}

export function mirrorPoint(point, planePoint, planeNormal) {
  const normal = unit(asTriple(planeNormal));
  const origin = asTriple(planePoint);
  if (!normal || !origin) return null;
  const d = -(normal[0] * origin[0] + normal[1] * origin[1] + normal[2] * origin[2]);
  const signed = normal[0] * point[0] + normal[1] * point[1] + normal[2] * point[2] + d;
  return [
    point[0] - 2 * signed * normal[0],
    point[1] - 2 * signed * normal[1],
    point[2] - 2 * signed * normal[2],
  ];
}

export function pointToLineDistance(point, lineA, lineB) {
  const L = [lineB[0] - lineA[0], lineB[1] - lineA[1], lineB[2] - lineA[2]];
  const w = [point[0] - lineA[0], point[1] - lineA[1], point[2] - lineA[2]];
  const cross = [
    L[1] * w[2] - L[2] * w[1],
    L[2] * w[0] - L[0] * w[2],
    L[0] * w[1] - L[1] * w[0],
  ];
  const lineLength = Math.hypot(L[0], L[1], L[2]);
  if (lineLength < 1e-9) return NaN;
  return Math.hypot(cross[0], cross[1], cross[2]) / lineLength;
}

function withSpace(vector, space) {
  if (!vector) return null;
  return { x: Number(vector[0]), y: Number(vector[1]), z: Number(vector[2]), space };
}

function unit(vector) {
  const t = asTriple(vector);
  if (!t) return null;
  const length = Math.hypot(t[0], t[1], t[2]);
  if (!Number.isFinite(length) || length < 1e-12) return null;
  return [t[0] / length, t[1] / length, t[2] / length];
}

function asTriple(value) {
  if (!value) return null;
  if (Array.isArray(value)) {
    if (value.length < 3) return null;
    const out = [Number(value[0]), Number(value[1]), Number(value[2])];
    return out.every(Number.isFinite) ? out : null;
  }
  const out = [Number(value.x), Number(value.y), Number(value.z)];
  return out.every(Number.isFinite) ? out : null;
}
