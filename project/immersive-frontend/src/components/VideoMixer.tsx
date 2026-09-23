/**
 * Vista previa pequeña ("self-view") de la propia cámara del profesor —
 * el mismo <video> oculto que antes no se usaba en ningún lado, ahora
 * mostrado de verdad como una miniatura flotante, para que el docente
 * confirme que su cámara se está transmitiendo. La composición dentro
 * del espacio 3D (lo que SÍ ven los alumnos) la hace SceneContainer
 * directamente vía THREE.VideoTexture, no este componente — este es
 * solo el monitor local del emisor.
 */
import React, { useEffect, useRef } from "react";

export function VideoMixer({ videoTrack }: { videoTrack: MediaStreamTrack | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoRef.current || !videoTrack) return;
    const stream = new MediaStream([videoTrack]);
    videoRef.current.srcObject = stream;
  }, [videoTrack]);

  if (!videoTrack) return null;

  return (
    <video
      ref={videoRef}
      autoPlay
      muted
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        width: 180,
        borderRadius: 8,
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
        transform: "scaleX(-1)", // efecto espejo, como cualquier self-view de videollamada
      }}
    />
  );
}
