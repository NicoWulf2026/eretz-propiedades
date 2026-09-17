import { describe, expect, it } from "vitest";
import { getApiV2Agency, getApiV2Areas, getApiV2Filters, getApiV2Map, getApiV2Neighborhoods,
  getApiV2PropertiesBatch, getApiV2Property, getApiV2Suggestions, searchApiV2Properties } from "./client";
import type { CatalogSearchQuery } from "@/domain/catalog-search";

const smokeBaseUrl = process.env.ERETZ_API_V2_SMOKE_URL;

function query(changes: Partial<CatalogSearchQuery> = {}): CatalogSearchQuery {
  return { text: "casa", operation: null, propertyType: null, area: null, locality: null,
    neighborhood: null, agencyId: null, minPrice: null, maxPrice: null, currency: null,
    rooms: null, bedrooms: null, bathrooms: null, minSurface: null, maxSurface: null,
    sort: { kind: "technical_relevance" }, pagination: { page: 1, pageSize: 24 }, ...changes };
}

async function smoke<T>(endpoint: string, run: (fetchImpl: typeof fetch) => Promise<T>) {
  let httpStatus: number | null = null;
  const fetchImpl: typeof fetch = async (input, init) => {
    const response = await fetch(input, init);
    httpStatus = response.status;
    return response;
  };
  const started = performance.now();
  const result = await run(fetchImpl);
  const latencyMs = Math.round(performance.now() - started);
  const payload = result as { status?: string; data?: unknown };
  const adaptedCount = Array.isArray(payload.data) ? payload.data.length : payload.data ? 1 : 0;
  console.log(JSON.stringify({ endpoint, httpStatus, latencyMs, validation: payload.status, adaptedCount }));
  expect(httpStatus).toBe(200);
  return result;
}

describe.skipIf(!smokeBaseUrl)("API v2 real discovery smoke", () => {
  it("combines real search, filters and explicit price sort through the runtime boundary", async () => {
    const result = await searchApiV2Properties(query({ operation: "venta", propertyType: "casa",
      currency: "USD", minPrice: 0, bedrooms: 1,
      sort: { kind: "user_selected", value: "price_asc" } }), { baseUrl: smokeBaseUrl });
    expect(result.status).toBe("SUCCESS");
    if (result.status === "FAILURE") throw result.error;
    expect(result.data.properties.length).toBeGreaterThan(0);
    const prices = result.data.properties.map(p => p.price.amount as number);
    expect(prices).toEqual([...prices].sort((a, b) => a - b));
  }, 20_000);

  it("hydrates detail, agency and ordered batch without a PostgreSQL client", async () => {
    const page = await searchApiV2Properties(query(), { baseUrl: smokeBaseUrl });
    if (page.status === "FAILURE") throw page.error;
    const property = page.data.properties[0];
    const detail = await getApiV2Property(property.id, { baseUrl: smokeBaseUrl });
    expect(detail).toMatchObject({ status: "SUCCESS", data: { id: property.id } });
    expect(property.agencyId).toBeTruthy();
    const agency = await getApiV2Agency(property.agencyId!, { baseUrl: smokeBaseUrl });
    expect(agency).toMatchObject({ status: "SUCCESS", data: { contact: { status: "UNAVAILABLE" } } });
    const batch = await getApiV2PropertiesBatch([property.id, "missing-replay-property", property.id],
      { baseUrl: smokeBaseUrl });
    expect(batch).toMatchObject({ status: "PARTIAL_DATA", data: {
      missingIds: ["missing-replay-property"], requestedIds: [property.id, "missing-replay-property"] } });
    if (batch.status === "FAILURE") throw batch.error;
    expect(batch.data.items.map(p => p.id)).toEqual([property.id]);
  }, 20_000);

  it("keeps map volume bounded and reports truncation truthfully", async () => {
    const result = await getApiV2Map(new URLSearchParams({ north: "-21", south: "-56",
      east: "-53", west: "-74", q: "casa", limit: "25" }), { baseUrl: smokeBaseUrl });
    expect(result.status).toBe("SUCCESS");
    if (result.status === "FAILURE") throw result.error;
    expect(result.data.returnedPoints).toBeLessThanOrEqual(25);
    expect(result.data.truncated).toBe(result.data.viewportMatches > result.data.returnedPoints);
    expect(result.data.points.every(p => p.latitude !== 0 && p.longitude !== 0)).toBe(true);
  }, 20_000);

  it("distinguishes real zero results and authoritative missing detail", async () => {
    expect(await searchApiV2Properties(query({ text: "zzznomatchingreplayproperty" }),
      { baseUrl: smokeBaseUrl })).toMatchObject({ status: "SUCCESS_EMPTY", data: { total: 0 } });
    expect(await getApiV2Property("missing-replay-property", { baseUrl: smokeBaseUrl }))
      .toMatchObject({ status: "FAILURE", error: { kind: "NOT_FOUND", status: 404 } });
  }, 20_000);

  it("refuses an out-of-window URL before making any request", async () => {
    let calls = 0;
    const fetchImpl: typeof fetch = async (input, init) => { calls++; return fetch(input, init); };
    expect(await searchApiV2Properties(query({ pagination: { page: 10, pageSize: 24 } }),
      { baseUrl: smokeBaseUrl, fetchImpl })).toMatchObject({ status: "FAILURE", error: { kind: "BAD_REQUEST" } });
    expect(calls).toBe(0);
  });

  it("validates and adapts /v2/areas", async () => {
    const result = await smoke("/v2/areas?q=cor", (fetchImpl) =>
      getApiV2Areas("cor", 20, { baseUrl: smokeBaseUrl, fetchImpl }));
    expect(result).toMatchObject({ status: expect.stringMatching(/SUCCESS|PARTIAL_DATA/) });
  }, 20_000);

  it("validates and adapts /v2/barrios", async () => {
    const result = await smoke("/v2/barrios?q=pal", (fetchImpl) =>
      getApiV2Neighborhoods("pal", 20, { baseUrl: smokeBaseUrl, fetchImpl }));
    expect(result).toMatchObject({ status: expect.stringMatching(/SUCCESS|PARTIAL_DATA/) });
  }, 20_000);

  it("validates and adapts /v2/sugerencias", async () => {
    const result = await smoke("/v2/sugerencias?q=cor", (fetchImpl) =>
      getApiV2Suggestions("cor", 8, { baseUrl: smokeBaseUrl, fetchImpl }));
    expect(result).toMatchObject({ status: expect.stringMatching(/SUCCESS|PARTIAL_DATA/) });
  }, 20_000);

  it("validates and adapts /v2/filtros", async () => {
    const result = await smoke("/v2/filtros", (fetchImpl) =>
      getApiV2Filters({ baseUrl: smokeBaseUrl, fetchImpl }));
    expect(result).toMatchObject({ status: expect.stringMatching(/SUCCESS|PARTIAL_DATA/) });
  }, 20_000);
});
