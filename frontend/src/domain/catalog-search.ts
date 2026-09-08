import type { CatalogOperation, CatalogProperty, CatalogPropertyType, SearchAreaLevel } from "./catalog-property";

export type CatalogUserSort = "recent" | "price_asc" | "price_desc";
export type CatalogSort =
  | { kind: "technical_relevance" }
  | { kind: "user_selected"; value: CatalogUserSort };

export type CatalogPagination = {
  page: number;
  pageSize: number;
};

export type CatalogSearchQuery = {
  text: string;
  operation: CatalogOperation | null;
  propertyType: CatalogPropertyType | null;
  area: { level: SearchAreaLevel; name: string } | null;
  locality: string | null;
  neighborhood: string | null;
  agencyId: string | null;
  minPrice: number | null;
  maxPrice: number | null;
  currency: string | null;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  minSurface: number | null;
  maxSurface: number | null;
  sort: CatalogSort;
  pagination: CatalogPagination;
};

export type CatalogSearchPage = {
  properties: CatalogProperty[];
  /** All matches reported by the backend, including results outside the ranked window. */
  total: number;
  /** Maximum number of matches addressable through ranked pagination; null for stable catalog pages. */
  reachableSearchWindow: number | null;
  /** More matches exist, but the next ranked offset is forbidden by the backend contract. */
  searchWindowExhausted: boolean;
  page: number;
  pageSize: number;
  hasPrevious: boolean;
  hasNext: boolean;
  rankingVersion: "eretz_ranking_tecnico_v1" | null;
};

export function catalogPaginationToOffset(pagination: CatalogPagination): {
  limit: number;
  offset: number;
} {
  const pageSize = Math.min(100, Math.max(1, Math.trunc(pagination.pageSize)));
  const page = Math.max(1, Math.trunc(pagination.page));
  return { limit: pageSize, offset: (page - 1) * pageSize };
}
