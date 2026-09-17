import "server-only";

import type { CatalogSuggestion } from "@/domain/catalog-discovery";
import { getApiV2Filters, getApiV2Suggestions, type ApiV2ClientOptions } from "@/lib/api-v2/client";
import type { DiscoveryAutocompleteResponse } from "@/lib/discovery-contract";
import type { DiscoveryFilterMetadataResponse } from "@/lib/discovery-contract";
import type { SearchSuggestion } from "@/types/property";

const CATEGORY_BY_LEVEL: Record<
  Exclude<CatalogSuggestion["level"], null>,
  SearchSuggestion["category"]
> = {
  PROVINCIA: "provincia",
  DEPARTAMENTO: "departamento",
  MUNICIPIO: "municipio",
  LOCALIDAD: "localidad",
  SIN_AREA: "área",
};

function stablePresentationId(suggestion: CatalogSuggestion): string {
  const normalized = suggestion.name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("es-AR")
    .replace(/\s+/g, "-");
  return `${suggestion.kind.toLocaleLowerCase("en-US")}:${suggestion.level ?? "BARRIO"}:${normalized}`;
}

export function presentCatalogSuggestion(suggestion: CatalogSuggestion): SearchSuggestion {
  return {
    id: stablePresentationId(suggestion),
    label: suggestion.name,
    category: suggestion.kind === "NEIGHBORHOOD" ? "barrio" : CATEGORY_BY_LEVEL[suggestion.level],
    query: suggestion.name,
    context: `${suggestion.propertyCount.toLocaleString("es-AR")} propiedades`,
    count: suggestion.propertyCount,
    geography: {
      kind: suggestion.kind === "NEIGHBORHOOD" ? "neighborhood" : "area",
      entityId: suggestion.id,
      level: suggestion.level,
      canonical: suggestion.canonical,
      province: suggestion.context.province,
      department: suggestion.context.department,
      municipality: suggestion.context.municipality,
      locality: suggestion.context.locality,
    },
  };
}

export async function searchDiscoverySuggestions(
  query: string,
  options: ApiV2ClientOptions = {},
): Promise<DiscoveryAutocompleteResponse> {
  const clean = query.replace(/[<>]/g, "").trim().slice(0, 60);
  if (clean.length < 2) return { status: "SUCCESS_EMPTY", suggestions: [] };
  const result = await getApiV2Suggestions(clean, 12, options);
  if (result.status === "FAILURE") {
    return { status: "FAILURE", suggestions: [], error: { kind: result.error.kind } };
  }
  const suggestions = result.data.map(presentCatalogSuggestion);
  if (result.status === "PARTIAL_DATA") {
    return { status: "PARTIAL_DATA", suggestions, issues: result.issues };
  }
  return { status: result.status, suggestions };
}

export async function loadDiscoveryFilterMetadata(
  options: ApiV2ClientOptions = {},
): Promise<DiscoveryFilterMetadataResponse> {
  const result = await getApiV2Filters(options);
  if (result.status === "FAILURE") {
    return { status: "FAILURE", metadata: null, error: { kind: result.error.kind } };
  }
  if (result.status === "SUCCESS_EMPTY") return { status: "SUCCESS_EMPTY", metadata: null };
  if (result.status === "PARTIAL_DATA") {
    return { status: "PARTIAL_DATA", metadata: result.data, issues: result.issues };
  }
  return { status: "SUCCESS", metadata: result.data };
}
