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
      cursor: "180000:123",
    });
    const serialized = filtersToSearchParams(filters);
    expect(serialized.get("q")).toBe("Palermo");
    expect(serialized.get("pagina")).toBe("3");
    expect(serialized.get("cursor")).toBe("180000:123");
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
});
