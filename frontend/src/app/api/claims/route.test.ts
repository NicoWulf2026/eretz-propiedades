import { describe, expect, it, vi, beforeEach } from "vitest";
import { POST } from "@/app/api/claims/route";
import * as writer from "@/lib/db-writer";

vi.mock("@/lib/db-writer", () => ({
  insertSignal: vi.fn(async () => ({ persisted: false, reason: "no_writer" as const })),
  persistenceRequired: vi.fn(() => false),
}));

function post(body: unknown) {
  return POST(new Request("http://localhost/api/claims", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

const validBody = { entidadId: "10", nombre: "Juan Pérez", email: "j@x.com", telefono: "111", rol: "Titular" };

beforeEach(() => {
  vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "no_writer" });
  vi.mocked(writer.persistenceRequired).mockReturnValue(false);
});

describe("POST /api/claims — validación", () => {
  it("rechaza sin email válido o sin nombre", async () => {
    expect((await post({ entidadId: "10", nombre: "A", email: "no-mail" })).status).toBe(422);
  });
  it("rechaza entidadId no numérica", async () => {
    expect((await post({ entidadId: "abc", nombre: "Juan Pérez", email: "j@x.com" })).status).toBe(422);
  });
  it("nunca auto-aprueba: reclamo completo queda 'pending'", async () => {
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("pending");
  });
  it("sin teléfono ni rol entra como 'needs_review', nunca 'approved'", async () => {
    const data = await (await post({ entidadId: "10", nombre: "Juan Pérez", email: "j@x.com" })).json();
    expect(data.status).toBe("needs_review");
    expect(data.status).not.toBe("approved");
  });
});

describe("POST /api/claims — persistencia (no éxito falso)", () => {
  it("A. writer configurado + insert OK → 200 persisted:true", async () => {
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: true });
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect((await res.json()).persisted).toBe(true);
  });

  it("B. writer ausente en entorno real → 503 persistence_unavailable", async () => {
    vi.mocked(writer.persistenceRequired).mockReturnValue(true);
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "no_writer" });
    const res = await post(validBody);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toBe("persistence_unavailable");
  });

  it("C. el writer falla en entorno real → 503 (nunca éxito falso)", async () => {
    vi.mocked(writer.persistenceRequired).mockReturnValue(true);
    vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "error" });
    const res = await post(validBody);
    expect(res.status).toBe(503);
  });

  it("dev/test sin writer (persistencia no obligatoria) → 200 acuse", async () => {
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect((await res.json()).persisted).toBe(false);
  });
});
