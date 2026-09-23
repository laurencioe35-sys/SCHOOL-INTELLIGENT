/**
 * Genera un token válido con el MISMO esquema que core-erp-backend/api/auth.py,
 * solo para poder probar la autenticación del servidor CRDT sin tener que
 * levantar el backend Python completo en cada prueba. En un entorno real,
 * el token siempre lo emite el ERP (login real), esto es únicamente un
 * helper de testing.
 */
import { createHmac } from "crypto";

const SECRET_KEY = process.env.ERP_SECRET_KEY ?? "dev-secret-change-in-production";

function b64url(buf) {
  return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function generateTestToken(userId, role, ttlSeconds = 3600) {
  const payload = {
    sub: userId,
    role,
    jti: `test-jti-${Math.random().toString(36).slice(2)}`,
    exp: Math.floor(Date.now() / 1000) + ttlSeconds,
  };
  const payloadB64 = b64url(Buffer.from(JSON.stringify(payload)));
  const signature = createHmac("sha256", SECRET_KEY).update(payloadB64).digest();
  return `${payloadB64}.${b64url(signature)}`;
}

export function generateExpiredTestToken(userId, role) {
  return generateTestToken(userId, role, -3600); // ya expiró hace 1 hora
}

export function extractJti(token) {
  const payloadB64 = token.split(".")[0];
  const padded = payloadB64 + "=".repeat((4 - (payloadB64.length % 4)) % 4);
  const json = Buffer.from(padded, "base64").toString("utf-8");
  return JSON.parse(json).jti;
}
