/**
 * Orquestador del espacio 3D. Escucha el Y.Map "pizarra" (sincronizado por
 * CRDT) y renderiza/actualiza los objetos 3D correspondientes cada vez que
 * cambia, sin importar si el cambio vino del profesor, de un alumno, o de
 * un componente generado por el ai-agents-engine (ver UIComponentSchema).
 *
 * `videoTrack` (nuevo): si se pasa un MediaStreamTrack de video (de
 * useLiveKitSession), se compone como una THREE.VideoTexture sobre un
 * plano en la escena — esta es la pieza que el comentario anterior
 * describía como pendiente ("el <video> oculto de VideoMixer se usa como
 * fuente de una textura") y que ahora sí está implementada. Compilado y
 * type-checkeado en este entorno (`npx tsc --noEmit`, `npx vite build`);
 * NO se probó contra una pista de video real (requiere una sala LiveKit
 * real, ver hooks/useLiveKitSession.ts).
 */
import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import * as Y from "yjs";
import { useSocket } from "../context/SocketContext";

interface BoardObject {
  x: number;
  y: number;
  z: number;
  movedBy?: string;
  shape?: "triangle" | "cube" | "sphere";
  color?: string;
}

type BoardTool = "cube" | "sphere" | "triangle";

const BOARD_COLORS: Record<BoardTool, string> = {
  cube: "#4cc9ff",
  sphere: "#9efc7a",
  triangle: "#ffc857",
};

export function SceneContainer({
  videoTrack,
  activeTool = "cube",
}: {
  videoTrack?: MediaStreamTrack | null;
  activeTool?: BoardTool;
}) {
  const { doc } = useSocket();
  const mountRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [objects, setObjects] = useState<Record<string, BoardObject>>({});

  // Suscripción reactiva al Y.Map compartido — esta es la pieza que
  // reemplaza el "estado de React local" por el estado CRDT distribuido.
  useEffect(() => {
    const map = doc.getMap<BoardObject>("pizarra");
    const sync = () => setObjects(Object.fromEntries(map.entries()));
    sync();
    map.observe(sync);
    return () => map.unobserve(sync);
  }, [doc]);

  // Elemento <video> oculto, fuente de la textura de video del
  // profesor. Vive fuera del ciclo de vida de Three.js (que se
  // reconstruye completo en el efecto de abajo) para no recrear el
  // elemento <video> — y por lo tanto reiniciar la reproducción — cada
  // vez que cambian los objetos de la pizarra.
  useEffect(() => {
    const video = document.createElement("video");
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    videoRef.current = video;
    return () => {
      videoRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!videoRef.current || !videoTrack) return;
    videoRef.current.srcObject = new MediaStream([videoTrack]);
  }, [videoTrack]);

  useEffect(() => {
    const host = mountRef.current;
    if (!host) return;

    const addObjectAtPointer = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 12;
      const y = (0.5 - (event.clientY - rect.top) / rect.height) * 8;
      const z = -0.5 + Math.random() * 2;
      const map = doc.getMap<BoardObject>("pizarra");
      const id = `obj_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
      doc.transact(() => {
        map.set(id, {
          x,
          y,
          z,
          movedBy: "teacher",
          shape: activeTool,
          color: BOARD_COLORS[activeTool],
        });
      }, "local");
    };

    host.addEventListener("pointerdown", addObjectAtPointer);
    return () => host.removeEventListener("pointerdown", addObjectAtPointer);
  }, [activeTool, doc]);

  // Setup básico de Three.js (cámara, luces, render loop).
  useEffect(() => {
    if (!mountRef.current) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
    camera.position.set(0, 3, 10);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    mountRef.current.appendChild(renderer.domElement);

    const light = new THREE.PointLight(0xffffff, 1.2);
    light.position.set(5, 5, 5);
    scene.add(light, new THREE.AmbientLight(0x404040));

    const meshes = new Map<string, THREE.Mesh>();

    // Plano flotante para el video del profesor: se crea siempre (con
    // una textura vacía) y se activa/desactiva según haya o no track,
    // en vez de añadir/quitar el mesh del scene graph en cada cambio.
    let videoTexture: THREE.VideoTexture | null = null;
    let videoPlane: THREE.Mesh | null = null;
    if (videoRef.current) {
      videoTexture = new THREE.VideoTexture(videoRef.current);
      videoTexture.colorSpace = THREE.SRGBColorSpace;
      const videoMaterial = new THREE.MeshBasicMaterial({ map: videoTexture, toneMapped: false });
      videoPlane = new THREE.Mesh(new THREE.PlaneGeometry(4, 2.25), videoMaterial);
      videoPlane.position.set(0, 4, -3); // detrás y por encima de la pizarra, como una "pantalla" del profesor
      videoPlane.visible = false;
      scene.add(videoPlane);
    }

    function syncMeshes() {
      for (const [id, obj] of Object.entries(objects)) {
        let mesh = meshes.get(id);
        if (!mesh) {
          const geometry =
            obj.shape === "triangle"
              ? new THREE.ConeGeometry(1, 1, 3)
              : new THREE.BoxGeometry(1, 1, 1);
          const material = new THREE.MeshStandardMaterial({ color: obj.color ?? "#4f9dff" });
          mesh = new THREE.Mesh(geometry, material);
          scene.add(mesh);
          meshes.set(id, mesh);
        }
        mesh.position.set(obj.x, obj.y, obj.z);
      }
    }
    syncMeshes();

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      if (videoPlane) {
        // readyState >= 2 (HAVE_CURRENT_DATA) evita mostrar un frame
        // negro mientras el <video> todavía no tiene datos decodificados.
        videoPlane.visible = !!videoRef.current && videoRef.current.readyState >= 2;
      }
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(frameId);
      videoTexture?.dispose();
      renderer.dispose();
      mountRef.current?.removeChild(renderer.domElement);
    };
  }, [objects]);

  return <div ref={mountRef} style={{ width: "100%", height: "100%" }} />;
}
