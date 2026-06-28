import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { TrackballControls } from "three/examples/jsm/controls/TrackballControls.js";

import { COLORS, planeColor, pointFromRow, toVector3 } from "./geometry.js";

const DEVICE_DARK_COLOR = 0x4f5661;
const VIEW_FRAME_COLOR = 0x1f5a78;
const CAMERA_MODEL_SCALE = 2.35;
const DEVICE_LAYER_KEYS = [
  "frontViewFrame",
  "rearViewFrame",
  "frontFrostedGlass",
  "rearFrostedGlass",
  "frontReflectionMirror",
  "rearReflectionMirror",
  "basePlate",
  "probeRod",
];

export function SceneView({ rows, geometry, layers }) {
  const mountRef = useRef(null);
  const axesRef = useRef(null);
  const layersRef = useRef(layers);
  const sceneRef = useRef(null);
  const [inspection, setInspection] = useState(null);
  const [cameraPosition, setCameraPosition] = useState({ x: 0, y: 0, z: 0 });

  useEffect(() => {
    layersRef.current = layers;
  }, [layers]);

  useEffect(() => {
    const mount = mountRef.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);

    const camera = new THREE.OrthographicCamera(-60, 60, 60, -60, 0.1, 4000);
    camera.position.set(45, -55, 42);
    camera.userData.viewSize = 60;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    mount.appendChild(renderer.domElement);

    const controls = new TrackballControls(camera, renderer.domElement);
    controls.dynamicDampingFactor = 0.12;
    controls.rotateSpeed = 2.4;
    controls.zoomSpeed = 1.1;
    controls.panSpeed = 0.55;
    controls.staticMoving = false;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };

    scene.add(new THREE.AmbientLight(0xffffff, 0.78));
    const light = new THREE.DirectionalLight(0xffffff, 0.72);
    light.position.set(30, -45, 60);
    scene.add(light);

    const root = new THREE.Group();
    scene.add(root);

    const axes = createAxesView(axesRef.current);
    sceneRef.current = { root, camera, renderer, controls, mount, axes };
    const raycaster = new THREE.Raycaster();
    raycaster.params.Line.threshold = 0.8;
    const pointer = new THREE.Vector2();
    const inspect = (event) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster
        .intersectObjects(root.children, true)
        .find((item) => item.object.userData?.pickInfo);
      setInspection(hit ? hit.object.userData.pickInfo : null);
    };
    const clearInspection = () => setInspection(null);
    renderer.domElement.addEventListener("pointermove", inspect);
    renderer.domElement.addEventListener("click", inspect);
    renderer.domElement.addEventListener("pointerleave", clearInspection);

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      renderer.setSize(rect.width, rect.height);
      applyOrthoFrustum(camera, mount);
      controls.handleResize();
    };
    resize();
    window.addEventListener("resize", resize);

    let active = true;
    let frameIndex = 0;
    const animate = () => {
      if (!active) return;
      controls.update();
      renderer.render(scene, camera);
      renderAxesView(axes, camera, sceneRef.current?.geometry);
      if (frameIndex % 8 === 0) {
        setCameraPosition({ x: camera.position.x, y: camera.position.y, z: camera.position.z });
      }
      frameIndex += 1;
      requestAnimationFrame(animate);
    };
    animate();

    return () => {
      active = false;
      window.removeEventListener("resize", resize);
      renderer.domElement.removeEventListener("pointermove", inspect);
      renderer.domElement.removeEventListener("click", inspect);
      renderer.domElement.removeEventListener("pointerleave", clearInspection);
      axes?.renderer.dispose();
      axes?.renderer.domElement.remove();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    const context = sceneRef.current;
    if (!context) return;
    clearGroup(context.root);
    buildScene(context.root, rows, geometry, layers);
    context.geometry = geometry;
  }, [rows, geometry, layers]);

  useEffect(() => {
    const context = sceneRef.current;
    if (!context) return;
    fitCamera(context.camera, context.controls, geometry, context.mount);
  }, [geometry]);

  const setMainView = () => {
    const context = sceneRef.current;
    if (!context) return;
    setHomeView(context.camera, context.controls);
  };

  const setTopView = () => {
    const context = sceneRef.current;
    if (!context) return;
    setViewAlongY(context.camera, context.controls);
  };

  return (
    <div ref={mountRef} className="scene-mount">
      <div className="axes-widget">
        <div className="view-buttons">
          <button type="button" onClick={setMainView}>主视图</button>
          <button type="button" onClick={setTopView}>正视图</button>
        </div>
        <div ref={axesRef} className="axes-mount" />
        <div className="view-direction">camera.position {formatPoint(cameraPosition)}</div>
      </div>
      <InspectionPanel info={inspection} />
    </div>
  );
}

function buildScene(root, rows, geometry, layers) {
  const deviceVisible = hasVisibleDeviceLayer(layers);
  if (geometry) {
    geometry.planes.forEach((plane) => {
      if (plane.kind === "image" && !layers.imagePlanes) return;
      if (plane.kind === "reflection" && !layers.reflectionPlanes) return;
      if (plane.kind === "virtual" && !layers.virtualPlanes) return;
      root.add(planeMesh(plane));
      if (layers.labels) root.add(labelSprite(plane.label, plane.point, deviceVisible));
    });
    if (layers.cameras) {
      geometry.cameras.forEach((camera) => {
        root.add(cameraMesh(camera));
        if (layers.labels) root.add(labelSprite(camera.name, camera.position, deviceVisible));
      });
    }
    if (layers.localAxes) {
      (geometry.coordinateFrames || []).forEach((frame) => {
        root.add(coordinateFrameMesh(frame));
        if (layers.labels) root.add(labelSprite(frame.name, frame.origin, deviceVisible));
      });
    }
    if (deviceVisible) {
      const device = deviceModelMesh(geometry, layers);
      if (device) root.add(device);
    }
    if (layers.opticalAxes) {
      (geometry.opticalAxes || []).forEach((axis) => {
        root.add(opticalAxisMesh(axis));
        if (layers.labels) root.add(labelSprite(axis.label, axis.end, deviceVisible));
      });
    }
  }

  rows.forEach((row) => {
    const frontVirtual = displayPointFromRow(row, "front_virtual", "cf", geometry);
    const rearVirtual = displayPointFromRow(row, "rear_virtual", "cr", geometry);
    if (layers.frontVirtual && frontVirtual) {
      addPoint(root, frontVirtual, COLORS.frontVirtual, 0.72, pointInfo("前虚像点", "虚像点", frontVirtual, row.name, "C1 显示坐标系：由设备坐标系经前取景框 PnP 对齐得到"));
    }
    if (layers.rearVirtual && rearVirtual) {
      addPoint(root, rearVirtual, COLORS.rearVirtual, 0.72, pointInfo("后虚像点", "虚像点", rearVirtual, row.name, "C1 显示坐标系：由设备坐标系经前取景框 PnP 对齐得到"));
    }
    if (layers.realPoints) {
      const frontReal = displayPointFromRow(row, "front_real", "cf", geometry);
      const rearReal = displayPointFromRow(row, "rear_real", "cr", geometry);
      if (frontReal) {
        addPoint(root, frontReal, COLORS.real, 0.42, pointInfo("前实像点", "实像点", frontReal, row.name, "C1 显示坐标系"));
      }
      if (rearReal) {
        addPoint(root, rearReal, 0x8a96a8, 0.42, pointInfo("后实像点", "实像点", rearReal, row.name, "C1 显示坐标系"));
      }
    }
    if (layers.laserLines && frontVirtual && rearVirtual) {
      root.add(laserLineMesh(frontVirtual, rearVirtual, {
        name: row.name,
        type: "激光线",
        coordinateSystem: "C1 显示坐标系",
        position: midpoint(frontVirtual, rearVirtual),
        details: [
          `前端点：${formatPoint(frontVirtual)}，来自前虚像点`,
          `后端点：${formatPoint(rearVirtual)}，来自后虚像点`,
          "说明：红色线段为显示用激光线，沿前/后虚像点连线方向延长穿过画面。",
        ],
      }));
    }
  });
}

function hasVisibleDeviceLayer(layers) {
  return DEVICE_LAYER_KEYS.some((key) => layers[key]);
}

function addPoint(root, point, color, radius, info) {
  root.add(pointMesh(point, color, radius, info));
}

function rearDisplayPointFromRow(row, prefix, geometry) {
  const point = pointFromRow(row, prefix, "cr");
  const transform = geometry?.rearCameraDisplayTransform?.transformPoint;
  return point && transform ? toPointFromArray(transform([point.x, point.y, point.z])) : null;
}

function displayPointFromRow(row, prefix, cameraSuffix, geometry) {
  const point = pointFromRow(row, prefix, cameraSuffix);
  if (!point) return null;
  if (point.space === "device") {
    const transform = geometry?.deviceAlignment?.transformPoint;
    return transform ? toPointFromArray(transform([point.x, point.y, point.z])) : { x: point.x, y: point.y, z: point.z };
  }
  if (point.space === "camera_rear") {
    const transform = geometry?.rearCameraDisplayTransform?.transformPoint;
    return transform ? toPointFromArray(transform([point.x, point.y, point.z])) : { x: point.x, y: point.y, z: point.z };
  }
  return { x: point.x, y: point.y, z: point.z };
}

function pointInfo(name, type, position, sampleName, coordinateSystem) {
  return {
    coordinateSystem,
    details: [`位置：${formatPoint(position)}，${coordinateSystem}`],
    name,
    type,
    sampleName,
    position,
  };
}

function withPickInfo(object, info) {
  object.traverse((item) => {
    item.userData.pickInfo = info;
  });
  return object;
}

function planeTypeName(kind) {
  if (kind === "image") return "实像面";
  if (kind === "reflection") return "反射面";
  return "虚像面";
}

function planeMesh(plane) {
  const geometry = new THREE.BufferGeometry().setFromPoints(plane.corners.map(toVector3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.computeVertexNormals();
  const material = new THREE.MeshBasicMaterial({
    color: planeColor(plane.kind),
    transparent: true,
    opacity: plane.kind === "reflection" ? 0.22 : 0.18,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: planeColor(plane.kind), transparent: true, opacity: 0.72 }),
  );
  const group = new THREE.Group();
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    coordinateSystem: "C1 显示坐标系",
    name: plane.label,
    type: planeTypeName(plane.kind),
    position: plane.point,
    details: planeDetails(plane),
  });
}

function planeDetails(plane) {
  const details = [
    `平面参考点：${formatPoint(plane.point)}，C1 显示坐标系`,
    `法向量：${formatPoint(plane.normal)}，C1 显示坐标系中的方向向量`,
  ];
  if (Number.isFinite(plane.d)) {
    details.push(`平面方程：${planeEquation(plane.normal, plane.d)}`);
  }
  if (plane.method) {
    details.push(`来源：${methodName(plane.method)}`);
  }
  if (Number.isFinite(plane.width) && Number.isFinite(plane.height)) {
    details.push(`尺寸：X=${formatNumber(plane.width)}mm，Y=${formatNumber(plane.height)}mm`);
  }
  if (Number.isFinite(plane.reprojectionErrorPx)) {
    details.push(`PnP 重投影误差：${formatNumber(plane.reprojectionErrorPx)}px`);
  }
  return details;
}

function frameMesh(frame) {
  const group = new THREE.Group();
  const points = frame.corners.map(toVector3);
  const faceGeometry = new THREE.BufferGeometry().setFromPoints(points);
  faceGeometry.setIndex([0, 1, 2, 0, 2, 3]);
  faceGeometry.computeVertexNormals();
  const face = new THREE.Mesh(
    faceGeometry,
    new THREE.MeshBasicMaterial({
      color: COLORS.frame,
      transparent: true,
      opacity: 0.08,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  const outline = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: COLORS.frame, transparent: true, opacity: 0.95 }),
  );
  group.add(face);
  group.add(outline);
  group.add(pointMesh(frame.origin, COLORS.frame, 0.45));
  group.add(surfaceAxes(frame.origin, frame.axes, 5.0));
  return withPickInfo(group, {
    coordinateSystem: "C1 显示坐标系",
    name: frame.label,
    type: "PnP 实像面",
    position: frame.origin,
    details: frameSurfaceDetails(frame),
  });
}

function surfaceAxes(origin, axes, length) {
  const group = new THREE.Group();
  group.add(frameAxis(origin, axes.x, 0xd97706, length));
  group.add(frameAxis(origin, axes.y, 0x6b7280, length * 0.8));
  group.add(frameAxis(origin, axes.z, 0x111114, length * 0.8));
  return group;
}

function coordinateFrameMesh(frame) {
  const group = surfaceAxes(frame.origin, frame.axes, frame.length || 8);
  group.add(pointMesh(frame.origin, 0x111114, 0.35));
  return withPickInfo(group, {
    coordinateSystem: "C1 显示坐标系",
    name: frame.name,
    type: "坐标系",
    position: frame.origin,
    details: [
      `原点：${formatPoint(frame.origin)}，C1 显示坐标系`,
      `X 轴：${formatPoint(frame.axes.x)}，C1 显示坐标系中的方向向量`,
      `Y 轴：${formatPoint(frame.axes.y)}，C1 显示坐标系中的方向向量`,
      `Z 轴：${formatPoint(frame.axes.z)}，C1 显示坐标系中的方向向量`,
    ],
  });
}

function frameSurfaceDetails(frame) {
  const details = [
    "说明：通过取景框角点 PnP 估计出的实像面。",
    `中心点：${formatPoint(frame.origin)}，C1 显示坐标系`,
    `X 轴：${formatPoint(frame.axes.x)}，C1 显示坐标系中的方向向量`,
    `Y 轴：${formatPoint(frame.axes.y)}，C1 显示坐标系中的方向向量`,
    `法向量：${formatPoint(frame.axes.z)}，C1 显示坐标系中的方向向量`,
    `尺寸：X=${formatNumber(frame.width)}mm，Y=${formatNumber(frame.height)}mm`,
  ];
  if (Number.isFinite(frame.reprojectionErrorPx)) {
    details.push(`PnP 重投影误差：${formatNumber(frame.reprojectionErrorPx)}px`);
  }
  if (frame.method) {
    details.push(`来源：${methodName(frame.method)}`);
  }
  return details;
}

function deviceModelMesh(geometry, layers) {
  const device = geometry.device;
  if (!device) return null;

  const group = new THREE.Group();
  if (layers.frontViewFrame) group.add(viewFrameAssembly(device.frames[0], device.viewFrame, "前取景框"));
  if (layers.rearViewFrame) group.add(viewFrameAssembly(device.frames[1], device.viewFrame, "后取景框"));
  if (layers.frontFrostedGlass) {
    group.add(frostedGlassAssembly(device.frames[0], device.viewFrame, device.frostedGlass, "前毛玻璃片"));
  }
  if (layers.rearFrostedGlass) {
    group.add(frostedGlassAssembly(device.frames[1], device.viewFrame, device.frostedGlass, "后毛玻璃片"));
  }
  if (layers.frontReflectionMirror) group.add(reflectionMirrorAssembly(device.reflections[0], 0x8c7f93, "前反射镜"));
  if (layers.rearReflectionMirror) group.add(reflectionMirrorAssembly(device.reflections[1], 0x756f7d, "后反射镜"));
  if (layers.basePlate) group.add(basePlateMesh(device.basePlate));
  if (layers.probeRod) group.add(probeRodMesh(device.probeRod, device.basePlate));
  if (geometry.deviceAlignment?.matrix) {
    group.applyMatrix4(matrixFromRows(geometry.deviceAlignment.matrix));
  }
  return group;
}

function deviceSolidMaterial(color = DEVICE_DARK_COLOR) {
  return new THREE.MeshStandardMaterial({
    color,
    depthTest: true,
    depthWrite: true,
    metalness: 0.18,
    opacity: 1,
    roughness: 0.42,
    transparent: false,
  });
}

function viewFrameAssembly(frame, spec, name) {
  const group = new THREE.Group();
  const material = deviceSolidMaterial(VIEW_FRAME_COLOR);
  const geometry = viewFrameGeometry(frame, spec);
  const mesh = new THREE.Mesh(geometry, material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x262c35, transparent: true, opacity: 0.75 }),
  );
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    coordinateSystem: "设备坐标系；显示时整体通过 C1-P1 对齐变换放入 C1 显示坐标系",
    name,
    type: "取景框实体",
    position: frame.center,
    details: viewFrameDetails(frame, spec),
  });
}

function viewFrameGeometry(frame, spec) {
  const outerBounds = rectBounds(frame.outerCorners);
  const innerBounds = rectBounds(frame.rectCorners);
  const outer = roundedRectPath(
    outerBounds.xMin,
    outerBounds.xMax,
    outerBounds.yMin,
    outerBounds.yMax,
    spec.outerRadius,
  );
  const inner = roundedRectPath(
    innerBounds.xMin,
    innerBounds.xMax,
    innerBounds.yMin,
    innerBounds.yMax,
    spec.innerRadius,
    true,
  );
  outer.holes.push(inner);
  const geometry = new THREE.ExtrudeGeometry(outer, {
    bevelEnabled: false,
    curveSegments: 16,
    depth: spec.thickness,
  });
  const positions = geometry.attributes.position;
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const y = positions.getY(index);
    const z = positions.getZ(index) - spec.thickness;
    positions.setXYZ(index, x, y, z);
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function viewFrameDetails(frame, spec) {
  return [
    `中心点：${formatPoint(frame.center)}，设备坐标系`,
    `设备实像面(Z=0)：${planeEquation(frame.normal, frame.d)}`,
    `透空尺寸：X=${formatNumber(spec.innerWidth)}mm，Y=${formatNumber(spec.innerHeight)}mm`,
    `透空圆角：R=${formatNumber(spec.innerRadius)}mm`,
    `实体外形：X=${formatNumber(spec.outerWidth)}mm，Y=${formatNumber(spec.outerHeight)}mm`,
    `厚度：沿 -Z 方向 ${formatNumber(spec.thickness)}mm，背面贴 Z=0`,
  ];
}

function frostedGlassAssembly(frame, spec, glass, name) {
  const geometry = frostedGlassGeometry(frame, spec, glass);
  const material = new THREE.MeshPhysicalMaterial({
    color: 0xf5f7f2,
    transparent: true,
    opacity: 0.46,
    roughness: 0.86,
    transmission: 0.2,
    thickness: 3,
    side: THREE.DoubleSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0xcfd6d1, transparent: true, opacity: 0.82 }),
  );
  const group = new THREE.Group();
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    coordinateSystem: "设备坐标系；显示时整体通过 C1-P1 对齐变换放入 C1 显示坐标系",
    name,
    type: "毛玻璃片",
    position: { ...frame.center, z: frame.center.z + glass.thickness / 2 },
    details: frostedGlassDetails(frame, spec, glass),
  });
}

function frostedGlassGeometry(frame, spec, glass) {
  const bounds = rectBounds(frame.outerCorners);
  const shape = roundedRectPath(
    bounds.xMin,
    bounds.xMax,
    bounds.yMin,
    bounds.yMax,
    spec.outerRadius,
  );
  const geometry = new THREE.ExtrudeGeometry(shape, {
    bevelEnabled: false,
    curveSegments: 16,
    depth: glass.thickness,
  });
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function frostedGlassDetails(frame, spec, glass) {
  return [
    `中心点：${formatPoint({ ...frame.center, z: frame.center.z + glass.thickness / 2 })}，设备坐标系`,
    `设备实像面(Z=0)：${planeEquation(frame.normal, frame.d)}`,
    `厚度：沿 +Z 方向 ${formatNumber(glass.thickness)}mm`,
    `外形：X=${formatNumber(spec.outerWidth)}mm，Y=${formatNumber(spec.outerHeight)}mm，R=${formatNumber(spec.outerRadius)}mm`,
  ];
}

function reflectionMirrorAssembly(reflection, color, name) {
  const group = new THREE.Group();
  const geometry = reflectionMirrorGeometry(reflection);
  const material = new THREE.MeshStandardMaterial({
    color,
    transparent: true,
    opacity: 0.5,
    metalness: 0.25,
    roughness: 0.32,
    side: THREE.DoubleSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x5b5264, transparent: true, opacity: 0.72 }),
  );
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    coordinateSystem: "设备坐标系；显示时整体通过 C1-P1 对齐变换放入 C1 显示坐标系",
    name,
    type: "反射镜",
    position: reflection.point,
    details: reflectionMirrorDetails(reflection),
  });
}

function reflectionMirrorGeometry(reflection) {
  const center = toVector3(reflection.point);
  const normal = toVector3(reflection.normal).normalize();
  const widthAxis = new THREE.Vector3(normal.z, 0, -normal.x).normalize();
  const heightAxis = new THREE.Vector3(0, 1, 0);
  const thicknessDirection = toVector3(reflection.thicknessDirection).normalize();
  const halfWidth = reflection.width / 2;
  const halfHeight = reflection.height / 2;
  const front = [
    center.clone().add(widthAxis.clone().multiplyScalar(-halfWidth)).add(heightAxis.clone().multiplyScalar(-halfHeight)),
    center.clone().add(widthAxis.clone().multiplyScalar(halfWidth)).add(heightAxis.clone().multiplyScalar(-halfHeight)),
    center.clone().add(widthAxis.clone().multiplyScalar(halfWidth)).add(heightAxis.clone().multiplyScalar(halfHeight)),
    center.clone().add(widthAxis.clone().multiplyScalar(-halfWidth)).add(heightAxis.clone().multiplyScalar(halfHeight)),
  ].map(toPointFromVector);
  const back = front.map((point) => toPointFromVector(
    toVector3(point).add(thicknessDirection.clone().multiplyScalar(reflection.thickness)),
  ));
  const vertices = [...front, ...back];
  const indices = [
    0, 1, 2, 0, 2, 3,
    4, 6, 5, 4, 7, 6,
    0, 4, 5, 0, 5, 1,
    1, 5, 6, 1, 6, 2,
    2, 6, 7, 2, 7, 3,
    3, 7, 4, 3, 4, 0,
  ];
  const geometry = new THREE.BufferGeometry().setFromPoints(vertices.map(toVector3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function reflectionMirrorDetails(reflection) {
  return [
    `镜面参考点：${formatPoint(reflection.point)}，设备坐标系`,
    `前平面：${planeEquation(reflection.normal, reflection.d)}`,
    `尺寸：镜面宽 ${formatNumber(reflection.width)}mm，高 ${formatNumber(reflection.height)}mm`,
    `厚度：沿 ${formatPoint(reflection.thicknessDirection)} 方向 ${formatNumber(reflection.thickness)}mm`,
  ];
}

function basePlateMesh(bounds) {
  const center = new THREE.Vector3(
    (bounds.xMin + bounds.xMax) / 2,
    (bounds.yMin + bounds.yMax) / 2,
    (bounds.zMin + bounds.zMax) / 2,
  );
  const material = deviceSolidMaterial();
  const mesh = new THREE.Mesh(basePlateGeometry(bounds), material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: 0x262c35, transparent: true, opacity: 0.72 }),
  );
  const group = new THREE.Group();
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    coordinateSystem: "设备坐标系；显示时整体通过 C1-P1 对齐变换放入 C1 显示坐标系",
    name: "底座",
    type: "设备底座",
    position: toPointFromVector(center),
    details: basePlateDetails(bounds),
  });
}

function basePlateGeometry(bounds) {
  const shape = roundedRectPath(bounds.xMin, bounds.xMax, bounds.zMin, bounds.zMax, bounds.cornerRadius);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    bevelEnabled: false,
    curveSegments: 12,
    depth: bounds.yMax - bounds.yMin,
  });
  const positions = geometry.attributes.position;
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const z = positions.getY(index);
    const y = bounds.yMin + positions.getZ(index);
    positions.setXYZ(index, x, y, z);
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function roundedRectPath(xMin, xMax, yMin, yMax, radius, clockwise = false) {
  const path = new THREE.Shape();
  if (clockwise) {
    path.moveTo(xMin + radius, yMin);
    path.quadraticCurveTo(xMin, yMin, xMin, yMin + radius);
    path.lineTo(xMin, yMax - radius);
    path.quadraticCurveTo(xMin, yMax, xMin + radius, yMax);
    path.lineTo(xMax - radius, yMax);
    path.quadraticCurveTo(xMax, yMax, xMax, yMax - radius);
    path.lineTo(xMax, yMin + radius);
    path.quadraticCurveTo(xMax, yMin, xMax - radius, yMin);
    path.lineTo(xMin + radius, yMin);
    return path;
  }
  path.moveTo(xMin + radius, yMin);
  path.lineTo(xMax - radius, yMin);
  path.quadraticCurveTo(xMax, yMin, xMax, yMin + radius);
  path.lineTo(xMax, yMax - radius);
  path.quadraticCurveTo(xMax, yMax, xMax - radius, yMax);
  path.lineTo(xMin + radius, yMax);
  path.quadraticCurveTo(xMin, yMax, xMin, yMax - radius);
  path.lineTo(xMin, yMin + radius);
  path.quadraticCurveTo(xMin, yMin, xMin + radius, yMin);
  return path;
}

function basePlateDetails(bounds) {
  return [
    `上平面：Y=${formatNumber(bounds.yMin)}mm`,
    `下平面：Y=${formatNumber(bounds.yMax)}mm`,
    `X 范围：${formatNumber(bounds.xMin)}mm 到 ${formatNumber(bounds.xMax)}mm，宽度 ${formatNumber(bounds.xMax - bounds.xMin)}mm`,
    `Z 范围：${formatNumber(bounds.zMin)}mm 到 ${formatNumber(bounds.zMax)}mm，长度 ${formatNumber(bounds.zMax - bounds.zMin)}mm`,
    `厚度：${formatNumber(bounds.yMax - bounds.yMin)}mm`,
    `圆角：R=${formatNumber(bounds.cornerRadius)}mm`,
  ];
}

function probeRodMesh(spec, basePlate) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: 0xbfc1bd, metalness: 0.32, roughness: 0.28 });
  const connectorMaterial = deviceSolidMaterial();
  const root = toVector3(spec.root);
  const target = toVector3(spec.target);
  const rodAxis = target.clone().sub(root).normalize();
  const totalLength = root.distanceTo(target);
  const shaftLength = totalLength - spec.tipHeight;
  const shaftCenter = root.clone().add(rodAxis.clone().multiplyScalar(shaftLength / 2));
  const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), rodAxis);
  const cylinder = new THREE.Mesh(
    new THREE.CylinderGeometry(spec.rodRadius, spec.rodRadius, shaftLength, 32),
    material,
  );
  cylinder.position.copy(shaftCenter);
  cylinder.quaternion.copy(quaternion);
  const tip = new THREE.Mesh(
    new THREE.ConeGeometry(spec.rodRadius, spec.tipHeight, 32),
    material,
  );
  tip.position.copy(target.clone().add(rodAxis.clone().multiplyScalar(-spec.tipHeight / 2)));
  tip.quaternion.copy(quaternion);
  group.add(probeRodConnector(spec, basePlate, connectorMaterial));
  group.add(cylinder);
  group.add(tip);
  return withPickInfo(group, {
    coordinateSystem: "设备坐标系；显示时整体通过 C1-P1 对齐变换放入 C1 显示坐标系",
    name: "测量探杆",
    type: "探杆",
    position: spec.root,
    details: probeRodDetails(spec),
  });
}

function probeRodConnector(spec, basePlate, material) {
  const baseY = basePlate.yMax;
  const radius = spec.connectorRadius;
  const shape = new THREE.Shape();
  shape.moveTo(radius, 0);
  shape.absarc(0, 0, radius, 0, Math.PI, false);
  shape.lineTo(radius, 0);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: spec.connectorLength,
    bevelEnabled: false,
    curveSegments: 32,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(spec.root.x, baseY, spec.root.z);
  return mesh;
}

function probeRodLength(spec) {
  return toVector3(spec.root).distanceTo(toVector3(spec.target));
}

function probeRodDetails(spec) {
  return [
    `根部坐标：${formatPoint(spec.root)}，设备坐标系`,
    `靶点坐标：${formatPoint(spec.target)}，设备坐标系`,
    `杆长：${formatNumber(probeRodLength(spec))}mm`,
    "方向：沿 -Z 方向",
  ];
}

function frameAxis(origin, direction, color, length) {
  return new THREE.ArrowHelper(
    toVector3(direction).normalize(),
    toVector3(origin),
    length,
    color,
    0.65,
    0.32,
  );
}

function toPointFromVector(vector) {
  return { x: vector.x, y: vector.y, z: vector.z };
}

function toPointFromArray(vector) {
  return { x: vector[0], y: vector[1], z: vector[2] };
}

function matrixFromRows(rows) {
  return new THREE.Matrix4().set(
    rows[0][0], rows[0][1], rows[0][2], rows[0][3],
    rows[1][0], rows[1][1], rows[1][2], rows[1][3],
    rows[2][0], rows[2][1], rows[2][2], rows[2][3],
    rows[3][0], rows[3][1], rows[3][2], rows[3][3],
  );
}

function quaternionFromAxes(axes) {
  const matrix = new THREE.Matrix4().makeBasis(
    toVector3(axes.x).normalize(),
    toVector3(axes.y).normalize(),
    toVector3(axes.z).normalize(),
  );
  return new THREE.Quaternion().setFromRotationMatrix(matrix);
}

function opticalAxisMesh(axis) {
  const group = new THREE.Group();
  group.add(new THREE.ArrowHelper(
    toVector3(axis.direction).normalize(),
    toVector3(axis.origin),
    toVector3(axis.origin).distanceTo(toVector3(axis.end)),
    axis.color,
    1.2,
    0.5,
  ));
  group.add(pointMesh(axis.end, axis.color, 0.25));
  return withPickInfo(group, {
    coordinateSystem: "C1 显示坐标系",
    name: axis.label,
    type: "光轴",
    position: axis.origin,
    details: [
      `起点：${formatPoint(axis.origin)}，C1 显示坐标系`,
      `终点：${formatPoint(axis.end)}，C1 显示坐标系`,
      `方向：${formatPoint(axis.direction)}，C1 显示坐标系中的方向向量`,
    ],
  });
}

function cameraMesh(camera) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({
    color: camera.color,
    metalness: 0.18,
    opacity: 0.76,
    roughness: 0.34,
    transparent: true,
  });
  const dark = new THREE.MeshStandardMaterial({
    color: 0x141923,
    metalness: 0.2,
    opacity: 0.82,
    roughness: 0.28,
    transparent: true,
  });
  const glass = new THREE.MeshStandardMaterial({
    color: 0x1a1a1a,
    emissive: 0x050505,
    metalness: 0.1,
    roughness: 0.18,
  });

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(6.2, 3.2, 3.0),
    material,
  );
  const top = new THREE.Mesh(
    new THREE.BoxGeometry(2.7, 0.82, 1.55),
    material,
  );
  const lensBarrel = new THREE.Mesh(
    new THREE.CylinderGeometry(1.45, 1.62, 3.2, 56),
    dark,
  );
  const lensGlass = new THREE.Mesh(
    new THREE.CylinderGeometry(1.14, 1.14, 0.24, 56),
    glass,
  );
  const mount = new THREE.Mesh(
    new THREE.CylinderGeometry(1.82, 1.82, 0.62, 56),
    material,
  );
  const sensor = new THREE.Mesh(
    new THREE.BoxGeometry(2.2, 1.45, 0.12),
    new THREE.MeshStandardMaterial({ color: 0x0d1117, roughness: 0.4 }),
  );
  top.position.set(-0.58, 1.94, -0.24);
  mount.rotation.x = Math.PI / 2;
  mount.position.z = 1.68;
  lensBarrel.rotation.x = Math.PI / 2;
  lensBarrel.position.z = 3.25;
  lensGlass.rotation.x = Math.PI / 2;
  lensGlass.position.z = 4.98;
  sensor.position.z = -1.55;
  group.add(body);
  group.add(top);
  group.add(mount);
  group.add(lensBarrel);
  group.add(lensGlass);
  group.add(sensor);
  group.position.copy(toVector3(camera.position));
  group.quaternion.copy(quaternionFromAxes(camera.axes));
  group.scale.setScalar(CAMERA_MODEL_SCALE);
  return withPickInfo(group, {
    coordinateSystem: "C1 显示坐标系",
    name: camera.name,
    type: "相机",
    position: camera.position,
    details: [
      `位置：${formatPoint(camera.position)}，C1 显示坐标系`,
      `X 轴：${formatPoint(camera.axes.x)}，C1 显示坐标系中的方向向量`,
      `Y 轴：${formatPoint(camera.axes.y)}，C1 显示坐标系中的方向向量`,
      `Z 轴/光轴：${formatPoint(camera.axes.z)}，C1 显示坐标系中的方向向量`,
    ],
  });
}

function pointMesh(point, color, radius, info = null) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 24, 16),
    new THREE.MeshStandardMaterial({ color, roughness: 0.35 }),
  );
  mesh.position.copy(toVector3(point));
  return info ? withPickInfo(mesh, info) : mesh;
}

function lineMesh(first, second, color, info = null) {
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([toVector3(first), toVector3(second)]),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.75 }),
  );
  return info ? withPickInfo(line, info) : line;
}

function laserLineMesh(first, second, info = null) {
  const direction = normalize(subtractVector(second, first));
  const center = midpoint(first, second);
  const halfLength = 260;
  const start = addVector(center, scaleVector(direction, -halfLength));
  const end = addVector(center, scaleVector(direction, halfLength));
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([toVector3(start), toVector3(end)]),
    new THREE.LineBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.95 }),
  );
  return info ? withPickInfo(line, info) : line;
}

function labelSprite(text, point, deviceModelVisible) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  canvas.width = 640;
  canvas.height = 160;
  context.font = "700 64px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  if (deviceModelVisible) {
    context.lineWidth = 5;
    context.strokeStyle = "rgba(0, 0, 0, 0.72)";
    context.strokeText(text, 18, 104);
    context.fillStyle = "#ffffff";
  } else {
    context.fillStyle = "#000000";
  }
  context.fillText(text, 18, 104);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(toVector3(point));
  sprite.position.y += 3.0;
  sprite.scale.set(18, 4.5, 1);
  return sprite;
}

function InspectionPanel({ info }) {
  const details = info?.details || (info?.position ? [`位置：${formatPoint(info.position)}${info.coordinateSystem ? `，${info.coordinateSystem}` : ""}`] : null);
  return (
    <div className="inspection-panel">
      <div className="inspection-title">{info?.name || "对象信息"}</div>
      <div className="inspection-grid">
        <span>类型</span>
        <strong>{info?.type || "移动鼠标到对象上查看"}</strong>
        {info?.coordinateSystem && (
          <>
            <span>坐标系</span>
            <strong>{info.coordinateSystem}</strong>
          </>
        )}
        {info?.sampleName && (
          <>
            <span>样本</span>
            <strong>{info.sampleName}</strong>
          </>
        )}
        <span>信息</span>
        <strong className="inspection-details">
          {details ? details.map((item) => <em key={item}>{item}</em>) : "未选中"}
        </strong>
      </div>
    </div>
  );
}

function formatPoint(point) {
  return `(${formatNumber(point.x)}, ${formatNumber(point.y)}, ${formatNumber(point.z)})`;
}

function planeEquation(normal, d) {
  return `${formatNumber(normal.x)}x + ${formatNumber(normal.y)}y + ${formatNumber(normal.z)}z + ${formatNumber(d)} = 0`;
}

function methodName(method) {
  const names = {
    dcpam_device_geometry: "DCPAM 设备几何定义",
    dcpam_reflection_geometry: "DCPAM 反射镜几何定义",
    mirror_reflection: "由实像面关于反射面镜像得到",
    pnp_frame_pose: "PnP 目标定位法",
  };
  return names[method] || method;
}

function rectBounds(corners) {
  const xs = corners.map((point) => point.x);
  const ys = corners.map((point) => point.y);
  return {
    xMin: Math.min(...xs),
    xMax: Math.max(...xs),
    yMin: Math.min(...ys),
    yMax: Math.max(...ys),
  };
}

function formatNumber(value) {
  return Number.isFinite(value) ? value.toFixed(3) : "";
}

function midpoint(first, second) {
  return {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2,
    z: (first.z + second.z) / 2,
  };
}

function addVector(first, second) {
  return { x: first.x + second.x, y: first.y + second.y, z: first.z + second.z };
}

function subtractVector(first, second) {
  return { x: first.x - second.x, y: first.y - second.y, z: first.z - second.z };
}

function scaleVector(vector, scale) {
  return { x: vector.x * scale, y: vector.y * scale, z: vector.z * scale };
}

function normalize(vector) {
  const length = Math.hypot(vector.x, vector.y, vector.z);
  if (length < 1e-9) return { x: 0, y: 0, z: 1 };
  return scaleVector(vector, 1 / length);
}

function createAxesView(mount) {
  if (!mount) return null;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.1, 100);
  camera.position.set(0, 0, 14);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(180, 180);
  mount.appendChild(renderer.domElement);

  const root = new THREE.Group();
  root.add(axisArrow("X", 0xd97706, new THREE.Vector3(1, 0, 0)));
  root.add(axisArrow("Y", 0x6b7280, new THREE.Vector3(0, 1, 0)));
  root.add(axisArrow("Z", 0x111114, new THREE.Vector3(0, 0, 1)));
  scene.add(root);
  scene.add(new THREE.AmbientLight(0xffffff, 1.0));
  return { camera, renderer, root, scene, mount };
}

function axisArrow(label, color, direction) {
  const group = new THREE.Group();
  const origin = new THREE.Vector3(0, 0, 0);
  const labelPoint = direction.clone().multiplyScalar(3.75);
  const arrow = new THREE.ArrowHelper(direction, origin, 3.25, color, 0.64, 0.32);
  const sprite = axisLabelSprite(label, { x: labelPoint.x, y: labelPoint.y, z: labelPoint.z }, color);
  group.add(arrow);
  group.add(sprite);
  return group;
}

function axisLabelSprite(text, point, color) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  canvas.width = 128;
  canvas.height = 96;
  context.font = "700 58px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, 64, 48);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(toVector3(point));
  sprite.scale.set(1.45, 1.1, 1);
  return sprite;
}

function renderAxesView(axes, mainCamera, geometry) {
  if (!axes) return;
  axes.mount.style.display = "block";
  axes.root.quaternion.copy(mainCamera.quaternion).invert().multiply(deviceQuaternion(geometry));
  axes.renderer.render(axes.scene, axes.camera);
}

function deviceQuaternion(geometry) {
  const axes = deviceAxes(geometry);
  const matrix = new THREE.Matrix4().makeBasis(axes.x, axes.y, axes.z);
  return new THREE.Quaternion().setFromRotationMatrix(matrix);
}

function deviceAxes(geometry) {
  const rows = geometry?.deviceAlignment?.matrix;
  if (!rows) {
    return {
      x: new THREE.Vector3(1, 0, 0),
      y: new THREE.Vector3(0, 1, 0),
      z: new THREE.Vector3(0, 0, 1),
    };
  }
  return {
    x: new THREE.Vector3(rows[0][0], rows[1][0], rows[2][0]).normalize(),
    y: new THREE.Vector3(rows[0][1], rows[1][1], rows[2][1]).normalize(),
    z: new THREE.Vector3(rows[0][2], rows[1][2], rows[2][2]).normalize(),
  };
}

function setHomeView(camera, controls) {
  setCameraView(camera, controls, new THREE.Vector3(-0.538, -0.785, 0.308), new THREE.Vector3(0, 0, 1));
}

function setViewAlongY(camera, controls) {
  setCameraView(camera, controls, new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1));
}

function setCameraView(camera, controls, offsetDirection, upDirection) {
  const target = controls.target.clone();
  const distance = Math.max(20, camera.position.distanceTo(target));
  camera.up.copy(upDirection).normalize();
  camera.position.copy(target.clone().add(offsetDirection.clone().normalize().multiplyScalar(distance)));
  camera.lookAt(target);
  camera.updateProjectionMatrix();
  controls.update();
}

function fitCamera(camera, controls, geometry, mount) {
  const points = [];
  if (geometry) {
    geometry.planes.forEach((plane) => points.push(...plane.corners));
    geometry.frames.forEach((frame) => {
      points.push(frame.origin);
      points.push(...frame.corners);
    });
    geometry.cameras.forEach((item) => points.push(...cameraBounds(item)));
    (geometry.coordinateFrames || []).forEach((frame) => points.push(frame.origin));
    (geometry.opticalAxes || []).forEach((axis) => {
      points.push(axis.origin);
      points.push(axis.end);
    });
    const device = deviceBounds(geometry);
    if (device) points.push(...device);
  }
  if (!points.length) return;
  const box = new THREE.Box3().setFromPoints(points.map(toVector3));
  const center = box.getCenter(new THREE.Vector3());
  const size = Math.max(12, box.getSize(new THREE.Vector3()).length());
  controls.target.copy(center);
  camera.up.set(0, 0, 1);
  camera.position.copy(center.clone().add(new THREE.Vector3(-0.538, -0.785, 0.308).normalize().multiplyScalar(size * 1.4)));
  camera.near = Math.max(0.01, size / 1000);
  camera.far = Math.max(1000, size * 20);
  camera.userData.viewSize = size * 0.62;
  applyOrthoFrustum(camera, mount);
  controls.update();
}

function applyOrthoFrustum(camera, mount) {
  const rect = mount.getBoundingClientRect();
  const aspect = rect.width / Math.max(rect.height, 1);
  const halfHeight = camera.userData.viewSize;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.updateProjectionMatrix();
}

function cameraBounds(camera) {
  const center = toVector3(camera.position);
  const radius = CAMERA_MODEL_SCALE * 5.8;
  return [
    toPointFromVector(center.clone().add(new THREE.Vector3(-radius, -radius, -radius))),
    toPointFromVector(center.clone().add(new THREE.Vector3(radius, radius, radius))),
  ];
}

function deviceBounds(geometry) {
  const device = geometry.device;
  if (!device) return null;
  const points = [
    ...basePlateCornerPoints(device.basePlate),
    ...device.frames.flatMap((frame) => viewFrameCornerPoints(frame, device.viewFrame)),
    ...device.frames.flatMap((frame) => frostedGlassCornerPoints(frame, device.frostedGlass)),
    ...device.reflections.flatMap(reflectionMirrorCornerPoints),
    ...probeRodBounds(device.probeRod),
  ];
  if (!geometry.deviceAlignment?.transformPoint) return points;
  return points.map((point) => toPointFromArray(geometry.deviceAlignment.transformPoint([point.x, point.y, point.z])));
}

function frostedGlassCornerPoints(frame, glass) {
  const { xMin, xMax, yMin, yMax } = rectBounds(frame.outerCorners);
  const zMin = frame.center.z;
  const zMax = frame.center.z + glass.thickness;
  return [
    { x: xMin, y: yMin, z: zMin },
    { x: xMax, y: yMin, z: zMin },
    { x: xMax, y: yMax, z: zMin },
    { x: xMin, y: yMax, z: zMin },
    { x: xMin, y: yMin, z: zMax },
    { x: xMax, y: yMin, z: zMax },
    { x: xMax, y: yMax, z: zMax },
    { x: xMin, y: yMax, z: zMax },
  ];
}

function reflectionMirrorCornerPoints(reflection) {
  return Array.from(reflectionMirrorGeometry(reflection).attributes.position.array)
    .reduce((points, value, index, values) => {
      if (index % 3 === 0) points.push({ x: value, y: values[index + 1], z: values[index + 2] });
      return points;
    }, []);
}

function probeRodBounds(spec) {
  return [spec.root, spec.target];
}

function viewFrameCornerPoints(frame, spec) {
  const { xMin, xMax, yMin, yMax } = rectBounds(frame.outerCorners);
  const zMin = frame.center.z - spec.thickness;
  const zMax = frame.center.z;
  return [
    { x: xMin, y: yMin, z: zMin },
    { x: xMax, y: yMin, z: zMin },
    { x: xMax, y: yMax, z: zMin },
    { x: xMin, y: yMax, z: zMin },
    { x: xMin, y: yMin, z: zMax },
    { x: xMax, y: yMin, z: zMax },
    { x: xMax, y: yMax, z: zMax },
    { x: xMin, y: yMax, z: zMax },
  ];
}

function basePlateCornerPoints(bounds) {
  return [
    { x: bounds.xMin, y: bounds.yMin, z: bounds.zMin },
    { x: bounds.xMax, y: bounds.yMin, z: bounds.zMin },
    { x: bounds.xMax, y: bounds.yMax, z: bounds.zMin },
    { x: bounds.xMin, y: bounds.yMax, z: bounds.zMin },
    { x: bounds.xMin, y: bounds.yMin, z: bounds.zMax },
    { x: bounds.xMax, y: bounds.yMin, z: bounds.zMax },
    { x: bounds.xMax, y: bounds.yMax, z: bounds.zMax },
    { x: bounds.xMin, y: bounds.yMax, z: bounds.zMax },
  ];
}

function clearGroup(group) {
  while (group.children.length) {
    const child = group.children.pop();
    child.traverse?.((object) => {
      object.geometry?.dispose?.();
      object.material?.dispose?.();
    });
  }
}
