import { describe, expect, it } from "vitest";
import { POST } from "@/app/api/reports/route";

function post(body: unknown) {
  return POST(new Request("http://localhost/api/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

describe("POST /api/reports", () => {
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
    const res = await post({ propiedadId: "10", motivo: "no_disponible", detalle: "Ya se vendió" });
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("received");
  });
});
