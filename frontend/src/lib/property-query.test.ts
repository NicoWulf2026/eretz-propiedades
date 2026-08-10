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

  it("parsea, deduplica y limita multi-ubicación; ida y vuelta por URL", () => {
    const filters = parsePropertyFilters({ ubicaciones: "Palermo, Belgrano ,palermo" });
    expect(filters.locations).toEqual(["Palermo", "Belgrano"]); // dedup case-insensitive
    const round = parsePropertyFilters(Object.fromEntries(filtersToSearchParams(filters)));
    expect(round.locations).toEqual(["Palermo", "Belgrano"]);
  });

  it("sin filtros no produce near, priceMode ni mortgageState", () => {
    const f = parsePropertyFilters({});
    expect(f.near).toBeNull();
    expect(f.priceMode).toBe("");
    expect(f.mortgageState).toBe("");
    expect(f.locations).toEqual([]);
  });

  it("precio y crédito aceptan valores nuevos y compatibilidad con '1'", () => {
    expect(parsePropertyFilters({ precio: "consult" }).priceMode).toBe("consult");
    expect(parsePropertyFilters({ precio: "1" }).priceMode).toBe("with"); // legado
    expect(parsePropertyFilters({ credito: "sininfo" }).mortgageState).toBe("sininfo");
    expect(parsePropertyFilters({ credito: "1" }).mortgageState).toBe("si"); // legado
  });

  it("orden 'nearest' sólo sobrevive con un punto de referencia válido", () => {
    expect(parsePropertyFilters({ orden: "nearest" }).sort).toBe("recent"); // sin punto
    const near = parsePropertyFilters({ orden: "nearest", cerca_lat: "-34.6", cerca_lng: "-58.4" });
    expect(near.sort).toBe("nearest");
    expect(near.near).toEqual({ lat: -34.6, lng: -58.4 });
    expect(filtersToSearchParams(near).get("cerca_lat")).toBe("-34.6");
  });
});
