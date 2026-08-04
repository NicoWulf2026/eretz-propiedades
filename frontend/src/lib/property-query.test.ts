import { describe, expect, it } from "vitest";
import { filtersToSearchParams, parsePropertyFilters } from "@/lib/property-query";

describe("property query", () => {
  it("parses and serializes shareable filters", () => {
    const filters = parsePropertyFilters({
      q: "Palermo",
      operacion: "venta",
      tipo: "departamento",
      moneda: "USD",
      precio_min: "100000",
      orden: "price_asc",
      pagina: "3",
      cursor: "eyJ2ZXJzaW9uIjoxfQ",
    });
    const serialized = filtersToSearchParams(filters);
    expect(serialized.get("q")).toBe("Palermo");
    expect(serialized.get("pagina")).toBe("3");
    expect(serialized.get("cursor")).toBe("eyJ2ZXJzaW9uIjoxfQ");
    expect(parsePropertyFilters(Object.fromEntries(serialized)).sort).toBe("price_asc");
  });

  it("does not allow global mixed-currency price sorting", () => {
    expect(parsePropertyFilters({ orden: "price_desc" }).sort).toBe("recent");
  });

  it("bounds and sanitizes untrusted params", () => {
    const filters = parsePropertyFilters({ q: "foo),estado.eq.inactiva", pagina: "999999" });
    expect(filters.q).not.toMatch(/[(),]/);
    expect(filters.page).toBe(1);
  });

  it("round-trips viewport, map mode and supported data filters", () => {
    const filters = parsePropertyFilters({
      norte: "-34", sur: "-35", este: "-58", oeste: "-59", zoom: "12",
      modo: "map_only", ubicacion: "1", reciente: "30", publicador: "Acme",
    });
    expect(filters.viewport).toEqual({ north: -34, south: -35, east: -58, west: -59, zoom: 12 });
    expect(filters.mode).toBe("map_only");
    expect(filters.hasLocation).toBe(true);
    expect(filtersToSearchParams(filters).get("publicador")).toBe("Acme");
  });
});
