import { describe, expect, it } from "vitest";
import { getApiV2Areas, getApiV2Filters, getApiV2Neighborhoods, getApiV2Suggestions } from "./client";

const smokeBaseUrl = process.env.ERETZ_API_V2_SMOKE_URL;

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
