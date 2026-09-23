/**
 * Canvas de composición: dibuja el video del profesor (via WebRTC/LiveKit,
 * ver streaming/webrtc_handler.ts) como una textura incrustada dentro de la
 * escena 3D, en vez de mostrarlo en un <video> aparte. No compilado/
 * ejecutado en este entorno (requiere una pista de video real de LiveKit).
 */
import React, { useEffect, useRef } from "react";

export function VideoMixer({ videoTrack }: { videoTrack: MediaStreamTrack | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoRef.current || !videoTrack) return;
    const stream = new MediaStream([videoTrack]);
    videoRef.current.srcObject = stream;
  }, [videoTrack]);

  // En producción, este <video> oculto se usa como fuente para un
  // THREE.VideoTexture aplicado a un plano dentro de SceneContainer,
  // en vez de mostrarse directamente en el DOM.
  return <video ref={videoRef} autoPlay muted style={{ display: "none" }} />;
}
