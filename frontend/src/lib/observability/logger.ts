import "server-only";

// Logger estructurado server-only. Una línea JSON por evento, a stdout, que es
// lo que Vercel ya recolecta: no agrega proveedores ni costo.
//
// Hoy un 503 de /api/properties/counts no deja rastro. La ruta hace
// `catch { return 503 }` y el error se pierde entero, así que desde afuera un
// timeout de la base, una credencial vencida y un bug de parseo se ven igual.
// Eso es lo que este módulo existe para terminar.
//
// Dos reglas gobiernan qué se escribe:
//
//   1. Nada de valores de entrada. Los filtros de búsqueda son texto que tipeó
//      una persona -una calle, un barrio, a veces un teléfono- y no tienen por
//      qué quedar en un log. Se registran los NOMBRES de los parámetros y
//      cuántos vinieron, que es lo que sirve para diagnosticar, no su
//      contenido.
//
//   2. Todo lo que se escribe pasa por el redactor. Un mensaje de error de
//      `postgres` incluye la cadena de conexión completa, con usuario y
//      contraseña; un error de fetch puede traer un token en la URL. Confiar
//      en que "ese mensaje no trae nada" es exactamente como terminan las
//      credenciales en un log.

export type Outcome = "ok" | "client_error" | "server_error";

export type LogLevel = "info" | "warn" | "error";

export type LogEvent = {
  level: LogLevel;
  event: string;
  requestId: string;
  route?: string;
  method?: string;
  status?: number;
  outcome?: Outcome;
  durationMs?: number;
  /** Nombres de los parámetros recibidos. Nunca sus valores. */
  paramKeys?: string[];
  paramCount?: number;
  errorName?: string;
  errorMessage?: string;
  /** Cualquier extra ya debe venir libre de datos de la persona usuaria. */
  [key: string]: unknown;
};

const ID_ACEPTABLE = /^[A-Za-z0-9_-]{8,64}$/;

/** Patrones que nunca deben salir en un log, con lo que se los reemplaza. */
const REDACCIONES: ReadonlyArray<readonly [RegExp, string]> = [
  // Cadena de conexión completa: postgres://usuario:clave@host/base
  [/\b[a-z][a-z0-9+.-]*:\/\/[^\s:@/]+:[^\s@/]+@/gi, "[redacted-dsn]@"],
  // JWT
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, "[redacted-jwt]"],
  // Claves con prefijo conocido
  [/\b(sk|pk|rk)-[A-Za-z0-9]{16,}\b/g, "[redacted-key]"],
  // Email. Se excluyen los corchetes a propósito: sin eso, el marcador que
  // deja la regla anterior -"[redacted-dsn]@db.host"- vuelve a parecer un
  // email y la siguiente regla se lo come, dejando un log donde no se entiende
  // qué se redactó.
  [/\b[^\s@[\]]{1,64}@[^\s@[\]]{1,255}\.[a-z]{2,}\b/gi, "[redacted-email]"],
  // Asignaciones tipo password=... / token: "..."
  [/\b(password|passwd|pwd|secret|token|apikey|api_key|authorization)\b\s*[=:]\s*\S+/gi,
   "$1=[redacted]"],
];

/** Deja un texto en condiciones de ser escrito a un log. */
export function redactar(texto: unknown, maxLargo = 500): string {
  if (typeof texto !== "string") return "";
  let salida = texto;
  for (const [patron, reemplazo] of REDACCIONES) {
    salida = salida.replace(patron, reemplazo);
  }
  return salida.slice(0, maxLargo);
}

/**
 * El id con el que se sigue una request de punta a punta.
 *
 * Se acepta el que venga en `x-request-id` sólo si tiene forma inofensiva: es
 * un valor que controla quien llama, así que sin validarlo se puede inyectar
 * un salto de línea y partir una línea de log en dos, que es como se falsifica
 * un registro.
 */
export function requestIdDe(headers: Headers | null | undefined): string {
  const entrante = headers?.get("x-request-id");
  if (entrante && ID_ACEPTABLE.test(entrante)) return entrante;
  return nuevoRequestId();
}

export function nuevoRequestId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

/** A dónde va cada línea. Se puede sustituir en tests. */
let escribir: (linea: string) => void = (linea) => {
  process.stdout.write(linea + "\n");
};

export function _setEscritor(fn: (linea: string) => void): () => void {
  const previo = escribir;
  escribir = fn;
  return () => {
    escribir = previo;
  };
}

const CLAVES_PROPIAS = new Set([
  "level", "event", "requestId", "route", "method", "status", "outcome",
  "durationMs", "paramKeys", "paramCount", "errorName", "errorMessage",
]);

/**
 * Escribe un evento. Los extras se redactan siempre: no se confía en que quien
 * llama ya lo haya hecho.
 */
export function logEvent(evento: LogEvent): void {
  const salida: Record<string, unknown> = {
    ts: new Date().toISOString(),
    level: evento.level,
    event: evento.event,
    requestId: evento.requestId,
  };
  for (const clave of ["route", "method", "outcome"] as const) {
    if (evento[clave] !== undefined) salida[clave] = redactar(evento[clave], 120);
  }
  for (const clave of ["status", "durationMs", "paramCount"] as const) {
    if (typeof evento[clave] === "number") salida[clave] = evento[clave];
  }
  if (evento.paramKeys) salida.paramKeys = evento.paramKeys.slice(0, 40).map((k) => redactar(k, 40));
  if (evento.errorName) salida.errorName = redactar(evento.errorName, 80);
  if (evento.errorMessage) salida.errorMessage = redactar(evento.errorMessage, 300);

  for (const [clave, valor] of Object.entries(evento)) {
    if (CLAVES_PROPIAS.has(clave)) continue;
    salida[clave] = typeof valor === "string" ? redactar(valor, 200)
      : typeof valor === "number" || typeof valor === "boolean" ? valor
      : undefined;
    if (salida[clave] === undefined) delete salida[clave];
  }

  try {
    escribir(JSON.stringify(salida));
  } catch {
    // Un log que rompe la request es peor que no tener log.
  }
}

export function outcomeDe(status: number): Outcome {
  if (status >= 500) return "server_error";
  if (status >= 400) return "client_error";
  return "ok";
}

/** Los nombres de los parámetros, sin sus valores. */
export function clavesDeQuery(url: string): { paramKeys: string[]; paramCount: number } {
  try {
    const sp = new URL(url).searchParams;
    const claves = Array.from(new Set(Array.from(sp.keys()))).sort();
    return { paramKeys: claves, paramCount: Array.from(sp.keys()).length };
  } catch {
    return { paramKeys: [], paramCount: 0 };
  }
}
