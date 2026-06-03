import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { COLORS, planeColor, pointFromRow, toVector3 } from "./geometry.js";

export function SceneView({ rows, geometry, layers }) {
  const mountRef = useRef(null);
  const axesRef = useRef(null);
  const layersRef = useRef(layers);
  const sceneRef = useRef(null);

  useEffect(() => {
    layersRef.current = layers;
  }, [layers]);

  useEffect(() => {
    const mount = mountRef.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101010);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
    camera.position.set(45, -55, 42);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.72;
    controls.zoomSpeed = 0.9;
    controls.panSpeed = 0.8;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };

    scene.add(new THREE.AmbientLight(0xffffff, 0.68));
    const light = new THREE.DirectionalLight(0xf5e4cc, 0.82);
    light.position.set(30, -45, 60);
    scene.add(light);

    const root = new THREE.Group();
    scene.add(root);

    const axes = createAxesView(axesRef.current);
    sceneRef.current = { root, camera, renderer, controls, mount, axes };

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      renderer.setSize(rect.width, rect.height);
      camera.aspect = rect.width / Math.max(rect.height, 1);
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener("resize", resize);

    let active = true;
    const animate = () => {
      if (!active) return;
      controls.update();
      renderer.render(scene, camera);
      renderAxesView(axes, camera, layersRef.current.axes);
      requestAnimationFrame(animate);
    };
    animate();

    return () => {
      active = false;
      window.removeEventListener("resize", resize);
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
    fitCamera(context.camera, context.controls, rows, geometry);
  }, [rows, geometry]);

  return (
    <div ref={mountRef} className="scene-mount">
      <div ref={axesRef} className="axes-mount" />
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
  }

  rows.forEach((row) => {
    const frontVirtual = pointFromRow(row, "front_virtual", "cf");
    const rearVirtual = pointFromRow(row, "rear_virtual", "cf");
    if (layers.frontVirtual && frontVirtual) root.add(pointMesh(frontVirtual, COLORS.frontVirtual, 0.72));
    if (layers.rearVirtual && rearVirtual) root.add(pointMesh(rearVirtual, COLORS.rearVirtual, 0.72));
    if (layers.realPoints) {
      const frontReal = pointFromRow(row, "front_real", "cf");
      const rearReal = pointFromRow(row, "rear_real", "cr");
      if (frontReal) root.add(pointMesh(frontReal, COLORS.real, 0.42));
      if (rearReal) root.add(pointMesh(rearReal, 0x8a96a8, 0.42));
    }
    if (layers.laserLines && frontVirtual && rearVirtual) {
      root.add(lineMesh(frontVirtual, rearVirtual, 0x8995a8));
    }
  });
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
  return group;
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
  return group;
}

function pointMesh(point, color, radius) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 24, 16),
    new THREE.MeshStandardMaterial({ color, roughness: 0.35 }),
  );
  mesh.position.copy(toVector3(point));
  return mesh;
}

function lineMesh(first, second, color) {
  return new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([toVector3(first), toVector3(second)]),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.75 }),
  );
}

function labelSprite(text, point, color) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  canvas.width = 256;
  canvas.height = 64;
  context.font = "28px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.fillStyle = "rgba(16,16,16,0.78)";
  context.fillRect(0, 0, 256, 64);
  context.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
  context.fillText(text, 12, 40);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(toVector3(point));
  sprite.position.y += 1.5;
  sprite.scale.set(8, 2, 1);
  return sprite;
}

function createAxesView(mount) {
  if (!mount) return null;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(0, 0, 10);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(126, 126);
  mount.appendChild(renderer.domElement);

  const root = new THREE.Group();
  root.add(axisArrow("X", 0xe7c59a, new THREE.Vector3(1, 0, 0)));
  root.add(axisArrow("Y", 0xc1c1c1, new THREE.Vector3(0, 1, 0)));
  root.add(axisArrow("Z", 0xf3f3f3, new THREE.Vector3(0, 0, 1)));
  scene.add(root);
  scene.add(new THREE.AmbientLight(0xffffff, 1.0));
  return { camera, renderer, root, scene, mount };
}

function axisArrow(label, color, direction) {
  const group = new THREE.Group();
  const origin = new THREE.Vector3(0, 0, 0);
  const end = direction.clone().multiplyScalar(3.2);
  const arrow = new THREE.ArrowHelper(direction, origin, 3.2, color, 0.52, 0.26);
  const sprite = labelSprite(label, { x: end.x, y: end.y, z: end.z }, color);
  sprite.scale.set(1.6, 0.4, 1);
  group.add(arrow);
  group.add(sprite);
  return group;
}

function renderAxesView(axes, mainCamera, visible) {
  if (!axes) return;
  axes.mount.style.display = visible ? "block" : "none";
  if (!visible) return;
  axes.root.quaternion.copy(mainCamera.quaternion).invert();
  axes.renderer.render(axes.scene, axes.camera);
}

function fitCamera(camera, controls, rows, geometry) {
  const points = [];
  rows.forEach((row) => {
    ["front_virtual", "rear_virtual"].forEach((prefix) => {
      const point = pointFromRow(row, prefix, "cf");
      if (point) points.push(point);
    });
  });
  if (geometry) {
    geometry.planes.forEach((plane) => points.push(...plane.corners));
    geometry.cameras.forEach((item) => points.push(item.position));
  }
  if (!points.length) return;
  const box = new THREE.Box3().setFromPoints(points.map(toVector3));
  const center = box.getCenter(new THREE.Vector3());
  const size = Math.max(12, box.getSize(new THREE.Vector3()).length());
  controls.target.copy(center);
  camera.position.copy(center.clone().add(new THREE.Vector3(size * 0.7, -size * 0.9, size * 0.65)));
  camera.near = Math.max(0.01, size / 1000);
  camera.far = Math.max(1000, size * 20);
  camera.updateProjectionMatrix();
  controls.update();
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
