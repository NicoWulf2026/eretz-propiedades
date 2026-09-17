import type { SearchAreaLevel } from "./catalog-property";

export type CatalogGeographyContext = {
  province: string | null;
  department: string | null;
  municipality: string | null;
  locality: string | null;
};

export type CatalogArea = {
  /** API v2 does not currently expose an area identifier. */
  id: null;
  name: string;
  level: SearchAreaLevel;
  propertyCount: number;
  context: CatalogGeographyContext;
};

export type CatalogNeighborhood = {
  /** API v2 returns source text, not a canonical neighborhood entity. */
  id: null;
  name: string;
  kind: "NEIGHBORHOOD";
  canonical: false;
  propertyCount: number;
  context: CatalogGeographyContext;
};

export type CatalogSuggestion =
  | {
      id: null;
      name: string;
      kind: "AREA";
      level: SearchAreaLevel;
      canonical: null;
      propertyCount: number;
      context: CatalogGeographyContext;
    }
  | {
      id: null;
      name: string;
      kind: "NEIGHBORHOOD";
      level: null;
      canonical: false;
      propertyCount: number;
      context: CatalogGeographyContext;
    };

export type CatalogFacetValue = {
  value: string | number;
  propertyCount: number;
};

export type CatalogFilterMetadata = {
  operations: CatalogFacetValue[];
  propertyTypes: CatalogFacetValue[];
  currencies: CatalogFacetValue[];
  areaLevels: CatalogFacetValue[];
  priceRanges: Array<{ currency: string; minimum: number; maximum: number }>;
  missing: {
    operation: number;
    propertyType: number;
    price: number;
    locality: number;
    latitude: number;
  };
};

export type CatalogFilterCutoverStatus =
  | "SUPPORTED_NOW"
  | "DISPLAY_ONLY_LEGACY"
  | "BLOCKED_BY_BACKEND"
  | "UNUSED";
