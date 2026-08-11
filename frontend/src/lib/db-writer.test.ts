import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { insertSignal, isWriterConfigured } from "@/lib/db-writer";

// Sin ERETZ_WRITE_DATABASE_URL (preview de sólo lectura), la escritura es un no-op
// seguro: no intenta conectar, no rompe, devuelve persisted=false.
describe("db-writer (fallback sin writer configurado)", () => {
  const original = process.env.ERETZ_WRITE_DATABASE_URL;
  beforeEach(() => { delete process.env.ERETZ_WRITE_DATABASE_URL; });
  afterEach(() => { if (original !== undefined) process.env.ERETZ_WRITE_DATABASE_URL = original; });

  it("isWriterConfigured() es false sin la variable", () => {
    expect(isWriterConfigured()).toBe(false);
  });

  it("insertSignal devuelve persisted:false y no lanza", async () => {
    const res = await insertSignal("perfil_claims", { tipo: "inmobiliaria", entidad_id: 10, nombre: "Test", email: "t@x.com", estado: "pending" });
    expect(res).toEqual({ persisted: false });
  });

  it("insertSignal para reportes también es no-op seguro", async () => {
    const res = await insertSignal("reportes_publicacion", { propiedad_id: 5, motivo: "otro", estado: "nuevo" });
    expect(res).toEqual({ persisted: false });
  });
});
