import { describe, expect, it } from "vitest";
import { parsePropertyFilters, filtersToSearchParams } from "@/lib/property-query";

// Fase I: la URL es la fuente de verdad de la restauración. Un ciclo
// parse -> serialize -> parse debe conservar filtros, orden, modo y zona.
// (scroll, tarjeta seleccionada, modo-fallback y densidad se restauran además
//  desde sessionStorage/localStorage en ExplorerClient.)
describe("restauración por URL (round-trip lossless)", () => {
  it("conserva filtros, orden, modo y viewport", () => {
    const params = {
      operacion: "venta", tipo: "casa", ciudad: "Córdoba", barrio: "Nueva Córdoba",
      moneda: "USD", precio_min: "50000", precio_max: "200000", dormitorios: "2",
      orden: "price_asc", modo: "analysis",
      norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12",
    };
    const first = parsePropertyFilters(params);
    const serialized = filtersToSearchParams(first).toString();
    const restored = parsePropertyFilters(Object.fromEntries(new URLSearchParams(serialized)));

    expect(restored.operation).toBe("venta");
    expect(restored.propertyType).toBe("casa");
    expect(restored.city).toBe("Córdoba");
    expect(restored.neighborhood).toBe("Nueva Córdoba");
    expect(restored.currency).toBe("USD");
    expect(restored.minPrice).toBe(50000);
    expect(restored.maxPrice).toBe(200000);
    expect(restored.minBedrooms).toBe(2);
    expect(restored.sort).toBe("price_asc");
    expect(restored.mode).toBe("analysis");
    expect(restored.viewport).toEqual({ north: 10, east: 20, south: 5, west: 10, zoom: 12 });
  });

  it("una URL vacía restaura los valores por defecto", () => {
    const f = parsePropertyFilters({});
    expect(f.operation).toBe("");
    expect(f.mode).toBe("balanced");
    expect(f.sort).toBe("recent");
    expect(f.viewport).toBeNull();
  });
});
