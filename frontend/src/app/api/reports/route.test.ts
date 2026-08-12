import { describe, expect, it, vi, beforeEach } from "vitest";
import { POST } from "@/app/api/reports/route";
import * as writer from "@/lib/db-writer";

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
