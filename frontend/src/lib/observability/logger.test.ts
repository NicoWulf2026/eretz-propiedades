import { describe, expect, it } from "vitest";
import {
  _setEscritor,
  clavesDeQuery,
  logEvent,
  outcomeDe,
  redactar,
  requestIdDe,
} from "@/lib/observability/logger";

function capturar(fn: () => void): Record<string, unknown>[] {
  const lineas: string[] = [];
  const restaurar = _setEscritor((l) => lineas.push(l));
  try {
    fn();
  } finally {
    restaurar();
  }
  return lineas.map((l) => JSON.parse(l) as Record<string, unknown>);
}

describe("logger estructurado", () => {
  it("escribe una línea JSON por evento", () => {
    const [e] = capturar(() =>
      logEvent({ level: "info", event: "request", requestId: "abc12345", status: 200 }),
    );
    expect(e.event).toBe("request");
    expect(e.requestId).toBe("abc12345");
    expect(e.status).toBe(200);
    expect(typeof e.ts).toBe("string");
  });

  // --- lo que nunca puede salir en un log ---------------------------------

  it("no deja pasar la cadena de conexión de la base", () => {
    // Es el caso real: cualquier error de `postgres` trae el DSN completo, con
    // usuario y contraseña, dentro del mensaje.
    const [e] = capturar(() =>
      logEvent({
        level: "error",
        event: "request",
        requestId: "r1",
        errorMessage: 'connect ECONNREFUSED postgres://eretz_app:Sup3rS3cret@db.host:5432/postgres',
      }),
    );
    expect(e.errorMessage).not.toContain("Sup3rS3cret");
    expect(e.errorMessage).not.toContain("eretz_app:");
    expect(String(e.errorMessage)).toContain("[redacted-dsn]");
  });

  it("no deja pasar un JWT", () => {
    const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r";
    expect(redactar(`Authorization: Bearer ${jwt}`)).not.toContain(jwt);
    expect(redactar(jwt)).toBe("[redacted-jwt]");
  });

  it("no deja pasar un email", () => {
    expect(redactar("reporte de vecino@ejemplo.com.ar")).toBe(
      "reporte de [redacted-email]",
    );
  });

  it("no deja pasar asignaciones de secretos", () => {
    expect(redactar("password=hunter2 token: abc123")).not.toContain("hunter2");
    expect(redactar("api_key=AKIA1234567890")).not.toContain("AKIA1234567890");
  });

  it("redacta también los campos extra, sin confiar en quien llama", () => {
    const [e] = capturar(() =>
      logEvent({ level: "info", event: "x", requestId: "r1", nota: "avisar a juan@casa.com" }),
    );
    expect(String(e.nota)).toBe("avisar a [redacted-email]");
  });

  // --- valores de entrada --------------------------------------------------

  it("registra los nombres de los parámetros y no sus valores", () => {
    // El texto de búsqueda lo tipea una persona: puede traer una calle, un
    // barrio o un teléfono. Sirve saber QUE filtro se uso, no con que.
    const r = clavesDeQuery("https://x/api?q=Palermo%203%20amb&operacion=venta&q=otra");
    expect(r.paramKeys).toEqual(["operacion", "q"]);
    expect(r.paramCount).toBe(3);
    expect(JSON.stringify(r)).not.toContain("Palermo");
  });

  it("no rompe con una url invalida", () => {
    expect(clavesDeQuery("no-es-una-url")).toEqual({ paramKeys: [], paramCount: 0 });
  });

  // --- request id ----------------------------------------------------------

  it("acepta el id entrante cuando tiene forma inofensiva", () => {
    const h = new Headers({ "x-request-id": "req-abc123XYZ" });
    expect(requestIdDe(h)).toBe("req-abc123XYZ");
  });

  it("descarta un id entrante con caracteres que ensucian la linea de log", () => {
    // Un salto de linea seria lo peor -parte la linea JSON en dos y deja
    // inyectar un registro falso- pero `Headers` ya lo rechaza al construirse.
    // Lo que SI llega son comillas y espacios, y un id no tiene por que
    // traerlos: se descarta y se genera uno propio.
    const h = new Headers({ "x-request-id": 'a"} {"level":"info"' });
    const id = requestIdDe(h);
    expect(id).not.toContain('"');
    expect(id).not.toContain(" ");
  });

  it("descarta un id entrante demasiado corto o largo", () => {
    expect(requestIdDe(new Headers({ "x-request-id": "abc" }))).not.toBe("abc");
    const largo = "a".repeat(200);
    expect(requestIdDe(new Headers({ "x-request-id": largo }))).not.toBe(largo);
  });

  it("genera uno cuando no viene ninguno", () => {
    const a = requestIdDe(new Headers());
    const b = requestIdDe(null);
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThanOrEqual(8);
  });

  // --- clasificacion -------------------------------------------------------

  it("distingue error del cliente de error del servidor", () => {
    expect(outcomeDe(200)).toBe("ok");
    expect(outcomeDe(304)).toBe("ok");
    expect(outcomeDe(422)).toBe("client_error");
    expect(outcomeDe(503)).toBe("server_error");
  });

  it("un fallo al escribir el log no puede romper la request", () => {
    const restaurar = _setEscritor(() => {
      throw new Error("stdout cerrado");
    });
    try {
      expect(() => logEvent({ level: "info", event: "x", requestId: "r1" })).not.toThrow();
    } finally {
      restaurar();
    }
  });
});
