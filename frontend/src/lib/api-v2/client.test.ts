import { describe, expect, it, vi } from "vitest";
import type { CatalogSearchQuery } from "@/domain/catalog-search";
import { apiV2FixtureMatrix, invalidMissingAgencyDto } from "@/test/api-v2-fixtures";
import { API_V2_CONTRACT, API_V2_RANKING } from "./dto";
import { fetchApiV2Json, getApiV2Property, searchApiV2Properties } from "./client";

const baseUrl = "https://api.example.test";
const query: CatalogSearchQuery = {
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
  pagination: { page: 1, pageSize: 24 },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("API v2 client error and success model", () => {
  it.each([
    [404, "NOT_FOUND"],
    [422, "BAD_REQUEST"],
    [500, "SERVER_ERROR"],
  ] as const)("maps HTTP %s to %s", async (status, kind) => {
    const fetchImpl = vi.fn(async () => jsonResponse({ detail: "error" }, status)) as unknown as typeof fetch;
    const result = await fetchApiV2Json("/v2/stats", null, { baseUrl, fetchImpl });
    expect(result).toMatchObject({ status: "FAILURE", error: { kind, status } });
  });

  it("distinguishes invalid JSON from a successful empty result", async () => {
    const invalidFetch = vi.fn(async () => new Response("not-json", { status: 200 })) as unknown as typeof fetch;
    expect(await fetchApiV2Json("/v2/stats", null, { baseUrl, fetchImpl: invalidFetch })).toMatchObject({
      status: "FAILURE",
      error: { kind: "INVALID_RESPONSE" },
    });

    const emptyFetch = vi.fn(async () => jsonResponse({
      contrato: API_V2_CONTRACT,
      ranking: API_V2_RANKING,
      consulta: "none",
      total: 0,
      limit: 24,
      offset: 0,
      data: [],
    })) as unknown as typeof fetch;
    expect(await searchApiV2Properties(query, { baseUrl, fetchImpl: emptyFetch })).toMatchObject({ status: "SUCCESS_EMPTY", data: { total: 0 } });
  });

  it("distinguishes network failure and timeout", async () => {
    const networkFetch = vi.fn(async () => { throw new TypeError("offline"); }) as unknown as typeof fetch;
    expect(await fetchApiV2Json("/v2/stats", null, { baseUrl, fetchImpl: networkFetch })).toMatchObject({ status: "FAILURE", error: { kind: "NETWORK_ERROR" } });

    const timeoutFetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    })) as unknown as typeof fetch;
    expect(await fetchApiV2Json("/v2/stats", null, { baseUrl, fetchImpl: timeoutFetch, timeoutMs: 1 })).toMatchObject({ status: "FAILURE", error: { kind: "TIMEOUT" } });
  });

  it("returns INVALID_RESPONSE for malformed property detail instead of NOT_FOUND", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(invalidMissingAgencyDto)) as unknown as typeof fetch;
    expect(await getApiV2Property("property", { baseUrl, fetchImpl })).toMatchObject({ status: "FAILURE", error: { kind: "INVALID_RESPONSE" } });
  });

  it("returns partial data with validation issues and keeps valid rows", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      contrato: API_V2_CONTRACT,
      ranking: API_V2_RANKING,
      consulta: "casa",
      total: 2,
      limit: 24,
      offset: 0,
      data: [apiV2FixtureMatrix.ranked, invalidMissingAgencyDto],
    })) as unknown as typeof fetch;
    const result = await searchApiV2Properties(query, { baseUrl, fetchImpl });
    expect(result).toMatchObject({ status: "PARTIAL_DATA", data: { total: 2 } });
    if (result.status === "PARTIAL_DATA") {
      expect(result.data.properties).toHaveLength(1);
      expect(result.issues).toContainEqual(expect.objectContaining({ path: "$.data[1].agency_id" }));
    }
  });

  it("does not call the network for unsupported user sorting", async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    const result = await searchApiV2Properties(
      { ...query, sort: { kind: "user_selected", value: "recent" } },
      { baseUrl, fetchImpl },
    );
    expect(result).toMatchObject({ status: "FAILURE", error: { kind: "BAD_REQUEST" } });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
