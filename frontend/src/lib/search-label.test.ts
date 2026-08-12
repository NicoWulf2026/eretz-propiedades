import { describe, expect, it } from "vitest";
import { describeSearch } from "@/lib/search-label";
import { parsePropertyFilters } from "@/lib/property-query";

describe("describeSearch", () => {
  it("vacío cuando no hay filtros significativos", () => {
    expect(describeSearch(parsePropertyFilters({}))).toBe("");
  });

  it("combina operación, tipo y lugar", () => {
    const label = describeSearch(parsePropertyFilters({ operacion: "venta", tipo: "casa", ciudad: "Córdoba" }));
    expect(label).toContain("en Córdoba");
    expect(label).toContain("·");
  });

  it("incluye la palabra clave", () => {
    expect(describeSearch(parsePropertyFilters({ q: "jardín" }))).toContain("jardín");
  });

  it("describe un rango de precio con moneda", () => {
    const label = describeSearch(parsePropertyFilters({ moneda: "USD", precio_min: "100000", precio_max: "200000" }));
    expect(label).toContain("USD");
    expect(label).toMatch(/–/);
  });
});
