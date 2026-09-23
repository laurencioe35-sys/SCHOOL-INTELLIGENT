/**
 * ⚠️ ARQUITECTURA NO EJECUTADA EN ESTE ENTORNO.
 * Requiere un SFU real (LiveKit self-hosted o LiveKit Cloud, o Mediasoup)
 * corriendo en un servidor con acceso a puertos UDP/TCP de media y,
 * usualmente, una IP pública o TURN server para NAT traversal. Nada de
 * eso existe en este sandbox, así que este archivo documenta el contrato
 * de integración correcto, no una prueba de funcionamiento.
 *
 * Con LiveKit (recomendado por simplicidad operativa frente a Mediasoup
 * autogestionado), el flujo real sería:
 *
 *   1. El core-erp-backend, al iniciar una ClassSession, pide un token de
 *      acceso a LiveKit (via su Server SDK) para el profesor y lo pasa al
 *      frontend.
 *   2. El frontend (VideoMixer.tsx) se conecta a la sala de LiveKit con
 *      ese token usando el SDK de cliente (`livekit-client`).
 *   3. Este archivo, del lado servidor, solo necesitaría reaccionar a
 *      webhooks de LiveKit (participante entra/sale, track publicado) para
 *      sincronizar el estado con el ERP (ej. marcar `is_live = true`).
 *
 * Pseudocódigo del webhook handler (requiere el paquete `livekit-server-sdk`
 * real y un servidor LiveKit accesible; no se instaló ni se corrió aquí):
 */

// import { WebhookReceiver } from "livekit-server-sdk";
//
// const receiver = new WebhookReceiver(LIVEKIT_API_KEY, LIVEKIT_API_SECRET);
//
// export async function handleLiveKitWebhook(rawBody: string, authHeader: string) {
//   const event = await receiver.receive(rawBody, authHeader);
//   switch (event.event) {
//     case "participant_joined":
//       // notificar al core-erp-backend que un alumno se unió a la sesión
//       break;
//     case "track_published":
//       // si es el track de video del profesor, avisar al ffmpeg_processor
//       // para iniciar el pipeline de filtros/composición si aplica
//       break;
//   }
// }

export {};
