import { describe, expect, it, vi, beforeEach } from "vitest";
import { POST } from "@/app/api/claims/route";
import * as writer from "@/lib/db-writer";
import * as service from "@/lib/property-service";
import { _reiniciarAlmacenPorDefecto } from "@/lib/abuse/rate-limit";

vi.mock("@/lib/db-writer", () => ({
  insertSignal: vi.fn(async () => ({ persisted: false, reason: "no_writer" as const })),
  persistenceRequired: vi.fn(() => false),
}));

vi.mock("@/lib/property-service", () => ({
  realEstateExists: vi.fn(async () => true),
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
  // Cada caso arranca con el freno de abuso en cero: sin esto, el segundo
  // envio identico se deduplica y el caso mide otra cosa.
  _reiniciarAlmacenPorDefecto();
  vi.clearAllMocks();
  vi.mocked(writer.insertSignal).mockResolvedValue({ persisted: false, reason: "no_writer" });
  vi.mocked(writer.persistenceRequired).mockReturnValue(false);
  vi.mocked(service.realEstateExists).mockResolvedValue(true);
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

  // Regresión: la API aceptaba un id numérico cualquiera y lo dejaba en la cola
  // de revisión aunque el perfil no existiera.
  it("rechaza con 404 un perfil inexistente", async () => {
    vi.mocked(service.realEstateExists).mockResolvedValue(false);
    const res = await post({ ...validBody, entidadId: "999999999" });
    expect(res.status).toBe(404);
    expect(writer.insertSignal).not.toHaveBeenCalled();
  });

  // Regresión: un fallo de base no puede leerse como "no existe".
  it("si la base falla devuelve 503, no 404", async () => {
    vi.mocked(service.realEstateExists).mockRejectedValue(new Error("db down"));
    const res = await post(validBody);
    expect(res.status).toBe(503);
    expect(writer.insertSignal).not.toHaveBeenCalled();
  });

  // Regresión: un tipo desconocido se guardaba silenciosamente como inmobiliaria.
  it("rechaza un tipo desconocido en vez de asumir inmobiliaria", async () => {
    const res = await post({ ...validBody, tipo: "cualquier-cosa" });
    expect(res.status).toBe(422);
    expect(writer.insertSignal).not.toHaveBeenCalled();
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