import { describe, expect, it } from "vitest";
import { _setEscritor } from "@/lib/observability/logger";
import { withObservability } from "@/lib/observability/route";
import { medirEnRequest } from "@/lib/observability/request-timings";

async function correr(handler: Parameters<typeof withObservability>[1], url = "https://x/api/t?q=Palermo&op=venta") {
  const lineas: string[] = [];
  const restaurar = _setEscritor((l) => lineas.push(l));
  try {
    const res = await withObservability("/api/t", handler)(new Request(url));
    return { res, logs: lineas.map((l) => JSON.parse(l) as Record<string, unknown>) };
  } finally {
    restaurar();
  }
}

describe("observabilidad de rutas", () => {
  it("deja una línea por request con ruta, método, estado y duración", async () => {
    const { res, logs } = await correr(() => new Response("{}", { status: 200 }));
    expect(res.status).toBe(200);
    expect(logs).toHaveLength(1);
    expect(logs[0]).toMatchObject({
      event: "http_request",
      route: "/api/t",
      method: "GET",
      status: 200,
      outcome: "ok",
    });
    expect(typeof logs[0].durationMs).toBe("number");
  });

  it("devuelve el request id en la respuesta para que se pueda citar", async () => {
    const { res, logs } = await correr(() => new Response("{}", { status: 200 }));
    const id = res.headers.get("x-request-id");
    expect(id).toBeTruthy();
    expect(logs[0].requestId).toBe(id);
  });

  it("propaga el request id entrante en vez de inventar otro", async () => {
    const lineas: string[] = [];
    const restaurar = _setEscritor((l) => lineas.push(l));
    try {
      const req = new Request("https://x/api/t", { headers: { "x-request-id": "traza-12345" } });
      const res = await withObservability("/api/t", () => new Response("{}"))(req);
      expect(res.headers.get("x-request-id")).toBe("traza-12345");
    } finally {
      restaurar();
    }
  });

  // --- lo que hoy no deja rastro -------------------------------------------

  it("registra el 503 que la ruta ya devolvía en silencio", async () => {
    // `/api/properties/counts` hace `catch { return 503 }`: desde afuera, un
    // timeout de la base y un bug de parseo se ven igual. Ahora el 503 queda
    // registrado como server_error aunque la ruta lo maneje.
    const { res, logs } = await correr(() => new Response("{}", { status: 503 }));
    expect(res.status).toBe(503);
    expect(logs[0]).toMatchObject({ status: 503, outcome: "server_error", level: "error" });
  });

  it("convierte un throw no capturado en 500 con id, y lo registra", async () => {
    const { res, logs } = await correr(() => {
      throw new Error("conexión perdida");
    });
    expect(res.status).toBe(500);
    const cuerpo = (await res.json()) as { error: string; requestId: string };
    expect(cuerpo.requestId).toBe(res.headers.get("x-request-id"));
    expect(logs[0]).toMatchObject({ outcome: "server_error", errorName: "Error" });
    expect(String(logs[0].errorMessage)).toContain("conexión perdida");
  });

  it("un 4xx se registra como error del cliente, no del servidor", async () => {
    const { logs } = await correr(() => new Response("{}", { status: 422 }));
    expect(logs[0]).toMatchObject({ outcome: "client_error", level: "warn" });
  });

  // --- lo que no puede filtrarse ------------------------------------------

  it("no registra los valores de búsqueda, sólo qué filtros vinieron", async () => {
    const { logs } = await correr(() => new Response("{}"));
    expect(logs[0].paramKeys).toEqual(["op", "q"]);
    expect(JSON.stringify(logs[0])).not.toContain("Palermo");
  });

  it("no filtra la cadena de conexión cuando el error la trae", async () => {
    const { res, logs } = await correr(() => {
      throw new Error("connect ETIMEDOUT postgres://eretz_app:Cl4v3@db:5432/postgres");
    });
    const texto = JSON.stringify(logs[0]);
    expect(texto).not.toContain("Cl4v3");
    expect(await res.text()).not.toContain("Cl4v3");
  });

  it("el mensaje que ve el cliente no repite el error interno", async () => {
    const { res } = await correr(() => {
      throw new Error("relation propiedades_backup_2026 does not exist");
    });
    const cuerpo = await res.text();
    expect(cuerpo).not.toContain("propiedades_backup_2026");
  });

  // --- no puede romper la ruta --------------------------------------------

  it("sirve la respuesta aunque los headers sean inmutables", async () => {
    // Es lo que devuelve Next en algunos caminos: un Headers real, con guarda
    // que hace que `set` lance. Se reconstruye la respuesta copiando entradas.
    const inmutable = () => {
      const r = new Response("{}", { status: 200, headers: { "cache-control": "private" } });
      Object.defineProperty(r.headers, "set", {
        value: () => { throw new TypeError("immutable headers"); },
      });
      return r;
    };
    const { res } = await correr(inmutable);
    expect(res.status).toBe(200);
    expect(res.headers.get("x-request-id")).toBeTruthy();
    expect(res.headers.get("cache-control")).toBe("private");
  });
});

describe("sub-tiempos de la request", () => {
  it("surface el tiempo de base en la misma línea, sin agregar otra", async () => {
    // `db_ms` junto a `durationMs` es lo que separa una request lenta por la
    // base de una lenta por otra cosa.
    const { logs } = await correr(async () => {
      await medirEnRequest("db", async () => undefined);
      return new Response("{}", { status: 200 });
    });
    expect(logs).toHaveLength(1);
    expect(typeof logs[0].db_ms).toBe("number");
    expect(logs[0].db_n).toBe(1);
  });

  it("acumula varias consultas de la misma request", async () => {
    const { logs } = await correr(async () => {
      await medirEnRequest("db", async () => undefined);
      await medirEnRequest("db", async () => undefined);
      return new Response("{}", { status: 200 });
    });
    expect(logs[0].db_n).toBe(2);
  });

  it("no agrega campos cuando el handler no midió nada", async () => {
    const { logs } = await correr(() => new Response("{}", { status: 200 }));
    expect(logs[0]).not.toHaveProperty("db_ms");
  });

  it("registra el tiempo aunque el handler falle", async () => {
    // Una consulta lenta que después revienta es la que hay que ver.
    const { logs } = await correr(async () => {
      await medirEnRequest("db", async () => undefined);
      throw new Error("explotó");
    });
    expect(logs[0].status).toBe(500);
    expect(logs[0].db_n).toBe(1);
  });

  it("dos requests concurrentes no se mezclan los tiempos", async () => {
    const lenta = correr(async () => {
      await medirEnRequest("db", async () => {
        await new Promise((r) => setTimeout(r, 20));
      });
      return new Response("{}", { status: 200 });
    });
    const rapida = correr(async () => {
      await medirEnRequest("db", async () => undefined);
      return new Response("{}", { status: 200 });
    });
    const [a, b] = await Promise.all([lenta, rapida]);
    expect(a.logs[0].db_n).toBe(1);
    expect(b.logs[0].db_n).toBe(1);
    expect(a.logs[0].db_ms as number).toBeGreaterThan(b.logs[0].db_ms as number);
  });
});
