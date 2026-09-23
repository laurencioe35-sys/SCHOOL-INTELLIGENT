/**
 * Orquestador del espacio 3D. Escucha el Y.Map "pizarra" (sincronizado por
 * CRDT) y renderiza/actualiza los objetos 3D correspondientes cada vez que
 * cambia, sin importar si el cambio vino del profesor, de un alumno, o de
 * un componente generado por el ai-agents-engine (ver UIComponentSchema).
 *
 * NOTA: no compilado/ejecutado en este entorno (requiere proyecto Vite +
 * three.js instalados). Estructura fiel al contrato de datos que sí se
 * probó en el backend (CRDT) y en el motor de agentes (schemas.py).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { useSocket } from "../context/SocketContext";
import { MathRenderer } from "./MathRenderer";

interface BoardObject {
  x?: number;
  y?: number;
  z?: number;
  movedBy?: string;
  shape?: "triangle" | "cube" | "sphere" | "generic";
  color?: string;
  label?: string;
  kind?: "formula" | "highlight";
  text?: string;
}

function position(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function createLabelSprite(label: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 160;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas text rendering is unavailable.");
  context.fillStyle = "rgba(5, 16, 33, 0.88)";
  context.roundRect(0, 0, canvas.width, canvas.height, 32);
  context.fill();
  context.fillStyle = "#ffffff";
  context.font = "bold 54px Arial";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(label.slice(0, 80), canvas.width / 2, canvas.height / 2);
  const material = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(3.6, 0.56, 1);
  return sprite;
}

function disposeSprite(sprite: THREE.Sprite) {
  const material = sprite.material;
  material.map?.dispose();
  material.dispose();
}

export function SceneContainer() {
  const { doc } = useSocket();
  const mountRef = useRef<HTMLDivElement>(null);
  const [objects, setObjects] = useState<Record<string, BoardObject>>({});
  const objectsRef = useRef(objects);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const meshesRef = useRef(new Map<string, THREE.Mesh>());
  const labelsRef = useRef(new Map<string, THREE.Sprite>());
  const annotations = Object.entries(objects).filter(([, item]) => item.kind === "formula" || item.kind === "highlight");

  const syncMeshes = useCallback((boardObjects: Record<string, BoardObject>) => {
    const scene = sceneRef.current;
    if (!scene) return;

    const meshes = meshesRef.current;
    const labels = labelsRef.current;
    for (const [id, mesh] of meshes) {
      if (id in boardObjects) continue;
      scene.remove(mesh);
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
      meshes.delete(id);
      const label = labels.get(id);
      if (label) { scene.remove(label); disposeSprite(label); labels.delete(id); }
    }

    for (const [id, obj] of Object.entries(boardObjects)) {
      if (obj.kind) continue;
      let mesh = meshes.get(id);
      if (!mesh) {
        const geometry = obj.shape === "triangle"
          ? new THREE.ConeGeometry(1, 1, 3)
          : obj.shape === "sphere"
            ? new THREE.SphereGeometry(0.65, 32, 16)
            : new THREE.BoxGeometry(1, 1, 1);
        mesh = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({ color: obj.color ?? "#4f9dff" })
        );
        scene.add(mesh);
        meshes.set(id, mesh);
      }
      mesh.position.set(position(obj.x), position(obj.y), position(obj.z));
      if (obj.label && !labels.has(id)) {
        const label = createLabelSprite(obj.label);
        scene.add(label);
        labels.set(id, label);
      }
      const label = labels.get(id);
      if (label) label.position.set(mesh.position.x, mesh.position.y + 1.1, mesh.position.z);
    }
  }, []);

  // Suscripción reactiva al Y.Map compartido — esta es la pieza que
  // reemplaza el "estado de React local" por el estado CRDT distribuido.
  useEffect(() => {
    const map = doc.getMap<BoardObject>("pizarra");
    const sync = () => setObjects(Object.fromEntries(map.entries()));
    sync();
    map.observe(sync);
    return () => map.unobserve(sync);
  }, [doc]);

  useEffect(() => {
    objectsRef.current = objects;
    syncMeshes(objects);
  }, [objects, syncMeshes]);

  // Setup básico de Three.js (cámara, luces, render loop).
  useEffect(() => {
    if (!mountRef.current) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
    camera.position.set(0, 3, 10);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    const mount = mountRef.current;
    mount.appendChild(renderer.domElement);
    const resize = () => {
      const { clientWidth, clientHeight } = mount;
      if (!clientWidth || !clientHeight) return;
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);

    const light = new THREE.PointLight(0xffffff, 1.2);
    light.position.set(5, 5, 5);
    scene.add(light, new THREE.AmbientLight(0x404040));

    sceneRef.current = scene;
    syncMeshes(objectsRef.current);

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      for (const mesh of meshesRef.current.values()) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      meshesRef.current.clear();
      for (const label of labelsRef.current.values()) {
        scene.remove(label);
        disposeSprite(label);
      }
      labelsRef.current.clear();
      sceneRef.current = null;
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, [syncMeshes]);

  return <div ref={mountRef} style={{ width: "100%", height: "100%", position: "relative" }}>
    {annotations.length > 0 && <aside aria-label="Contenido aprobado de la pizarra" style={{ position: "absolute", top: 16, left: 16, zIndex: 1, maxWidth: "min(440px, calc(100% - 32px))", display: "grid", gap: 8, pointerEvents: "none" }}>
      {annotations.map(([id, item]) => item.kind === "formula" ? <div key={id} style={{ background: "rgba(5, 16, 33, .88)", color: "white", padding: 12, borderRadius: 8 }}><MathRenderer latex={item.text ?? ""} /></div> : <div key={id} style={{ background: "rgba(255, 227, 91, .94)", color: "#182235", padding: 12, borderRadius: 8, fontWeight: 700 }}>{item.text}</div>)}
    </aside>}
  </div>;
}
