import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { insertSignal, isWriterConfigured, persistenceRequired } from "@/lib/db-writer";

// Sin ERETZ_WRITE_DATABASE_URL (preview de sólo lectura), la escritura es un no-op
// seguro: no intenta conectar, no rompe, devuelve persisted=false con reason.
describe("db-writer (fallback sin writer configurado)", () => {
  const originalUrl = process.env.ERETZ_WRITE_DATABASE_URL;
  const originalReq = process.env.ERETZ_PERSISTENCE_REQUIRED;
  const originalVercel = process.env.VERCEL;
  beforeEach(() => { delete process.env.ERETZ_WRITE_DATABASE_URL; });
  afterEach(() => {
    if (originalUrl !== undefined) process.env.ERETZ_WRITE_DATABASE_URL = originalUrl;
    if (originalReq !== undefined) process.env.ERETZ_PERSISTENCE_REQUIRED = originalReq; else delete process.env.ERETZ_PERSISTENCE_REQUIRED;
    if (originalVercel !== undefined) process.env.VERCEL = originalVercel; else delete process.env.VERCEL;
  });

  it("isWriterConfigured() es false sin la variable", () => {
    expect(isWriterConfigured()).toBe(false);
  });

  it("insertSignal sin writer devuelve reason 'no_writer' y no lanza", async () => {
    const res = await insertSignal("perfil_claims", { tipo: "inmobiliaria", entidad_id: 10, nombre: "Test", email: "t@x.com", estado: "pending" });
    expect(res).toEqual({ persisted: false, reason: "no_writer" });
  });

  it("insertSignal para reportes también es no-op seguro", async () => {
    const res = await insertSignal("reportes_publicacion", { propiedad_id: 5, motivo: "otro", estado: "nuevo" });
    expect(res.persisted).toBe(false);
  });

  it("persistenceRequired() se activa por flag explícito", () => {
    process.env.ERETZ_PERSISTENCE_REQUIRED = "1";
    expect(persistenceRequired()).toBe(true);
    delete process.env.ERETZ_PERSISTENCE_REQUIRED;
  });
});
