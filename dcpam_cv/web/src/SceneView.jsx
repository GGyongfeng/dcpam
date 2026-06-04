import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { TrackballControls } from "three/examples/jsm/controls/TrackballControls.js";

import { COLORS, planeColor, pointFromRow, toVector3 } from "./geometry.js";

export function SceneView({ rows, geometry, layers }) {
  const mountRef = useRef(null);
  const axesRef = useRef(null);
  const layersRef = useRef(layers);
  const sceneRef = useRef(null);
  const [inspection, setInspection] = useState(null);
  const [viewDirection, setViewDirection] = useState({ x: 0, y: 0, z: 0 });

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
      renderAxesView(axes, camera);
      if (frameIndex % 8 === 0) {
        setViewDirection(directionFromCamera(camera, controls));
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
  }, [rows, geometry, layers]);

  useEffect(() => {
    const context = sceneRef.current;
    if (!context) return;
    fitCamera(context.camera, context.controls, rows, geometry, context.mount);
  }, [rows, geometry]);

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
        <div className="view-direction">视向 {formatPoint(viewDirection)}</div>
      </div>
      <InspectionPanel info={inspection} />
    </div>
  );
}

function buildScene(root, rows, geometry, layers) {
  if (geometry) {
    geometry.planes.forEach((plane) => {
      if (plane.kind === "image" && !layers.imagePlanes) return;
      if (plane.kind === "reflection" && !layers.reflectionPlanes) return;
      if (plane.kind === "virtual" && !layers.virtualPlanes) return;
      root.add(planeMesh(plane));
      if (layers.labels) root.add(labelSprite(plane.label, plane.point, planeColor(plane.kind)));
    });
    if (layers.cameras) {
      geometry.cameras.forEach((camera) => {
        root.add(cameraMesh(camera));
        if (layers.labels) root.add(labelSprite(camera.name, camera.position, camera.color));
      });
    }
    if (layers.deviceModel) {
      const device = deviceModelMesh(geometry);
      if (device) root.add(device);
    }
    if (layers.opticalAxes) {
      (geometry.opticalAxes || []).forEach((axis) => {
        root.add(opticalAxisMesh(axis));
        if (layers.labels) root.add(labelSprite(axis.label, axis.end, axis.color));
      });
    }
    if (layers.frames) {
      geometry.frames.forEach((frame) => {
        root.add(frameMesh(frame));
        if (layers.labels) root.add(labelSprite(frame.label, frame.origin, COLORS.frame));
      });
    }
  }

  rows.forEach((row) => {
    const frontVirtual = pointFromRow(row, "front_virtual", "cf");
    const rearVirtual = pointFromRow(row, "rear_virtual", "cf");
    if (layers.frontVirtual && frontVirtual) {
      addPoint(root, frontVirtual, COLORS.frontVirtual, 0.72, pointInfo("前虚像点", "虚像点", frontVirtual, row.name));
    }
    if (layers.rearVirtual && rearVirtual) {
      addPoint(root, rearVirtual, COLORS.rearVirtual, 0.72, pointInfo("后虚像点", "虚像点", rearVirtual, row.name));
    }
    if (layers.realPoints) {
      const frontReal = pointFromRow(row, "front_real", "cf");
      const rearReal = pointFromRow(row, "rear_real", "cr");
      if (frontReal) {
        addPoint(root, frontReal, COLORS.real, 0.42, pointInfo("前实像点", "实像点", frontReal, row.name));
      }
      if (rearReal) {
        addPoint(root, rearReal, 0x8a96a8, 0.42, pointInfo("后实像点", "实像点", rearReal, row.name));
      }
    }
    if (layers.laserLines && frontVirtual && rearVirtual) {
      root.add(lineMesh(frontVirtual, rearVirtual, 0x8995a8, {
        name: row.name,
        type: "激光点连线",
        position: midpoint(frontVirtual, rearVirtual),
      }));
    }
  });
}

function addPoint(root, point, color, radius, info) {
  root.add(pointMesh(point, color, radius, info));
}

function pointInfo(name, type, position, sampleName) {
  return {
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
    name: plane.label,
    type: planeTypeName(plane.kind),
    position: plane.point,
  });
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
  group.add(frameAxis(frame.origin, frame.axes.x, 0xd97706, 5.0));
  group.add(frameAxis(frame.origin, frame.axes.y, 0x6b7280, 4.0));
  group.add(frameAxis(frame.origin, frame.axes.z, 0x111114, 4.0));
  return withPickInfo(group, {
    name: frame.label,
    type: "取景框",
    position: frame.origin,
  });
}

function deviceModelMesh(geometry) {
  const frontFrame = geometry.frames.find((frame) => frame.label === "front frame");
  const rearFrame = geometry.frames.find((frame) => frame.label === "rear frame");
  if (!frontFrame || !rearFrame) return null;

  const group = new THREE.Group();
  group.add(viewFrameAssembly(0, 0x5aaee8, "前取景框"));
  group.add(viewFrameAssembly(80, 0x4f5661, "后取景框"));
  group.add(frostedGlassAssembly(0, "前毛玻璃片"));
  group.add(frostedGlassAssembly(80, "后毛玻璃片"));
  group.add(reflectionMirrorAssembly(0, 0x8c7f93, "前反射镜"));
  group.add(reflectionMirrorAssembly(80, 0x756f7d, "后反射镜"));
  group.add(basePlateMesh());
  group.add(probeRodMesh());
  return group;
}

function viewFrameAssembly(xCenter, color, name) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color, metalness: 0.18, roughness: 0.42 });
  const geometry = viewFrameGeometry(xCenter);
  const mesh = new THREE.Mesh(geometry, material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x2f4d5d, transparent: true, opacity: 0.75 }),
  );
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    name,
    type: "取景框实体",
    position: { x: xCenter, y: 0, z: 0 },
    details: viewFrameDetails(xCenter),
  });
}

function viewFrameGeometry(xCenter) {
  const spec = viewFrameSpec();
  const outer = roundedRectPath(
    xCenter - spec.outerWidth / 2,
    xCenter + spec.outerWidth / 2,
    -spec.outerHeight / 2,
    spec.outerHeight / 2,
    spec.outerRadius,
  );
  const inner = roundedRectPath(
    xCenter - spec.innerWidth / 2,
    xCenter + spec.innerWidth / 2,
    -spec.innerHeight / 2,
    spec.innerHeight / 2,
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

function viewFrameSpec() {
  return {
    innerWidth: 22,
    innerHeight: 17,
    innerRadius: 1.5,
    outerWidth: 46,
    outerHeight: 47,
    outerRadius: 2.5,
    thickness: 2,
  };
}

function viewFrameDetails(xCenter) {
  const spec = viewFrameSpec();
  return [
    `中心点：${formatPoint({ x: xCenter, y: 0, z: 0 })}`,
    `透空尺寸：X=${formatNumber(spec.innerWidth)}mm，Y=${formatNumber(spec.innerHeight)}mm`,
    `透空圆角：R=${formatNumber(spec.innerRadius)}mm`,
    `实体外形：X=${formatNumber(spec.outerWidth)}mm，Y=${formatNumber(spec.outerHeight)}mm`,
    `厚度：沿 -Z 方向 ${formatNumber(spec.thickness)}mm，背面贴 Z=0`,
  ];
}

function frostedGlassAssembly(xCenter, name) {
  const geometry = frostedGlassGeometry(xCenter);
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
    name,
    type: "毛玻璃片",
    position: { x: xCenter, y: 0, z: 1.5 },
    details: frostedGlassDetails(xCenter),
  });
}

function frostedGlassGeometry(xCenter) {
  const frame = viewFrameSpec();
  const glass = frostedGlassSpec();
  const shape = roundedRectPath(
    xCenter - frame.outerWidth / 2,
    xCenter + frame.outerWidth / 2,
    -frame.outerHeight / 2,
    frame.outerHeight / 2,
    frame.outerRadius,
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

function frostedGlassSpec() {
  return {
    thickness: 3,
  };
}

function frostedGlassDetails(xCenter) {
  const frame = viewFrameSpec();
  const glass = frostedGlassSpec();
  return [
    `中心点：${formatPoint({ x: xCenter, y: 0, z: glass.thickness / 2 })}`,
    `前表面：Z=0`,
    `厚度：沿 +Z 方向 ${formatNumber(glass.thickness)}mm`,
    `外形：X=${formatNumber(frame.outerWidth)}mm，Y=${formatNumber(frame.outerHeight)}mm，R=${formatNumber(frame.outerRadius)}mm`,
  ];
}

function reflectionMirrorAssembly(xOffset, color, name) {
  const group = new THREE.Group();
  const geometry = reflectionMirrorGeometry(xOffset);
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
    name,
    type: "反射镜",
    position: reflectionMirrorCenter(xOffset),
    details: reflectionMirrorDetails(xOffset),
  });
}

function reflectionMirrorGeometry(xOffset) {
  const spec = reflectionMirrorSpec();
  const { xMin, xMax } = reflectionMirrorXRange(xOffset, spec.width);
  const yMin = -spec.height / 2;
  const yMax = spec.height / 2;
  const front = [
    { x: xMin, y: yMin, z: reflectionMirrorZ(xMin, xOffset) },
    { x: xMax, y: yMin, z: reflectionMirrorZ(xMax, xOffset) },
    { x: xMax, y: yMax, z: reflectionMirrorZ(xMax, xOffset) },
    { x: xMin, y: yMax, z: reflectionMirrorZ(xMin, xOffset) },
  ];
  const back = front.map((point) => ({ ...point, z: point.z + spec.thickness }));
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

function reflectionMirrorSpec() {
  const frame = viewFrameSpec();
  return {
    width: 21.2,
    height: frame.outerHeight,
    thickness: 1,
  };
}

function reflectionMirrorXRange(xOffset, mirrorWidth) {
  const halfXSpan = mirrorWidth / (2 * Math.SQRT2);
  return {
    xMin: xOffset - halfXSpan,
    xMax: xOffset + halfXSpan,
  };
}

function reflectionMirrorZ(x, xOffset) {
  return -(x - xOffset) + 23;
}

function reflectionMirrorCenter(xOffset) {
  const spec = reflectionMirrorSpec();
  return {
    x: xOffset,
    y: 0,
    z: reflectionMirrorZ(xOffset, xOffset) + spec.thickness / 2,
  };
}

function reflectionMirrorDetails(xOffset) {
  const spec = reflectionMirrorSpec();
  const center = reflectionMirrorCenter(xOffset);
  return [
    `中心点：${formatPoint(center)}`,
    `前平面：z = -(x - ${formatNumber(xOffset)}) + 23`,
    `尺寸：镜面宽 ${formatNumber(spec.width)}mm，高 ${formatNumber(spec.height)}mm`,
    `厚度：沿 +Z 方向 ${formatNumber(spec.thickness)}mm`,
  ];
}

function basePlateMesh() {
  const bounds = basePlateBounds();
  const center = new THREE.Vector3(
    (bounds.xMin + bounds.xMax) / 2,
    (bounds.yMin + bounds.yMax) / 2,
    (bounds.zMin + bounds.zMax) / 2,
  );
  const material = new THREE.MeshStandardMaterial({
    color: 0xd8d8d2,
    depthTest: true,
    depthWrite: true,
    metalness: 0.16,
    opacity: 1,
    roughness: 0.48,
    transparent: false,
  });
  const mesh = new THREE.Mesh(basePlateGeometry(bounds, 3), material);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: 0x777a76, transparent: true, opacity: 0.72 }),
  );
  const group = new THREE.Group();
  group.add(mesh);
  group.add(edges);
  return withPickInfo(group, {
    name: "底座",
    type: "设备底座",
    position: toPointFromVector(center),
    details: basePlateDetails(bounds),
  });
}

function basePlateGeometry(bounds, radius) {
  const shape = roundedRectPath(bounds.xMin, bounds.xMax, bounds.zMin, bounds.zMax, radius);
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

function basePlateBounds() {
  return {
    xMin: -23,
    xMax: 105,
    yMin: 23.5,
    yMax: 29.5,
    zMin: -132,
    zMax: 42,
  };
}

function basePlateDetails(bounds) {
  return [
    `上平面：Y=${formatNumber(bounds.yMin)}mm`,
    `下平面：Y=${formatNumber(bounds.yMax)}mm`,
    `X 范围：${formatNumber(bounds.xMin)}mm 到 ${formatNumber(bounds.xMax)}mm，宽度 ${formatNumber(bounds.xMax - bounds.xMin)}mm`,
    `Z 范围：${formatNumber(bounds.zMin)}mm 到 ${formatNumber(bounds.zMax)}mm，长度 ${formatNumber(bounds.zMax - bounds.zMin)}mm`,
    `厚度：${formatNumber(bounds.yMax - bounds.yMin)}mm`,
    "圆角：R=3.000mm",
  ];
}

function probeRodMesh() {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: 0xbfc1bd, metalness: 0.32, roughness: 0.28 });
  const spec = probeRodSpec();
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
  group.add(probeRodConnector(spec, material));
  group.add(cylinder);
  group.add(tip);
  return withPickInfo(group, {
    name: "测量探杆",
    type: "探杆",
    position: spec.root,
    details: probeRodDetails(spec),
  });
}

function probeRodConnector(spec, material) {
  const baseY = basePlateBounds().yMax;
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

function probeRodSpec() {
  return {
    root: { x: 41, y: 37, z: -132 },
    target: { x: 41, y: 37, z: -241 },
    rodRadius: 0.9,
    tipHeight: 5.0,
    connectorRadius: 13,
    connectorLength: 8,
  };
}

function probeRodLength(spec) {
  return toVector3(spec.root).distanceTo(toVector3(spec.target));
}

function probeRodDetails(spec) {
  return [
    `根部坐标：${formatPoint(spec.root)}`,
    `靶点坐标：${formatPoint(spec.target)}`,
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

function frameBasis(frame) {
  return {
    x: toVector3(frame.axes.x).normalize(),
    y: toVector3(frame.axes.y).normalize(),
    z: toVector3(frame.axes.z).normalize(),
  };
}

function localPoint(origin, axes, values) {
  return toVector3(origin)
    .add(axes.x.clone().multiplyScalar(values[0]))
    .add(axes.y.clone().multiplyScalar(values[1]))
    .add(axes.z.clone().multiplyScalar(values[2]));
}

function orientedBox(center, axes, size, material) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(size[0], size[1], size[2]), material);
  const matrix = new THREE.Matrix4().makeBasis(axes.x, axes.y, axes.z);
  matrix.setPosition(center);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.copy(matrix);
  return mesh;
}

function planeQuad(origin, axes, width, height, material) {
  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const points = [
    localPoint(origin, axes, [-halfWidth, -halfHeight, 0.08]),
    localPoint(origin, axes, [halfWidth, -halfHeight, 0.08]),
    localPoint(origin, axes, [halfWidth, halfHeight, 0.08]),
    localPoint(origin, axes, [-halfWidth, halfHeight, 0.08]),
  ];
  const quad = new THREE.Mesh(
    new THREE.BufferGeometry().setFromPoints(points),
    material,
  );
  quad.geometry.setIndex([0, 1, 2, 0, 2, 3]);
  quad.geometry.computeVertexNormals();
  return quad;
}

function toPointFromVector(vector) {
  return { x: vector.x, y: vector.y, z: vector.z };
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
    name: axis.label,
    type: "光轴",
    position: axis.origin,
  });
}

function cameraMesh(camera) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({
    color: camera.color,
    metalness: 0.18,
    roughness: 0.34,
  });
  const dark = new THREE.MeshStandardMaterial({ color: 0x141923, metalness: 0.2, roughness: 0.28 });
  const glass = new THREE.MeshStandardMaterial({
    color: 0x1a1a1a,
    emissive: 0x050505,
    metalness: 0.1,
    roughness: 0.18,
  });

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(3.4, 1.9, 1.8),
    material,
  );
  const top = new THREE.Mesh(
    new THREE.BoxGeometry(1.5, 0.48, 0.95),
    material,
  );
  const lensBarrel = new THREE.Mesh(
    new THREE.CylinderGeometry(0.72, 0.82, 1.55, 40),
    dark,
  );
  const lensGlass = new THREE.Mesh(
    new THREE.CylinderGeometry(0.55, 0.55, 0.12, 40),
    glass,
  );
  const mount = new THREE.Mesh(
    new THREE.CylinderGeometry(0.98, 0.98, 0.36, 40),
    material,
  );
  const sensor = new THREE.Mesh(
    new THREE.BoxGeometry(1.25, 0.9, 0.08),
    new THREE.MeshStandardMaterial({ color: 0x0d1117, roughness: 0.4 }),
  );
  top.position.set(-0.35, 1.18, -0.18);
  mount.rotation.x = Math.PI / 2;
  mount.position.z = 1.05;
  lensBarrel.rotation.x = Math.PI / 2;
  lensBarrel.position.z = 1.85;
  lensGlass.rotation.x = Math.PI / 2;
  lensGlass.position.z = 2.68;
  sensor.position.z = -0.95;
  group.add(body);
  group.add(top);
  group.add(mount);
  group.add(lensBarrel);
  group.add(lensGlass);
  group.add(sensor);
  group.position.copy(toVector3(camera.position));
  return withPickInfo(group, {
    name: camera.name,
    type: "相机",
    position: camera.position,
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

function labelSprite(text, point) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  canvas.width = 256;
  canvas.height = 64;
  context.font = "28px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.fillStyle = "#111114";
  context.fillText(text, 12, 40);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(toVector3(point));
  sprite.position.y += 1.5;
  sprite.scale.set(8, 2, 1);
  return sprite;
}

function InspectionPanel({ info }) {
  const details = info?.details || (info?.position ? [formatPoint(info.position)] : null);
  return (
    <div className="inspection-panel">
      <div className="inspection-title">{info?.name || "对象信息"}</div>
      <div className="inspection-grid">
        <span>类型</span>
        <strong>{info?.type || "移动鼠标到对象上查看"}</strong>
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

function renderAxesView(axes, mainCamera) {
  if (!axes) return;
  axes.mount.style.display = "block";
  axes.root.quaternion.copy(mainCamera.quaternion).invert();
  axes.renderer.render(axes.scene, axes.camera);
}

function directionFromCamera(camera, controls) {
  const direction = controls.target.clone().sub(camera.position).normalize();
  return { x: direction.x, y: direction.y, z: direction.z };
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

function fitCamera(camera, controls, rows, geometry, mount) {
  const points = [];
  rows.forEach((row) => {
    ["front_virtual", "rear_virtual"].forEach((prefix) => {
      const point = pointFromRow(row, prefix, "cf");
      if (point) points.push(point);
    });
  });
  if (geometry) {
    geometry.planes.forEach((plane) => points.push(...plane.corners));
    geometry.frames.forEach((frame) => {
      points.push(frame.origin);
      points.push(...frame.corners);
    });
    geometry.cameras.forEach((item) => points.push(item.position));
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

function deviceBounds(geometry) {
  const frontFrame = geometry.frames.find((frame) => frame.label === "front frame");
  const rearFrame = geometry.frames.find((frame) => frame.label === "rear frame");
  if (!frontFrame || !rearFrame) return null;
  const axes = frameBasis(frontFrame);
  const frontOrigin = toVector3(frontFrame.origin);
  const rearOrigin = toVector3(rearFrame.origin);
  const center = frontOrigin.clone().add(rearOrigin).multiplyScalar(0.5);
  const span = Math.max(34, frontOrigin.distanceTo(rearOrigin) + 34);
  return [
    ...basePlateCornerPoints(),
    ...viewFrameCornerPoints(0),
    ...viewFrameCornerPoints(80),
    ...frostedGlassCornerPoints(0),
    ...frostedGlassCornerPoints(80),
    ...reflectionMirrorCornerPoints(0),
    ...reflectionMirrorCornerPoints(80),
    ...probeRodBounds(),
    toPointFromVector(center.clone().add(axes.x.clone().multiplyScalar(span))),
    toPointFromVector(center.clone().add(axes.x.clone().multiplyScalar(-span))),
    toPointFromVector(center.clone().add(axes.y.clone().multiplyScalar(-45))),
    toPointFromVector(center.clone().add(axes.z.clone().multiplyScalar(-28))),
    toPointFromVector(center.clone().add(axes.z.clone().multiplyScalar(16))),
  ];
}

function frostedGlassCornerPoints(xCenter) {
  const frame = viewFrameSpec();
  const glass = frostedGlassSpec();
  const xMin = xCenter - frame.outerWidth / 2;
  const xMax = xCenter + frame.outerWidth / 2;
  const yMin = -frame.outerHeight / 2;
  const yMax = frame.outerHeight / 2;
  return [
    { x: xMin, y: yMin, z: 0 },
    { x: xMax, y: yMin, z: 0 },
    { x: xMax, y: yMax, z: 0 },
    { x: xMin, y: yMax, z: 0 },
    { x: xMin, y: yMin, z: glass.thickness },
    { x: xMax, y: yMin, z: glass.thickness },
    { x: xMax, y: yMax, z: glass.thickness },
    { x: xMin, y: yMax, z: glass.thickness },
  ];
}

function reflectionMirrorCornerPoints(xOffset) {
  const spec = reflectionMirrorSpec();
  const { xMin, xMax } = reflectionMirrorXRange(xOffset, spec.width);
  const yMin = -spec.height / 2;
  const yMax = spec.height / 2;
  return [
    { x: xMin, y: yMin, z: reflectionMirrorZ(xMin, xOffset) },
    { x: xMax, y: yMin, z: reflectionMirrorZ(xMax, xOffset) },
    { x: xMax, y: yMax, z: reflectionMirrorZ(xMax, xOffset) },
    { x: xMin, y: yMax, z: reflectionMirrorZ(xMin, xOffset) },
    { x: xMin, y: yMin, z: reflectionMirrorZ(xMin, xOffset) + spec.thickness },
    { x: xMax, y: yMin, z: reflectionMirrorZ(xMax, xOffset) + spec.thickness },
    { x: xMax, y: yMax, z: reflectionMirrorZ(xMax, xOffset) + spec.thickness },
    { x: xMin, y: yMax, z: reflectionMirrorZ(xMin, xOffset) + spec.thickness },
  ];
}

function probeRodBounds() {
  const spec = probeRodSpec();
  return [spec.root, spec.target];
}

function viewFrameCornerPoints(xCenter) {
  const spec = viewFrameSpec();
  const xMin = xCenter - spec.outerWidth / 2;
  const xMax = xCenter + spec.outerWidth / 2;
  const yMin = -spec.outerHeight / 2;
  const yMax = spec.outerHeight / 2;
  const zMin = -spec.thickness;
  const zMax = 0;
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

function basePlateCornerPoints() {
  const bounds = basePlateBounds();
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
