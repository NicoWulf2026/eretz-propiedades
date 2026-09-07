import "server-only";

import type { CatalogProperty } from "@/domain/catalog-property";
import type { CatalogSearchPage, CatalogSearchQuery } from "@/domain/catalog-search";
import { adaptApiV2Page, adaptApiV2Property, toApiV2SearchRequest } from "./adapters";
import { ApiV2Error, type ApiV2Result } from "./errors";
import { parseApiV2Page, parseApiV2Property } from "./schemas";

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

export async function fetchApiV2Json(
  path: string,
  params: URLSearchParams | null,
  options: ApiV2ClientOptions = {},
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
      method: "GET",
      headers: { accept: "application/json" },
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
