import { describe, expect, it } from "vitest";
import {
  apiV2AreasFixture,
  apiV2FiltersFixture,
  apiV2NeighborhoodsFixture,
  apiV2SuggestionsFixture,
} from "@/test/api-v2-fixtures";
import { adaptApiV2Area, adaptApiV2Filters, adaptApiV2Neighborhood, adaptApiV2Suggestion } from "./adapters";
import { API_V2_CONTRACT } from "./dto";
import { parseApiV2Areas, parseApiV2Filters, parseApiV2Neighborhoods, parseApiV2Suggestions } from "./schemas";

describe("API v2 discovery contracts", () => {
  it("parses areas with explicit levels and rejects null names item-by-item", () => {
    const parsed = parseApiV2Areas(apiV2AreasFixture);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    expect(parsed.data.data.map(adaptApiV2Area)).toEqual(expect.arrayContaining([
      expect.objectContaining({ level: "MUNICIPIO", name: "La Calera", id: null }),
    ]));
    const withNull = parseApiV2Areas({ ...apiV2AreasFixture, data: [...apiV2AreasFixture.data, { nivel: "SIN_AREA", nombre: null, propiedades: 12 }] });
    expect(withNull.success).toBe(true);
    if (withNull.success) {
      expect(withNull.data.data).toHaveLength(apiV2AreasFixture.data.length);
      expect(withNull.issues).toContainEqual(expect.objectContaining({ path: `$.data[${apiV2AreasFixture.data.length}].nombre` }));
    }
  });

  it("keeps source neighborhoods explicitly non-canonical", () => {
    const parsed = parseApiV2Neighborhoods(apiV2NeighborhoodsFixture);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    expect(parsed.data.data.map(adaptApiV2Neighborhood)[0]).toMatchObject({
      kind: "NEIGHBORHOOD", canonical: false, id: null,
    });
    expect(parseApiV2Neighborhoods({ ...apiV2NeighborhoodsFixture, canonizado: true }).success).toBe(false);
  });

  it("preserves province, department, municipality, locality and neighborhood semantics", () => {
    const parsed = parseApiV2Suggestions(apiV2SuggestionsFixture);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    const suggestions = parsed.data.data.map(adaptApiV2Suggestion);
    expect(suggestions.map((suggestion) => [suggestion.kind, suggestion.level])).toEqual([
      ["AREA", "PROVINCIA"],
      ["AREA", "DEPARTAMENTO"],
      ["AREA", "MUNICIPIO"],
      ["AREA", "LOCALIDAD"],
      ["NEIGHBORHOOD", null],
    ]);
    expect(suggestions[2].context).toEqual({ province: null, department: null, municipality: null, locality: null });
  });

  it("distinguishes a valid empty suggestion response from malformed data", () => {
    expect(parseApiV2Suggestions({ contrato: API_V2_CONTRACT, data: [] })).toMatchObject({ success: true, data: { data: [] } });
    expect(parseApiV2Suggestions({ contrato: API_V2_CONTRACT, data: "wrong" }).success).toBe(false);
  });

  it("keeps valid suggestion items and reports an invalid item", () => {
    const malformed = {
      ...apiV2SuggestionsFixture,
      data: [...apiV2SuggestionsFixture.data, { tipo: "area", nivel: "CIUDAD", nombre: "Inventada", propiedades: 1 }],
    };
    const parsed = parseApiV2Suggestions(malformed);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    expect(parsed.data.data).toHaveLength(apiV2SuggestionsFixture.data.length);
    expect(parsed.issues).toContainEqual(expect.objectContaining({ path: `$.data[${apiV2SuggestionsFixture.data.length}].nivel` }));
  });

  it("parses filter facets, price ranges, zero and missing-data coverage", () => {
    const parsed = parseApiV2Filters(apiV2FiltersFixture);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    expect(adaptApiV2Filters(parsed.data)).toMatchObject({
      operations: [
        { value: "venta", propertyCount: 42536 },
        { value: "alquiler", propertyCount: 4672 },
        { value: "alquiler_temporario", propertyCount: 303 },
      ],
      priceRanges: [
        { currency: "ARS", minimum: 65, maximum: 325909932 },
        { currency: "USD", minimum: 1, maximum: 75000000 },
      ],
      missing: { operation: 10916, propertyType: 5706, price: 5339, locality: 48808, latitude: 15928 },
    });
  });

  it("rejects a structurally incomplete filter envelope", () => {
    expect(parseApiV2Filters({ contrato: API_V2_CONTRACT, filtros: {}, rango_de_precio: [], sin_dato: {} }).success).toBe(false);
  });
});
