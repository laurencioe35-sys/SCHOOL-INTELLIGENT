/**
 * Contexto de autenticación. Llama a POST /auth/login del core-erp-backend
 * de verdad (no un mock) y guarda el token resultante.
 *
 * Nota sobre almacenamiento: se usa sessionStorage (no localStorage) para
 * que el token no sobreviva más allá de la pestaña/sesión del navegador —
 * un balance razonable entre "no pedir login en cada recarga de página"
 * y "no dejar el token indefinidamente en el disco del alumno". Para un
 * despliegue con requisitos de seguridad más estrictos, la alternativa
 * correcta es un cookie httpOnly emitido por el backend, que este SPA no
 * necesitaría leer directamente.
 *
 * No compilado/ejecutado en este entorno (requiere npm install + navegador).
 */
import React, { createContext, useContext, useEffect, useState } from "react";

interface AuthUser {
  userId: string;
  role: "student" | "teacher" | "admin";
  organizationId: string;
  token: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (email: string, password: string, apiBaseUrl: string) => Promise<void>;
  register: (
    fullName: string,
    email: string,
    password: string,
    organizationName: string,
    role: "student" | "teacher",
    apiBaseUrl: string
  ) => Promise<void>;
  logout: (apiBaseUrl: string) => Promise<void>;
  loading: boolean;
  error: string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEY = "erp_auth_session";

function decodeUserIdFromToken(token: string): string {
  const payloadB64 = token.split(".")[0];
  const padded = payloadB64 + "=".repeat((4 - (payloadB64.length % 4)) % 4);
  const json = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const payload = JSON.parse(json) as { sub?: unknown; exp?: unknown };
  if (typeof payload.sub !== "string" || !payload.sub) throw new Error("Token de sesión inválido");
  if (typeof payload.exp === "number" && payload.exp * 1000 <= Date.now()) {
    throw new Error("La sesión expiró. Inicia sesión nuevamente.");
  }
  return payload.sub;
}

function readStoredSession(): AuthUser | null {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    const session = JSON.parse(stored) as Partial<AuthUser>;
    if (
      typeof session.userId !== "string" ||
      typeof session.organizationId !== "string" ||
      typeof session.token !== "string" ||
      !["student", "teacher", "admin"].includes(session.role ?? "")
    ) throw new Error("Sesión almacenada inválida");
    decodeUserIdFromToken(session.token);
    return session as AuthUser;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUser(readStoredSession());
  }, []);

  async function login(email: string, password: string, apiBaseUrl: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Credenciales inválidas");
      }
      const data = await res.json();
      const authUser: AuthUser = {
        userId: decodeUserIdFromToken(data.access_token),
        role: data.role,
        organizationId: data.organization_id,
        token: data.access_token,
      };
      setUser(authUser);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(authUser));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de conexión");
      throw err;
    } finally {
      setLoading(false);
    }
  }

  async function register(
    fullName: string,
    email: string,
    password: string,
    organizationName: string,
    role: "student" | "teacher",
    apiBaseUrl: string
  ) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName, email, password, organization_name: organizationName, role }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "No se pudo registrar");
      }
      const data = await res.json();
      const authUser: AuthUser = {
        userId: decodeUserIdFromToken(data.access_token),
        role: data.role,
        organizationId: data.organization_id,
        token: data.access_token,
      };
      setUser(authUser);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(authUser));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de conexión");
      throw err;
    } finally {
      setLoading(false);
    }
  }

  async function logout(apiBaseUrl: string) {
    // Antes, logout() solo limpiaba el estado local — el token seguía
    // siendo válido en el backend hasta expirar. Ahora avisa al backend
    // para revocarlo de verdad (ver POST /auth/logout).
    if (user) {
      try {
        await fetch(`${apiBaseUrl}/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${user.token}` },
        });
      } catch {
        // Si falla la llamada (ej. sin conexión), igual limpiamos la
        // sesión local — el usuario no debe quedar atrapado sin poder
        // cerrar sesión solo porque el backend no respondió.
      }
    }
    setUser(null);
    sessionStorage.removeItem(STORAGE_KEY);
  }

  return (
    <AuthContext.Provider value={{ user, login, register, logout, loading, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
