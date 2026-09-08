import { describe, expect, it, vi } from "vitest";
import { apiV2FiltersFixture, apiV2SuggestionsFixture } from "@/test/api-v2-fixtures";
import { loadDiscoveryFilterMetadata, searchDiscoverySuggestions } from "./discovery-service";

const baseUrl = "https://api.example.test";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("API v2 autocomplete facade", () => {
  it("does not call the API for queries shorter than two characters", async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("c", { baseUrl, fetchImpl })).toEqual({ status: "SUCCESS_EMPTY", suggestions: [] });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("queries API v2 and maps typed geography to the stable presentation contract", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(apiV2SuggestionsFixture)) as unknown as typeof fetch;
    const result = await searchDiscoverySuggestions("  cór  ", { baseUrl, fetchImpl });
    expect(result.status).toBe("SUCCESS");
    expect(fetchImpl).toHaveBeenCalledOnce();
    const requested = new URL(String(vi.mocked(fetchImpl).mock.calls[0][0]));
    expect(requested.pathname).toBe("/v2/sugerencias");
    expect(requested.searchParams.get("q")).toBe("cór");
    expect(requested.searchParams.get("limit")).toBe("12");
    if (result.status !== "SUCCESS") return;
    expect(result.suggestions).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "provincia", geography: expect.objectContaining({ level: "PROVINCIA", entityId: null }) }),
      expect.objectContaining({ category: "municipio", geography: expect.objectContaining({ level: "MUNICIPIO", locality: null }) }),
      expect.objectContaining({ category: "barrio", geography: expect.objectContaining({ canonical: false, level: null }) }),
    ]));
  });

  it("distinguishes empty success from transport and validation failures", async () => {
    const emptyFetch = vi.fn(async () => jsonResponse({ ...apiV2SuggestionsFixture, data: [] })) as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("nada", { baseUrl, fetchImpl: emptyFetch })).toEqual({ status: "SUCCESS_EMPTY", suggestions: [] });

    const networkFetch = vi.fn(async () => { throw new TypeError("offline"); }) as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("casa", { baseUrl, fetchImpl: networkFetch })).toMatchObject({ status: "FAILURE", error: { kind: "NETWORK_ERROR" } });

    const timeoutFetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    })) as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("casa", { baseUrl, fetchImpl: timeoutFetch, timeoutMs: 1 })).toMatchObject({ status: "FAILURE", error: { kind: "TIMEOUT" } });

    const invalidFetch = vi.fn(async () => jsonResponse({ contrato: "wrong", data: [] })) as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("casa", { baseUrl, fetchImpl: invalidFetch })).toMatchObject({ status: "FAILURE", error: { kind: "INVALID_RESPONSE" } });

    const serverFetch = vi.fn(async () => jsonResponse({ detail: "unavailable" }, 500)) as unknown as typeof fetch;
    expect(await searchDiscoverySuggestions("casa", { baseUrl, fetchImpl: serverFetch })).toMatchObject({ status: "FAILURE", error: { kind: "SERVER_ERROR" } });
  });

  it("returns valid suggestions with PARTIAL_DATA when one collection item is malformed", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      ...apiV2SuggestionsFixture,
      data: [...apiV2SuggestionsFixture.data, { tipo: "area", nivel: "CIUDAD", nombre: "Incorrecta", propiedades: 1 }],
    })) as unknown as typeof fetch;
    const result = await searchDiscoverySuggestions("cor", { baseUrl, fetchImpl });
    expect(result).toMatchObject({ status: "PARTIAL_DATA" });
    if (result.status === "PARTIAL_DATA") {
      expect(result.suggestions).toHaveLength(apiV2SuggestionsFixture.data.length);
      expect(result.issues).not.toHaveLength(0);
    }
  });

  it("exposes filter metadata through a serializable facade", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(apiV2FiltersFixture)) as unknown as typeof fetch;
    const result = await loadDiscoveryFilterMetadata({ baseUrl, fetchImpl });
    expect(result).toMatchObject({
      status: "SUCCESS",
      metadata: { operations: expect.arrayContaining([{ value: "venta", propertyCount: 42536 }]) },
    });
    expect(JSON.parse(JSON.stringify(result))).toEqual(result);
  });

  it("preserves empty and failure metadata states instead of inventing facets", async () => {
    const emptyFetch = vi.fn(async () => jsonResponse({
      ...apiV2FiltersFixture,
      filtros: { operacion: [], tipo_propiedad: [], moneda: [], area_nivel: [] },
    })) as unknown as typeof fetch;
    await expect(loadDiscoveryFilterMetadata({ baseUrl, fetchImpl: emptyFetch })).resolves.toEqual({
      status: "SUCCESS_EMPTY", metadata: null,
    });

    const networkFetch = vi.fn(async () => { throw new TypeError("offline"); }) as unknown as typeof fetch;
    await expect(loadDiscoveryFilterMetadata({ baseUrl, fetchImpl: networkFetch })).resolves.toEqual({
      status: "FAILURE", metadata: null, error: { kind: "NETWORK_ERROR" },
    });
  });
});
