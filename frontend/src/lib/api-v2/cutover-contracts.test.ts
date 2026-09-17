import { describe, expect, it } from "vitest";
import { API_V2_CONTRACT } from "./dto";
import { parseApiV2Agency, parseApiV2Batch, parseApiV2Map, parseApiV2Property } from "./schemas";
import { catalogPropertyToSummary, propertyFiltersToCatalogQuery, unsupportedExplorerFilters, validateApiV2ExplorerParams } from "./property-boundary";
import { adaptApiV2Property } from "./adapters";
import { apiV2FixtureMatrix } from "@/test/api-v2-fixtures";
import { parsePropertyFilters } from "@/lib/property-query";

describe("final API v2 cutover contracts", () => {
  it("accepts null technical ranking on detail and batch properties", () => {
    const parsed = parseApiV2Property({ ...apiV2FixtureMatrix.complete, ranking: null });
    expect(parsed.success).toBe(true);
  });
  it("validates viewport totals, truncation and non-null coordinates", () => {
    const parsed = parseApiV2Map({
      contrato: API_V2_CONTRACT, total_matches: 100, viewport_matches: 3,
      returned_points: 2, truncated: true, limit: 2,
      data: [{ id: "a", latitud: -34.6, longitud: -58.4, precio: 0, moneda: null, operacion: null, tipo_propiedad: null, titulo: null }],
    });
    expect(parsed).toMatchObject({ success: true, data: { truncated: true, data: [{ precio: 0 }] } });
    expect(parseApiV2Map({ contrato: API_V2_CONTRACT, total_matches: 1, viewport_matches: 1, returned_points: 1, truncated: false, limit: 2, data: [{ id: "a", latitud: null, longitud: -58 }] })).toMatchObject({ success: true, data: { data: [] } });
  });

  it("formalizes unavailable contact without inventing channels", () => {
    expect(parseApiV2Agency({ contrato: API_V2_CONTRACT, data: { agency_id: "roomix:a", name: "A", logo: null, website: null, contact: { status: "UNAVAILABLE", phone: null, whatsapp: null, email: null } } })).toMatchObject({ success: true, data: { data: { contact: { status: "UNAVAILABLE", phone: null } } } });
  });

  it("keeps batch items and missing identifiers separate", () => {
    const parsed = parseApiV2Batch({ contrato: API_V2_CONTRACT, items: [apiV2FixtureMatrix.complete], missing_ids: ["gone"], requested_ids: [apiV2FixtureMatrix.complete.id, "gone"] });
    expect(parsed).toMatchObject({ success: true, data: { items: [{ id: apiV2FixtureMatrix.complete.id }], missing_ids: ["gone"] } });
  });

  it("maps nulls and real zeroes without conflating municipality and locality", () => {
    const catalog = adaptApiV2Property(apiV2FixtureMatrix.municipalityWithoutLocality);
    const summary = catalogPropertyToSummary({ ...catalog, price: { amount: 0, currency: null, rawCurrency: null }, bedrooms: 0 });
    expect(summary).toMatchObject({ price: 0, currency: null, bedrooms: 0, city: null, municipality: "La Calera" });
  });

  it("converts the supported combined filters and refuses unsupported combinations", () => {
    const filters = parsePropertyFilters({ q: "casa", operacion: "venta", tipo: "casa", moneda: "USD", precio_min: "1", dormitorios: "2", superficie: "40", area_nivel: "MUNICIPIO", area_nombre: "La Calera" });
    expect(propertyFiltersToCatalogQuery(filters)).toMatchObject({ text: "casa", operation: "venta", propertyType: "casa", currency: "USD", minPrice: 1, bedrooms: 2, minSurface: 40, area: { level: "MUNICIPIO", name: "La Calera" } });
    expect(unsupportedExplorerFilters(filters)).toEqual([]);
    expect(unsupportedExplorerFilters(parsePropertyFilters({ cocheras: "1" }))).toContain("cocheras");
  });

  it("rejects invalid manual enums before any network request", () => {
    expect(validateApiV2ExplorerParams(new URLSearchParams("orden=recent"))).toContain("orden");
    expect(validateApiV2ExplorerParams(new URLSearchParams("tipo=otro"))).toContain("tipo");
    expect(validateApiV2ExplorerParams(new URLSearchParams("orden=price_asc"))).toContain("requieren moneda");
    expect(validateApiV2ExplorerParams(new URLSearchParams("q=casa&q=depto"))).toContain("no puede repetirse");
    expect(validateApiV2ExplorerParams(new URLSearchParams("precio_min=-1&moneda=USD"))).toContain("precio_min");
    expect(validateApiV2ExplorerParams(new URLSearchParams("operacion=venta&tipo=casa&orden=relevance"))).toBeNull();
  });
});
