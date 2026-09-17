import "server-only";

import type { CatalogProperty } from "@/domain/catalog-property";
import type { ApiV2AgencyResponseDto } from "./dto";
import type { CatalogSearchPage, CatalogSearchQuery } from "@/domain/catalog-search";
import type { CatalogArea, CatalogFilterMetadata, CatalogNeighborhood, CatalogSuggestion } from "@/domain/catalog-discovery";
import {
  adaptApiV2Area,
  adaptApiV2Filters,
  adaptApiV2Neighborhood,
  adaptApiV2Page,
  adaptApiV2Property,
  adaptApiV2Suggestion,
  adaptApiV2Map,
  toApiV2SearchRequest,
} from "./adapters";
import { ApiV2Error, type ApiV2Result } from "./errors";
import {
  parseApiV2Areas,
  parseApiV2Filters,
  parseApiV2Neighborhoods,
  parseApiV2Page,
  parseApiV2Property,
  parseApiV2Suggestions,
  parseApiV2Map,
  parseApiV2Agency,
  parseApiV2Batch,
} from "./schemas";

export type ApiV2ClientOptions = {
  baseUrl?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
};

function resolveBaseUrl(override?: string): string | null {
  const raw = override?.trim() || process.env.ERETZ_API_V2_BASE_URL?.trim() || "";
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href.replace(/\/$/, "") : null;
  } catch {
    return null;
  }
}

function httpError(status: number, message: string): ApiV2Error {
  if (status === 404) return new ApiV2Error("NOT_FOUND", message, status);
  if (status === 400 || status === 422) return new ApiV2Error("BAD_REQUEST", message, status);
  return new ApiV2Error("SERVER_ERROR", message, status);
}

function boundedLimit(value: number, maximum: number): number {
  return Math.min(maximum, Math.max(1, Math.trunc(value)));
}

function invalidResponse<T>(message: string, issues: ApiV2Error["issues"]): ApiV2Result<T> {
  return { status: "FAILURE", error: new ApiV2Error("INVALID_RESPONSE", message, null, { issues }) };
}

export async function fetchApiV2Json(
  path: string,
  params: URLSearchParams | null,
  options: ApiV2ClientOptions & { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<ApiV2Result<unknown>> {
  const baseUrl = resolveBaseUrl(options.baseUrl);
  if (!baseUrl) {
    return { status: "FAILURE", error: new ApiV2Error("UNCONFIGURED", "ERETZ_API_V2_BASE_URL is missing or invalid") };
  }
  const url = new URL(path, `${baseUrl}/`);
  if (params) url.search = params.toString();

  const controller = new AbortController();
  let timedOut = false;
  const timeoutMs = Math.max(1, options.timeoutMs ?? 10_000);
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const abortFromCaller = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) abortFromCaller();
  else options.signal?.addEventListener("abort", abortFromCaller, { once: true });

  try {
    const response = await (options.fetchImpl ?? fetch)(url, {
      method: options.method ?? "GET",
      headers: { accept: "application/json", ...(options.body === undefined ? {} : { "content-type": "application/json" }) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      return { status: "FAILURE", error: httpError(response.status, `API v2 returned HTTP ${response.status}`) };
    }
    try {
      return { status: "SUCCESS", data: await response.json() as unknown };
    } catch (cause) {
      return {
        status: "FAILURE",
        error: new ApiV2Error("INVALID_RESPONSE", "API v2 returned invalid JSON", response.status, { cause }),
      };
    }
  } catch (cause) {
    const kind = timedOut ? "TIMEOUT" : "NETWORK_ERROR";
    return { status: "FAILURE", error: new ApiV2Error(kind, timedOut ? "API v2 request timed out" : "API v2 request failed", null, { cause }) };
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export type CatalogMapPage = ReturnType<typeof adaptApiV2Map>;

export async function getApiV2Map(params: URLSearchParams, options: ApiV2ClientOptions = {}): Promise<ApiV2Result<CatalogMapPage>> {
  const raw = await fetchApiV2Json("/v2/propiedades/mapa", params, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Map(raw.data);
  if (!parsed.success) return invalidResponse("API v2 map response does not match the contract", parsed.issues);
  const data = adaptApiV2Map(parsed.data);
  if (parsed.issues.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  return { status: data.points.length ? "SUCCESS" : "SUCCESS_EMPTY", data };
}

export async function getApiV2Agency(id: string, options: ApiV2ClientOptions = {}): Promise<ApiV2Result<ApiV2AgencyResponseDto["data"]>> {
  const raw = await fetchApiV2Json(`/v2/agencias/${encodeURIComponent(id)}`, null, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Agency(raw.data);
  if (!parsed.success) return invalidResponse("API v2 agency response does not match the contract", parsed.issues);
  return { status: "SUCCESS", data: parsed.data.data };
}

export async function getApiV2PropertiesBatch(ids: string[], options: ApiV2ClientOptions = {}): Promise<ApiV2Result<{ items: CatalogProperty[]; missingIds: string[]; requestedIds: string[] }>> {
  const raw = await fetchApiV2Json("/v2/propiedades/batch", null, { ...options, method: "POST", body: { ids } });
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Batch(raw.data);
  if (!parsed.success) return invalidResponse("API v2 batch response does not match the contract", parsed.issues);
  const data = { items: parsed.data.items.map(adaptApiV2Property), missingIds: parsed.data.missing_ids, requestedIds: parsed.data.requested_ids };
  if (parsed.issues.length || data.missingIds.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  return { status: data.items.length ? "SUCCESS" : "SUCCESS_EMPTY", data };
}

export async function getApiV2Property(id: string, options: ApiV2ClientOptions = {}): Promise<ApiV2Result<CatalogProperty>> {
  const raw = await fetchApiV2Json(`/v2/propiedades/${encodeURIComponent(id)}`, null, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Property(raw.data);
  if (!parsed.success) {
    return {
      status: "FAILURE",
      error: new ApiV2Error("INVALID_RESPONSE", "API v2 property response does not match the contract", null, { issues: parsed.issues }),
    };
  }
  return { status: "SUCCESS", data: adaptApiV2Property(parsed.data) };
}

export async function searchApiV2Properties(
  query: CatalogSearchQuery,
  options: ApiV2ClientOptions = {},
): Promise<ApiV2Result<CatalogSearchPage>> {
  const request = toApiV2SearchRequest(query);
  if (!request.supported) {
    return { status: "FAILURE", error: new ApiV2Error("BAD_REQUEST", request.reason) };
  }
  const raw = await fetchApiV2Json(request.path, request.params, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Page(raw.data, true);
  if (!parsed.success) {
    return {
      status: "FAILURE",
      error: new ApiV2Error("INVALID_RESPONSE", "API v2 search response does not match the contract", null, { issues: parsed.issues }),
    };
  }
  const page = adaptApiV2Page(parsed.data);
  if (parsed.issues.length > 0) return { status: "PARTIAL_DATA", data: page, issues: parsed.issues };
  if (page.properties.length === 0) return { status: "SUCCESS_EMPTY", data: page };
  return { status: "SUCCESS", data: page };
}

export async function getApiV2Areas(
  query: string | null = null,
  limit = 20,
  options: ApiV2ClientOptions = {},
): Promise<ApiV2Result<CatalogArea[]>> {
  const params = new URLSearchParams({ limit: String(boundedLimit(limit, 100)) });
  const clean = query?.trim().slice(0, 80);
  if (clean) params.set("q", clean);
  const raw = await fetchApiV2Json("/v2/areas", params, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Areas(raw.data);
  if (!parsed.success) return invalidResponse("API v2 areas response does not match the contract", parsed.issues);
  const data = parsed.data.data.map(adaptApiV2Area);
  if (parsed.issues.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  return { status: data.length ? "SUCCESS" : "SUCCESS_EMPTY", data };
}

export async function getApiV2Neighborhoods(
  query: string | null = null,
  limit = 50,
  options: ApiV2ClientOptions = {},
): Promise<ApiV2Result<CatalogNeighborhood[]>> {
  const params = new URLSearchParams({ limit: String(boundedLimit(limit, 200)) });
  const clean = query?.trim().slice(0, 80);
  if (clean) params.set("q", clean);
  const raw = await fetchApiV2Json("/v2/barrios", params, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Neighborhoods(raw.data);
  if (!parsed.success) return invalidResponse("API v2 neighborhoods response does not match the contract", parsed.issues);
  const data = parsed.data.data.map(adaptApiV2Neighborhood);
  if (parsed.issues.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  return { status: data.length ? "SUCCESS" : "SUCCESS_EMPTY", data };
}

export async function getApiV2Suggestions(
  query: string,
  limit = 8,
  options: ApiV2ClientOptions = {},
): Promise<ApiV2Result<CatalogSuggestion[]>> {
  const clean = query.trim().slice(0, 60);
  if (clean.length < 2) {
    return { status: "FAILURE", error: new ApiV2Error("BAD_REQUEST", "API v2 suggestions require at least two characters") };
  }
  const params = new URLSearchParams({ q: clean, limit: String(boundedLimit(limit, 20)) });
  const raw = await fetchApiV2Json("/v2/sugerencias", params, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Suggestions(raw.data);
  if (!parsed.success) return invalidResponse("API v2 suggestions response does not match the contract", parsed.issues);
  const data = parsed.data.data.map(adaptApiV2Suggestion);
  if (parsed.issues.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  return { status: data.length ? "SUCCESS" : "SUCCESS_EMPTY", data };
}

export async function getApiV2Filters(
  options: ApiV2ClientOptions = {},
): Promise<ApiV2Result<CatalogFilterMetadata>> {
  const raw = await fetchApiV2Json("/v2/filtros", null, options);
  if (raw.status === "FAILURE") return raw;
  const parsed = parseApiV2Filters(raw.data);
  if (!parsed.success) return invalidResponse("API v2 filters response does not match the contract", parsed.issues);
  const data = adaptApiV2Filters(parsed.data);
  if (parsed.issues.length) return { status: "PARTIAL_DATA", data, issues: parsed.issues };
  const empty = !data.operations.length && !data.propertyTypes.length && !data.currencies.length && !data.areaLevels.length;
  return { status: empty ? "SUCCESS_EMPTY" : "SUCCESS", data };
}
