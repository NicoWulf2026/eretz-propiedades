/**
 * Property model consumed by future catalog UI adapters.
 *
 * It deliberately differs from `types/property.ts::Property`: that type is the
 * current legacy presentation model. This one preserves the semantics exposed
 * by API v2 without flattening geography or turning unknown values into UI
 * fallbacks.
 */

export const CATALOG_OPERATIONS = ["venta", "alquiler", "alquiler_temporario"] as const;
export type CatalogOperation = (typeof CATALOG_OPERATIONS)[number];

export const CATALOG_PROPERTY_TYPES = [
  "departamento",
  "casa",
  "terreno",
  "local",
  "cochera",
  "oficina",
  "galpon",
] as const;
export type CatalogPropertyType = (typeof CATALOG_PROPERTY_TYPES)[number];

export const CATALOG_CURRENCIES = ["USD", "ARS"] as const;
export type CatalogCurrency = (typeof CATALOG_CURRENCIES)[number];

export const SEARCH_AREA_LEVELS = [
  "LOCALIDAD",
  "MUNICIPIO",
  "DEPARTAMENTO",
  "PROVINCIA",
  "SIN_AREA",
] as const;
export type SearchAreaLevel = (typeof SEARCH_AREA_LEVELS)[number];

export const SEARCH_AREA_ORIGINS = [
  "localidad",
  "municipio",
  "departamento",
  "provincia",
  "sin_area",
] as const;
export type SearchAreaOrigin = (typeof SEARCH_AREA_ORIGINS)[number];

export const LOCALITY_PROVENANCES = ["CANONICAL_NORMALIZED", "UNKNOWN"] as const;
export type LocalityProvenance = (typeof LOCALITY_PROVENANCES)[number];

export type CatalogGeoName = { name: string | null };

export type CatalogLocality = CatalogGeoName & {
  id: string | null;
  provenance: LocalityProvenance;
};

export type CatalogSearchArea = {
  level: SearchAreaLevel;
  name: string | null;
  id: string | null;
  origin: SearchAreaOrigin;
};

export type CatalogGeography = {
  locality: CatalogLocality;
  municipality: CatalogGeoName;
  department: CatalogGeoName;
  province: CatalogGeoName;
  neighborhood: CatalogGeoName;
  searchArea: CatalogSearchArea;
  state: "GEO_CONFLICT" | null;
};

export type TechnicalRanking = {
  version: "eretz_ranking_tecnico_v1";
  total: number;
  parts: {
    match: number;
    location: number;
    completeness: number;
    images: number;
  };
};

export type CatalogProperty = {
  id: string;
  sourceUrl: string;
  /** API v2 exposes the identifier, not agency details or contact channels. */
  agencyId: string;
  title: string | null;
  description: string | null;
  operation: CatalogOperation | null;
  rawOperation: string | null;
  propertyType: CatalogPropertyType | null;
  rawPropertyType: string | null;
  price: {
    amount: number | null;
    currency: CatalogCurrency | null;
    rawCurrency: string | null;
  };
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  surfaces: {
    total: number | null;
    covered: number | null;
  };
  images: readonly string[];
  latitude: number | null;
  longitude: number | null;
  geography: CatalogGeography;
  scopes: readonly string[];
  technicalRanking: TechnicalRanking | null;
};

/** Missing coordinates remain missing; they are never coerced to `0,0`. */
export function hasCatalogMapCoordinates(
  property: CatalogProperty,
): property is CatalogProperty & { latitude: number; longitude: number } {
  return property.latitude !== null && property.longitude !== null;
}
