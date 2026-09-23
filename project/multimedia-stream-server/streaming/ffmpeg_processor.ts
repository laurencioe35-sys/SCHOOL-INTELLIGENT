/**
 * ⚠️ ARQUITECTURA NO EJECUTADA EN ESTE ENTORNO.
 * Requiere el binario `ffmpeg` (con soporte de aceleración por hardware
 * para filtros de audio/video en tiempo real) instalado en el Media Pod.
 * No se instaló ni se corrió aquí porque el objetivo de este archivo es
 * documentar el contrato correcto del pipeline, no ejecutar transcodificación
 * real sin una fuente de video real.
 *
 * Este módulo usaría `fluent-ffmpeg` (wrapper de Node sobre el binario) para:
 *   1. Tomar el track de audio del profesor (desde LiveKit/Mediasoup).
 *   2. Aplicar un filtro de "voz en caliente" (ej. cambio de tono/eco) si el
 *      profesor lo activa desde TeacherDashboard.tsx.
 *   3. Re-publicar el audio procesado de vuelta a la sala.
 *
 * Ejemplo de la forma que tendría la función real (no ejecutado):
 */

// import ffmpeg from "fluent-ffmpeg";
// import { PassThrough } from "stream";
//
// export function applyVoiceFilter(inputStream: NodeJS.ReadableStream, filterType: "echo" | "pitch_up"): NodeJS.ReadableStream {
//   const output = new PassThrough();
//   const command = ffmpeg(inputStream).audioFilters(
//     filterType === "echo" ? "aecho=0.8:0.9:1000:0.3" : "asetrate=44100*1.25,atempo=0.8"
//   );
//   command.format("wav").pipe(output);
//   return output;
// }

export {};
