import { describe, expect, it } from "vitest";
import { hasCatalogMapCoordinates } from "@/domain/catalog-property";
import { catalogPaginationToOffset, type CatalogSearchQuery } from "@/domain/catalog-search";
import { apiV2FixtureMatrix, expectedZeroDomain, invalidMissingAgencyDto } from "@/test/api-v2-fixtures";
import { adaptApiV2Page, adaptApiV2Property, toApiV2SearchRequest } from "./adapters";
import { API_V2_CONTRACT, API_V2_RANKING, type ApiV2SearchPageDto } from "./dto";
import { parseApiV2Page, parseApiV2Property } from "./schemas";

const baseQuery: CatalogSearchQuery = {
  text: "casa",
  operation: null,
  propertyType: null,
  area: null,
  locality: null,
  neighborhood: null,
  agencyId: null,
  minPrice: null,
  maxPrice: null,
  currency: null,
  rooms: null,
  bedrooms: null,
  bathrooms: null,
  minSurface: null,
  maxSurface: null,
  sort: { kind: "technical_relevance" },
  pagination: { page: 3, pageSize: 24 },
};

describe("API v2 DTO validation and adapters", () => {
  it("accepts every valid contract fixture", () => {
    for (const fixture of Object.values(apiV2FixtureMatrix)) {
      expect(parseApiV2Property(fixture)).toMatchObject({ success: true });
    }
  });

  it("preserves null, empty string, and real zero as different values", () => {
    const zero = adaptApiV2Property(apiV2FixtureMatrix.zeroBedrooms);
    const zeroSurface = adaptApiV2Property(apiV2FixtureMatrix.zeroSurface);
    const missing = adaptApiV2Property(apiV2FixtureMatrix.partial);
    const empty = adaptApiV2Property(apiV2FixtureMatrix.emptyDescription);
    expect({ price: adaptApiV2Property(apiV2FixtureMatrix.zeroPrice).price, rooms: zero.rooms, bedrooms: zero.bedrooms, surfaces: zeroSurface.surfaces }).toEqual(expectedZeroDomain);
    expect(missing.price.amount).toBeNull();
    expect(missing.bedrooms).toBeNull();
    expect(missing.surfaces.total).toBeNull();
    expect(empty.description).toBe("");
  });

  it("never turns a municipality into a locality", () => {
    const property = adaptApiV2Property(apiV2FixtureMatrix.municipalityWithoutLocality);
    expect(property.geography.locality.name).toBeNull();
    expect(property.geography.municipality.name).toBe("La Calera");
    expect(property.geography.searchArea).toMatchObject({ level: "MUNICIPIO", name: "La Calera" });
  });

  it.each([
    ["locality", "LOCALIDAD"],
    ["municipalityWithoutLocality", "MUNICIPIO"],
    ["department", "DEPARTAMENTO"],
    ["province", "PROVINCIA"],
    ["withoutLocation", "SIN_AREA"],
  ] as const)("preserves the %s area level", (key, level) => {
    expect(adaptApiV2Property(apiV2FixtureMatrix[key]).geography.searchArea.level).toBe(level);
  });

  it("keeps missing coordinates out of map data without inventing 0,0", () => {
    const missing = adaptApiV2Property(apiV2FixtureMatrix.withoutCoordinates);
    expect(missing.latitude).toBeNull();
    expect(missing.longitude).toBeNull();
    expect(hasCatalogMapCoordinates(missing)).toBe(false);
    expect(hasCatalogMapCoordinates(adaptApiV2Property(apiV2FixtureMatrix.withCoordinates))).toBe(true);
  });

  it("preserves technical ranking and its explanation", () => {
    expect(adaptApiV2Property(apiV2FixtureMatrix.ranked).technicalRanking).toEqual({
      version: API_V2_RANKING,
      total: 78.5,
      parts: { match: 50, location: 12, completeness: 12.5, images: 4 },
    });
  });

  it("rejects a missing agency id instead of inventing agency data", () => {
    const result = parseApiV2Property(invalidMissingAgencyDto);
    expect(result.success).toBe(false);
    if (!result.success) expect(result.issues).toContainEqual(expect.objectContaining({ path: "$.agency_id" }));
  });

  it("adapts page numbers to API offsets and back", () => {
    expect(catalogPaginationToOffset({ page: 3, pageSize: 24 })).toEqual({ limit: 24, offset: 48 });
    const dto = {
      contrato: API_V2_CONTRACT,
      ranking: API_V2_RANKING,
      consulta: "casa",
      total: 50,
      limit: 24,
      offset: 48,
      data: [apiV2FixtureMatrix.ranked],
    } satisfies ApiV2SearchPageDto;
    expect(adaptApiV2Page(dto)).toMatchObject({ page: 3, pageSize: 24, hasPrevious: true, hasNext: true, rankingVersion: API_V2_RANKING });
  });

  it("uses backend technical ranking by default and refuses unsupported user sort", () => {
    const request = toApiV2SearchRequest(baseQuery);
    expect(request.supported).toBe(true);
    if (request.supported) {
      expect(request.path).toBe("/v2/buscar");
      expect(request.params.get("offset")).toBe("48");
    }
    expect(toApiV2SearchRequest({ ...baseQuery, sort: { kind: "user_selected", value: "price_asc" } })).toMatchObject({ supported: false });
  });

  it("refuses filters that /v2/buscar does not actually accept", () => {
    expect(toApiV2SearchRequest({ ...baseQuery, area: { level: "MUNICIPIO", name: "La Calera" } })).toMatchObject({ supported: false });
    expect(toApiV2SearchRequest({ ...baseQuery, minSurface: 40 })).toMatchObject({ supported: false });
  });

  it("reports malformed list items as partial data instead of an empty success", () => {
    const response = {
      contrato: API_V2_CONTRACT,
      ranking: API_V2_RANKING,
      consulta: null,
      total: 2,
      limit: 24,
      offset: 0,
      data: [apiV2FixtureMatrix.ranked, invalidMissingAgencyDto],
    };
    const parsed = parseApiV2Page(response, true);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.data).toHaveLength(1);
      expect(parsed.issues.length).toBeGreaterThan(0);
    }
  });

  it("keeps nine valid properties when a tenth item has no agency_id", () => {
    const invalid = { ...apiV2FixtureMatrix.ranked } as Partial<typeof apiV2FixtureMatrix.ranked>;
    delete invalid.agency_id;
    const response = {
      contrato: API_V2_CONTRACT,
      ranking: API_V2_RANKING,
      consulta: "casa",
      total: 10,
      limit: 10,
      offset: 0,
      data: [
        ...Array.from({ length: 9 }, (_, index) => ({ ...apiV2FixtureMatrix.ranked, id: `valid-${index}` })),
        invalid,
      ],
    };
    const parsed = parseApiV2Page(response, true);
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    expect(parsed.data.data).toHaveLength(9);
    expect(parsed.issues).toContainEqual(expect.objectContaining({ path: "$.data[9].agency_id" }));
  });
});
