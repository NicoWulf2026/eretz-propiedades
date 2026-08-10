import { describe, expect, it } from "vitest";
import { POST } from "@/app/api/claims/route";

function post(body: unknown) {
  return POST(new Request("http://localhost/api/claims", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

describe("POST /api/claims", () => {
  it("rechaza sin email válido o sin nombre", async () => {
    const res = await post({ entidadId: "10", nombre: "A", email: "no-mail" });
    expect(res.status).toBe(422);
  });

  it("rechaza entidadId no numérica", async () => {
    const res = await post({ entidadId: "abc", nombre: "Juan Pérez", email: "j@x.com" });
    expect(res.status).toBe(422);
  });

  it("nunca auto-aprueba: reclamo completo queda 'pending'", async () => {
    const res = await post({ entidadId: "10", nombre: "Juan Pérez", email: "j@x.com", telefono: "111", rol: "Titular" });
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("pending");
  });

  it("sin teléfono ni rol entra como 'needs_review', nunca 'approved'", async () => {
    const res = await post({ entidadId: "10", nombre: "Juan Pérez", email: "j@x.com" });
    const data = await res.json();
    expect(data.status).toBe("needs_review");
    expect(data.status).not.toBe("approved");
  });
});
