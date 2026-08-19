import { describe, expect, it } from "vitest";
import { suggestionMatchRank } from "@/lib/property-db-service";

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
