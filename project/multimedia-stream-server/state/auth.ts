/**
 * Verificación de tokens de sesión emitidos por core-erp-backend/api/auth.py.
 *
 * IMPORTANTE: esto replica EXACTAMENTE el mismo esquema (HMAC-SHA256 sobre
 * un payload JSON en base64url) para que un token emitido por el backend
 * Python sea válido aquí sin necesidad de una llamada de red entre
 * servicios. Ambos deben compartir el mismo ERP_SECRET_KEY (ver .env).
 *
 * Si el esquema de auth.py cambia, este archivo se desincroniza — es la
 * misma fragilidad de cualquier verificación de JWT duplicada en dos
 * lenguajes; la alternativa en producción sería un servicio de auth
 * centralizado que ambos consulten, o migrar a una librería JWT estándar
 * (RS256 con llave pública compartida) en vez de HMAC casero.
 */
import { createHmac, timingSafeEqual } from "crypto";
import { createClient } from "redis";

export interface TokenPayload {
  sub: string;
  role: string;
  jti?: string;
  exp: number;
}

const SECRET_KEY = process.env.ERP_SECRET_KEY ?? "dev-secret-change-in-production";
const REDIS_URL = process.env.ERP_REDIS_URL ?? "redis://localhost:6379/0";
const REVOKED_TOKEN_PREFIX = "revoked_token:";

const redisClient = createClient({ url: REDIS_URL });
redisClient.on("error", (err) => console.error("[auth] Error de conexión a Redis:", err.message));
let redisReady = false;
redisClient.connect().then(() => {
  redisReady = true;
  console.log("[auth] Conectado a Redis para verificar revocación de tokens");
});

function b64urlDecode(input: string): Buffer {
  const padded = input + "=".repeat((4 - (input.length % 4)) % 4);
  return Buffer.from(padded.replace(/-/g, "+").replace(/_/g, "/"), "base64");
}

async function isTokenRevoked(jti: string | undefined): Promise<boolean> {
  if (!jti) return false; // tokens sin jti (esquema viejo) no se pueden revocar individualmente
  if (!redisReady) {
    // Si Redis no está disponible, se falla CERRADO (se rechaza la
    // conexión) en vez de ABIERTO — un servidor de pizarra que acepte
    // conexiones sin poder verificar revocación es peor que uno que
    // rechace temporalmente mientras Redis se reconecta.
    console.error("[auth] Redis no disponible — rechazando conexión por seguridad (fail-closed)");
    return true;
  }
  const exists = await redisClient.exists(`${REVOKED_TOKEN_PREFIX}${jti}`);
  return exists === 1;
}

export async function verifyErpToken(token: string): Promise<TokenPayload | null> {
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [payloadB64, sigB64] = parts;

  const expectedSig = createHmac("sha256", SECRET_KEY).update(payloadB64).digest();
  const givenSig = b64urlDecode(sigB64);

  if (expectedSig.length !== givenSig.length || !timingSafeEqual(expectedSig, givenSig)) {
    return null;
  }

  try {
    const payload = JSON.parse(b64urlDecode(payloadB64).toString("utf-8")) as TokenPayload;
    if (typeof payload.exp !== "number" || payload.exp < Date.now() / 1000) {
      return null; // token expirado
    }
    if (await isTokenRevoked(payload.jti)) {
      return null; // token revocado (logout) — mismo Redis que consulta el ERP
    }
    return payload;
  } catch {
    return null;
  }
}
