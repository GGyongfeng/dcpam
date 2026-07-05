// 把 Python 端 dcpam.pipeline 的 2-6 步搬到 Web。
// 只依赖 TOML 里的标定/设备几何 + CSV 里的圆心像素坐标。

const UNDISTORT_ITERATIONS = 8;

// 聚合默认参数（对齐 spot_extraction.py 的校准）：
//   任一相机 confidence < 0.4 的帧先被淘汰（对应"圆版没入镜"或饱和眩光）
//   幸存帧算完距离后，再用 |d - median| > 2.5 × MAD 剔离群点
export const AGGREGATE_DEFAULTS = Object.freeze({
  confidenceThreshold: 0.4,
  madK: 2.5,
});

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

/**
 * 对一次采样的多帧图片做"per-frame pipeline + 双层过滤 + 均值"。
 *
 * 流程（原本前端只对均值 UV 跑一次 measureRow，忽略了帧间抖动）:
 *   1. 遍历 record.frames[]；任一相机 confidence < confidenceThreshold 的帧直接淘汰。
 *   2. 幸存帧各自跑完整 measureRow，收集有限 distance。
 *   3. 用 median + MAD 剔除 |d - median| > madK × MAD 的距离离群点。
 *   4. 幸存距离求均值 / std，同时挑一帧作 3D 场景的代表 (距离最靠近 mean 的那帧)。
 *
 * 返回 null 表示 record/几何缺失；否则返回：
 *   {
 *     representative,          // measureRow 结果，供 SceneView 显示 (mean-representative frame)
 *     distanceMean,            // 幸存帧距离均值 (mm)
 *     distanceStd,             // 幸存帧距离标准差 (mm)
 *     distancesUsed[],         // 通过双层过滤的距离数组
 *     nTotal,                  // record.frames 总数
 *     nDroppedByConfidence,    // 第一层淘汰数
 *     nDroppedByMAD,           // 第二层剔除数
 *     nUsed,                   // 最终参与均值的帧数
 *     perFrame[]               // 每帧详情：{index, confidence, distance, dropReason|null}
 *   }
 */
export function aggregateDistance(record, geometry, tomlConfig, options) {
  if (!record || !geometry || !tomlConfig) return null;
  if (!Array.isArray(record.frames) || record.frames.length === 0) return null;

  const opts = { ...AGGREGATE_DEFAULTS, ...(options || {}) };
  const perFrame = [];

  for (const frame of record.frames) {
    const frontConf = Number(frame.front_quality?.confidence);
    const rearConf = Number(frame.rear_quality?.confidence);
    const minConf = Math.min(
      Number.isFinite(frontConf) ? frontConf : 0,
      Number.isFinite(rearConf) ? rearConf : 0,
    );

    const entry = {
      index: frame.index,
      confidence: minConf,
      distance: NaN,
      measurement: null,
      dropReason: null,
    };

    if (!Array.isArray(frame.front_uv) || !Array.isArray(frame.rear_uv)) {
      entry.dropReason = "no_uv";
      perFrame.push(entry);
      continue;
    }
    if (minConf < opts.confidenceThreshold) {
      entry.dropReason = "low_confidence";
      perFrame.push(entry);
      continue;
    }

    const row = {
      name: `${record.id}#${frame.index}`,
      front_u: frame.front_uv[0],
      front_v: frame.front_uv[1],
      rear_u: frame.rear_uv[0],
      rear_v: frame.rear_uv[1],
    };
    const result = measureRow(row, geometry, tomlConfig);
    if (!result || !Number.isFinite(result.distance)) {
      entry.dropReason = "pipeline_failed";
      perFrame.push(entry);
      continue;
    }

    entry.distance = result.distance;
    entry.measurement = result;
    perFrame.push(entry);
  }

  const nTotal = perFrame.length;
  const survivors = perFrame.filter((e) => e.dropReason === null);
  const nDroppedByConfidence = perFrame.filter((e) => e.dropReason === "low_confidence").length;

  if (survivors.length === 0) {
    return {
      representative: null,
      distanceMean: NaN,
      distanceStd: NaN,
      distancesUsed: [],
      nTotal,
      nDroppedByConfidence,
      nDroppedByMAD: 0,
      nUsed: 0,
      perFrame,
    };
  }

  const distances = survivors.map((e) => e.distance);
  const median = quickMedian(distances);
  const mad = medianAbsDeviation(distances, median);

  // 若 MAD=0（所有距离相等或只有 1 个），跳过 MAD 剔除
  const tolerance = mad > 1e-12 ? opts.madK * mad : Infinity;
  const finalSurvivors = [];
  let droppedByMAD = 0;
  for (const entry of survivors) {
    if (Math.abs(entry.distance - median) <= tolerance) {
      finalSurvivors.push(entry);
    } else {
      entry.dropReason = "mad_outlier";
      droppedByMAD += 1;
    }
  }

  const usedDistances = finalSurvivors.map((e) => e.distance);
  const distanceMean = usedDistances.reduce((a, b) => a + b, 0) / usedDistances.length;
  const variance = usedDistances.length > 1
    ? usedDistances.reduce((s, d) => s + (d - distanceMean) ** 2, 0) / (usedDistances.length - 1)
    : 0;
  const distanceStd = Math.sqrt(variance);

  // 代表帧：距离最靠近 mean 的那一帧，用于 3D 场景显示
  let representative = null;
  let bestDiff = Infinity;
  for (const entry of finalSurvivors) {
    const diff = Math.abs(entry.distance - distanceMean);
    if (diff < bestDiff) {
      bestDiff = diff;
      representative = entry.measurement;
    }
  }

  return {
    representative,
    distanceMean,
    distanceStd,
    distancesUsed: usedDistances,
    nTotal,
    nDroppedByConfidence,
    nDroppedByMAD: droppedByMAD,
    nUsed: finalSurvivors.length,
    perFrame,
  };
}

function quickMedian(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  if (n === 0) return NaN;
  return n % 2 === 1 ? sorted[(n - 1) / 2] : 0.5 * (sorted[n / 2 - 1] + sorted[n / 2]);
}

function medianAbsDeviation(values, median) {
  if (values.length === 0) return 0;
  return quickMedian(values.map((v) => Math.abs(v - median)));
}
