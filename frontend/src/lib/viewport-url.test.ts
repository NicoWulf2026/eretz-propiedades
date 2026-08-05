import { describe, expect, it } from "vitest";
import { parsePropertyFilters, filtersToSearchParams } from "@/lib/property-query";

// Fase F: contrato de la zona del mapa en la URL (aplicar / conservar filtros / quitar).
describe("viewport en la URL", () => {
  it("parsea y re-serializa la zona del mapa conservando el resto de filtros", () => {
    const f = parsePropertyFilters({ norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12", ciudad: "Córdoba" });
    expect(f.viewport).toEqual({ north: 10, east: 20, south: 5, west: 10, zoom: 12 });
    const s = filtersToSearchParams(f).toString();
    expect(s).toContain("norte=10");
    expect(s).toContain("este=20");
    expect(s).toContain("ciudad=C%C3%B3rdoba");
  });

  it("descarta zonas inválidas (norte <= sur)", () => {
    expect(parsePropertyFilters({ norte: "5", este: "20", sur: "10", oeste: "10", zoom: "12" }).viewport).toBeNull();
  });

  it("quitar viewport conserva los filtros y elimina la zona de la URL", () => {
    const f = parsePropertyFilters({ norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12", ciudad: "Córdoba" });
    const cleared = { ...f, viewport: null, cursor: "", page: 1, direction: "next" as const };
    const s = filtersToSearchParams(cleared).toString();
    expect(s).not.toContain("norte");
    expect(s).not.toContain("oeste");
    expect(s).toContain("ciudad=C%C3%B3rdoba");
  });
});
