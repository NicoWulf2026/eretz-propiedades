import { describe, expect, it, vi } from "vitest";
import {
  apiV2AreasFixture,
  apiV2FiltersFixture,
  apiV2NeighborhoodsFixture,
  apiV2SuggestionsFixture,
} from "@/test/api-v2-fixtures";
import { getApiV2Areas, getApiV2Filters, getApiV2Neighborhoods, getApiV2Suggestions } from "./client";

const baseUrl = "https://api.example.test";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

describe("API v2 discovery client", () => {
  it("loads and validates areas, neighborhoods and filter metadata", async () => {
    const responses = [apiV2AreasFixture, apiV2NeighborhoodsFixture, apiV2FiltersFixture];
    const fetchImpl = vi.fn(async () => jsonResponse(responses.shift())) as unknown as typeof fetch;
    await expect(getApiV2Areas("cór", 20, { baseUrl, fetchImpl })).resolves.toMatchObject({ status: "SUCCESS", data: expect.any(Array) });
    await expect(getApiV2Neighborhoods("pal", 50, { baseUrl, fetchImpl })).resolves.toMatchObject({
      status: "SUCCESS",
      data: expect.arrayContaining([expect.objectContaining({ canonical: false })]),
    });
    await expect(getApiV2Filters({ baseUrl, fetchImpl })).resolves.toMatchObject({ status: "SUCCESS", data: { missing: { locality: 48000 } } });
    const urls = vi.mocked(fetchImpl).mock.calls.map((call) => new URL(String(call[0])));
    expect(urls.map((url) => url.pathname)).toEqual(["/v2/areas", "/v2/barrios", "/v2/filtros"]);
    expect(urls[0].searchParams.get("q")).toBe("cór");
  });

  it("returns SUCCESS_EMPTY for a valid empty suggestions response", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ...apiV2SuggestionsFixture, data: [] })) as unknown as typeof fetch;
    await expect(getApiV2Suggestions("zz", 8, { baseUrl, fetchImpl })).resolves.toEqual({ status: "SUCCESS_EMPTY", data: [] });
  });

  it("returns PARTIAL_DATA while keeping valid discovery items", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      ...apiV2AreasFixture,
      data: [...apiV2AreasFixture.data, { nivel: "CIUDAD", nombre: "Incorrecta", propiedades: 1 }],
    })) as unknown as typeof fetch;
    const result = await getApiV2Areas(null, 20, { baseUrl, fetchImpl });
    expect(result).toMatchObject({ status: "PARTIAL_DATA" });
    if (result.status === "PARTIAL_DATA") {
      expect(result.data).toHaveLength(apiV2AreasFixture.data.length);
      expect(result.issues).not.toHaveLength(0);
    }
  });
});
