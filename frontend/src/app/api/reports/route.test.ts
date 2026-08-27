import { describe, expect, it, vi, beforeEach } from "vitest";
import { POST } from "@/app/api/reports/route";
import * as writer from "@/lib/db-writer";
import { _reiniciarAlmacenPorDefecto } from "@/lib/abuse/rate-limit";

vi.mock("@/lib/db-writer", () => ({
  insertSignal: vi.fn(async () => ({ persisted: false, reason: "no_writer" as const })),
  persistenceRequired: vi.fn(() => false),
}));

function post(body: unknown) {
  return POST(new Request("http://localhost/api/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

const validBody = { propiedadId: "10", motivo: "no_disponible", detalle: "Ya se vendió" };

beforeEach(() => {
  // Cada caso arranca con el freno de abuso en cero: sin esto, el segundo
  // envio identico se deduplica y el caso mide otra cosa.
  _reiniciarAlmacenPorDefecto();
  // Los contadores de llamadas se arrastraban entre casos, así que "se
  // persistió una sola vez" medía el acumulado de todo el archivo.
  vi.clearAllMocks();
  vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "no_writer" });
  vi.mocked(writer.persistenceRequired).mockReturnValue(false);
});

describe("POST /api/reports — validación", () => {
  it("rechaza motivo inválido", async () => {
    expect((await post({ propiedadId: "10", motivo: "spam" })).status).toBe(422);
  });
  it("rechaza propiedad no numérica", async () => {
    expect((await post({ propiedadId: "x", motivo: "duplicada" })).status).toBe(422);
  });
  it("rechaza email inválido cuando se envía", async () => {
    expect((await post({ propiedadId: "10", motivo: "otro", email: "no-mail" })).status).toBe(422);
  });
  it("acepta un reporte válido (señal, no auto-modifica)", async () => {
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("received");
  });
});

describe("POST /api/reports — persistencia (no éxito falso)", () => {
  it("A. writer configurado + insert OK → 200 persisted:true", async () => {
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect((await res.json()).persisted).toBe(true);
  });
  it("B. writer ausente en entorno real → 503 persistence_unavailable", async () => {
    vi.mocked(writer.persistenceRequired).mockReturnValue(true);
    const res = await post(validBody);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toBe("persistence_unavailable");
  });
  it("C. el writer falla en entorno real → 503", async () => {
    vi.mocked(writer.persistenceRequired).mockReturnValue(true);
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "error" });
    expect((await post(validBody)).status).toBe(503);
  });
});
describe("POST /api/reports — freno de abuso", () => {
  it("deduplica el mismo reporte repetido sin decir que no se le dio curso", async () => {
    // Un doble clic o un reintento no debe abrir dos expedientes. Y la
    // respuesta sigue siendo "received": decirle "duplicado" a alguien que
    // reporta un problema real suena a que no se lo tomó en cuenta.
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    const primero = await post(validBody);
    const segundo = await post(validBody);
    expect(primero.status).toBe(200);
    expect(segundo.status).toBe(200);
    expect((await segundo.json())).toMatchObject({ status: "received", deduplicated: true });
    // y no se persistió dos veces
    expect(vi.mocked(writer.insertSignal)).toHaveBeenCalledTimes(1);
  });

  it("un reporte distinto sobre la misma propiedad sí pasa", async () => {
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    await post(validBody);
    const otro = await post({ ...validBody, motivo: "precio_incorrecto" });
    expect((await otro.json()).deduplicated).toBeUndefined();
    expect(vi.mocked(writer.insertSignal)).toHaveBeenCalledTimes(2);
  });

  it("corta con 429 y Retry-After tras varios envíos seguidos", async () => {
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    let ultima: Response | null = null;
    for (let i = 0; i < 8; i += 1) {
      ultima = await post({ ...validBody, detalle: `detalle distinto ${i}` });
    }
    expect(ultima?.status).toBe(429);
    expect(Number(ultima?.headers.get("Retry-After"))).toBeGreaterThan(0);
  });

  it("el 429 no revela cuál es el límite", async () => {
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    let ultima: Response | null = null;
    for (let i = 0; i < 8; i += 1) ultima = await post({ ...validBody, detalle: `d${i}` });
    const cuerpo = JSON.stringify(await ultima!.json());
    expect(cuerpo).not.toMatch(/\b[0-9]+\s*(por|per|\/)\s*(min|hora|hour)/i);
    expect(cuerpo).not.toContain("límite");
  });

  it("un cuerpo inválido no consume cuota", async () => {
    // Si un 422 gastara cuota, bastaría con mandar basura para dejar sin
    // servicio a quien reporta de verdad desde la misma red.
    for (let i = 0; i < 10; i += 1) await post({ propiedadId: "x", motivo: "spam" });
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    expect((await post(validBody)).status).toBe(200);
  });
});
