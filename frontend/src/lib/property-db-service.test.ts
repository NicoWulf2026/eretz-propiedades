import { afterEach, describe, expect, it } from "vitest";
import { getPropertiesByIds, getPropertyByIdResult, suggestionMatchRank } from "@/lib/property-db-service";

const originalSupabaseDatabaseUrl = process.env.SUPABASE_DATABASE_URL;
const originalDatabaseUrl = process.env.DATABASE_URL;
const originalQualityGate = process.env.ERETZ_PREVIEW_QUALITY_GATE;

afterEach(() => {
  if (originalSupabaseDatabaseUrl === undefined) delete process.env.SUPABASE_DATABASE_URL;
  else process.env.SUPABASE_DATABASE_URL = originalSupabaseDatabaseUrl;
  if (originalDatabaseUrl === undefined) delete process.env.DATABASE_URL;
  else process.env.DATABASE_URL = originalDatabaseUrl;
  if (originalQualityGate === undefined) delete process.env.ERETZ_PREVIEW_QUALITY_GATE;
  else process.env.ERETZ_PREVIEW_QUALITY_GATE = originalQualityGate;
});

describe("suggestionMatchRank", () => {
  it("rechaza campos de una fila que no coinciden con la consulta", () => {
    expect(suggestionMatchRank("Palermo", "Argentina")).toBeNull();
    expect(suggestionMatchRank("Palermo", "Araoz Palermo 2000")).toBe(2);
  });

  it("prioriza coincidencia exacta y luego prefijo, sin depender de acentos", () => {
    expect(suggestionMatchRank("nuñez", "Núñez")).toBe(0);
    expect(suggestionMatchRank("coldwell", "Coldwell Banker Destino")).toBe(1);
  });
});

describe("getPropertyByIdResult", () => {
  it("treats malformed public ids as not found without requiring infrastructure", async () => {
    delete process.env.SUPABASE_DATABASE_URL;
    delete process.env.DATABASE_URL;
    await expect(getPropertyByIdResult("not-a-property-id")).resolves.toEqual({ status: "NOT_FOUND" });
  });

  it("does not turn missing database configuration into a 404", async () => {
    delete process.env.SUPABASE_DATABASE_URL;
    delete process.env.DATABASE_URL;
    await expect(getPropertyByIdResult("987654321")).resolves.toEqual({
      status: "UNAVAILABLE",
      reason: "DATABASE_UNCONFIGURED",
    });
  });

  it("does not turn a disabled public quality gate into a 404", async () => {
    process.env.SUPABASE_DATABASE_URL = "postgres://unused.example/test";
    delete process.env.DATABASE_URL;
    delete process.env.ERETZ_PREVIEW_QUALITY_GATE;
    await expect(getPropertyByIdResult("987654322")).resolves.toEqual({
      status: "UNAVAILABLE",
      reason: "QUALITY_GATE_UNAVAILABLE",
    });
  });
});

describe("getPropertiesByIds", () => {
  it("keeps an empty valid request distinct from unavailable infrastructure", async () => {
    delete process.env.SUPABASE_DATABASE_URL;
    delete process.env.DATABASE_URL;
    await expect(getPropertiesByIds(["invalid"])).resolves.toEqual({ properties: [], failed: false });
  });

  it("does not report an infrastructure outage as an empty saved list", async () => {
    delete process.env.SUPABASE_DATABASE_URL;
    delete process.env.DATABASE_URL;
    await expect(getPropertiesByIds(["987654323"])).resolves.toEqual({ properties: [], failed: true });
  });
});
