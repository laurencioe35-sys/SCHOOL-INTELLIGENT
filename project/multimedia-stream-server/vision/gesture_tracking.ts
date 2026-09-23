/**
 * ⚠️ ARQUITECTURA NO EJECUTADA EN ESTE ENTORNO.
 * Requiere una fuente de video real (webcam del profesor) y, para buen
 * rendimiento en producción, GPU. Aquí no hay cámara ni GPU disponibles,
 * así que este archivo documenta el contrato de datos, no un modelo corriendo.
 *
 * En producción esto usaría `@mediapipe/tasks-vision` (que sí puede correr
 * en el navegador del profesor sin servidor, evitando mandar video crudo
 * al backend) para detectar gestos de mano y emitir eventos que el
 * ai-agents-engine podría usar como señal adicional (ej. "el profesor
 * señaló el objeto 3D X").
 */

// import { GestureRecognizer, FilesetResolver } from "@mediapipe/tasks-vision";
//
// export interface GestureEvent {
//   gesture: "point" | "open_palm" | "thumbs_up" | "none";
//   confidence: number;
//   timestamp: number;
// }
//
// export async function initGestureRecognizer(): Promise<GestureRecognizer> {
//   const vision = await FilesetResolver.forVisionTasks(
//     "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm"
//   );
//   return GestureRecognizer.createFromOptions(vision, {
//     baseOptions: { modelAssetPath: "gesture_recognizer.task" },
//     runningMode: "VIDEO",
//   });
// }

export {};
