import {
  CATALOG_CURRENCIES,
  CATALOG_OPERATIONS,
  CATALOG_PROPERTY_TYPES,
  type CatalogCurrency,
  type CatalogOperation,
  type CatalogProperty,
  type CatalogPropertyType,
} from "@/domain/catalog-property";
import {
  catalogPaginationToOffset,
  type CatalogSearchPage,
  type CatalogSearchQuery,
} from "@/domain/catalog-search";
import type {
  CatalogArea,
  CatalogFilterMetadata,
  CatalogGeographyContext,
  CatalogNeighborhood,
  CatalogSuggestion,
} from "@/domain/catalog-discovery";
import {
  API_V2_RANKING,
  type ApiV2AreaDto,
  type ApiV2FiltersResponseDto,
  type ApiV2NeighborhoodsResponseDto,
  type ApiV2PageDto,
  type ApiV2PropertyDto,
  type ApiV2SearchPageDto,
  type ApiV2MapResponseDto,
  type ApiV2SuggestionDto,
} from "./dto";

function known<T extends string>(raw: string | null, values: readonly T[]): T | null {
  return raw !== null && values.includes(raw as T) ? (raw as T) : null;
}

function unavailableGeographyContext(): CatalogGeographyContext {
  return { province: null, department: null, municipality: null, locality: null };
}

export function adaptApiV2Area(dto: ApiV2AreaDto): CatalogArea {
  return {
    id: null,
    name: dto.nombre,
    level: dto.nivel,
    propertyCount: dto.propiedades,
    context: unavailableGeographyContext(),
  };
}

export function adaptApiV2Neighborhood(
  dto: ApiV2NeighborhoodsResponseDto["data"][number],
): CatalogNeighborhood {
  return {
    id: null,
    name: dto.nombre,
    kind: "NEIGHBORHOOD",
    canonical: false,
    propertyCount: dto.propiedades,
    context: unavailableGeographyContext(),
  };
}

export function adaptApiV2Suggestion(dto: ApiV2SuggestionDto): CatalogSuggestion {
  if (dto.tipo === "barrio") {
    return {
      id: null,
      name: dto.nombre,
      kind: "NEIGHBORHOOD",
      level: null,
      canonical: false,
      propertyCount: dto.propiedades,
      context: unavailableGeographyContext(),
    };
  }
  return {
    id: null,
    name: dto.nombre,
    kind: "AREA",
    level: dto.nivel,
    canonical: null,
    propertyCount: dto.propiedades,
    context: unavailableGeographyContext(),
  };
}

export function adaptApiV2Filters(dto: ApiV2FiltersResponseDto): CatalogFilterMetadata {
  const facets = (values: ApiV2FiltersResponseDto["filtros"]["operacion"]) =>
    values.map((value) => ({ value: value.valor, propertyCount: value.propiedades }));
  return {
    operations: facets(dto.filtros.operacion),
    propertyTypes: facets(dto.filtros.tipo_propiedad),
    currencies: facets(dto.filtros.moneda),
    areaLevels: facets(dto.filtros.area_nivel),
    priceRanges: dto.rango_de_precio.map((range) => ({
      currency: range.moneda,
      minimum: range.minimo,
      maximum: range.maximo,
    })),
    missing: {
      operation: dto.sin_dato.operacion,
      propertyType: dto.sin_dato.tipo_propiedad,
      price: dto.sin_dato.precio,
      locality: dto.sin_dato.localidad,
      latitude: dto.sin_dato.latitud,
    },
  };
}

export function adaptApiV2Property(dto: ApiV2PropertyDto): CatalogProperty {
  const rawOperation = dto.operacion;
  const rawPropertyType = dto.tipo_propiedad;
  const rawCurrency = dto.moneda;
  return {
    id: dto.id,
    sourceUrl: dto.source_url ?? null,
    agencyId: dto.agency_id ?? null,
    title: dto.titulo,
    description: dto.descripcion,
    operation: known<CatalogOperation>(rawOperation, CATALOG_OPERATIONS),
    rawOperation,
    propertyType: known<CatalogPropertyType>(rawPropertyType, CATALOG_PROPERTY_TYPES),
    rawPropertyType,
    price: {
      amount: dto.precio,
      currency: known<CatalogCurrency>(rawCurrency, CATALOG_CURRENCIES),
      rawCurrency,
    },
    rooms: dto.ambientes,
    bedrooms: dto.dormitorios,
    bathrooms: dto.banos,
    surfaces: { total: dto.superficie_total, covered: dto.superficie_cubierta },
    images: [...dto.imagenes],
    latitude: dto.latitud,
    longitude: dto.longitud,
    geography: dto.geo ? {
      locality: { name: dto.geo.localidad.nombre, id: dto.geo.localidad.id, provenance: dto.geo.localidad.procedencia },
      municipality: { name: dto.geo.municipio.nombre },
      department: { name: dto.geo.departamento.nombre },
      province: { name: dto.geo.provincia.nombre },
      neighborhood: { name: dto.geo.barrio.nombre },
      searchArea: { level: dto.geo.area_busqueda.nivel, name: dto.geo.area_busqueda.nombre, id: dto.geo.area_busqueda.id, origin: dto.geo.area_busqueda.origen },
      state: dto.geo.estado,
    } : {
      locality: { name: null, id: null, provenance: "UNKNOWN" },
      municipality: { name: null }, department: { name: null }, province: { name: null }, neighborhood: { name: null },
      searchArea: { level: "SIN_AREA", name: null, id: null, origin: "sin_area" }, state: null,
    },
    scopes: [...dto.alcances],
    technicalRanking: dto.ranking
      ? {
          version: dto.ranking.ranking_version,
          total: dto.ranking.total,
          parts: {
            match: dto.ranking.partes.coincidencia,
            location: dto.ranking.partes.ubicacion,
            completeness: dto.ranking.partes.completitud,
            images: dto.ranking.partes.imagenes,
          },
        }
      : null,
  };
}

export type ApiV2SearchRequest =
  | { supported: true; path: "/v2/buscar"; params: URLSearchParams }
  | { supported: false; reason: string };

export const API_V2_RANKED_MAX_OFFSET = 200;

/**
 * API v2 currently ranks `/buscar`, but that endpoint accepts only text,
 * operation and property type. Refuse unsupported combinations rather than
 * pretending filters/sorts were applied.
 */
export function toApiV2SearchRequest(query: CatalogSearchQuery): ApiV2SearchRequest {
  if (query.sort.kind === "user_selected" && query.sort.value === "recent") return { supported: false, reason: "API v2 does not expose a contractual publication timestamp" };
  if (query.agencyId || query.maxSurface !== null) return { supported: false, reason: "API v2 does not expose agency or maximum-surface filters" };
  const { limit, offset } = catalogPaginationToOffset(query.pagination);
  if (query.sort.kind === "technical_relevance" && offset > API_V2_RANKED_MAX_OFFSET) {
    return {
      supported: false,
      reason: `API v2 /buscar only supports ranked pagination through offset ${API_V2_RANKED_MAX_OFFSET}`,
    };
  }
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.text) params.set("q", query.text);
  if (query.operation) params.set("operacion", query.operation);
  if (query.propertyType) params.set("tipo", query.propertyType);
  if (query.area) { params.set("nivel", query.area.level); params.set("area", query.area.name); }
  if (query.locality) params.set("localidad", query.locality);
  if (query.neighborhood) params.set("barrio", query.neighborhood);
  if (query.minPrice !== null) params.set("precio_min", String(query.minPrice));
  if (query.maxPrice !== null) params.set("precio_max", String(query.maxPrice));
  if (query.currency) params.set("moneda", query.currency);
  if (query.rooms !== null) params.set("ambientes", String(query.rooms));
  if (query.bedrooms !== null) params.set("dormitorios", String(query.bedrooms));
  if (query.bathrooms !== null) params.set("banos", String(query.bathrooms));
  if (query.minSurface !== null) params.set("superficie_min", String(query.minSurface));
  params.set("sort", query.sort.kind === "technical_relevance" ? "relevance" : query.sort.value);
  return { supported: true, path: "/v2/buscar", params };
}

export function adaptApiV2Page(dto: ApiV2PageDto | ApiV2SearchPageDto): CatalogSearchPage {
  const pageSize = dto.limit;
  const page = pageSize > 0 ? Math.floor(dto.offset / pageSize) + 1 : 1;
  const ranked = "ranking" in dto && dto.ranking === API_V2_RANKING;
  const hasMoreResults = dto.offset + dto.data.length < dto.total;
  const nextOffsetAllowed = dto.offset + pageSize <= API_V2_RANKED_MAX_OFFSET;
  return {
    properties: dto.data.map(adaptApiV2Property),
    total: dto.total,
    reachableSearchWindow: ranked ? Math.min(dto.total, API_V2_RANKED_MAX_OFFSET + pageSize) : null,
    searchWindowExhausted: ranked && hasMoreResults && !nextOffsetAllowed,
    page,
    pageSize,
    hasPrevious: dto.offset > 0,
    hasNext: hasMoreResults && (!ranked || nextOffsetAllowed),
    rankingVersion: ranked && dto.ranking === API_V2_RANKING ? API_V2_RANKING : null,
  };
}

export function adaptApiV2Map(dto: ApiV2MapResponseDto) {
  return {
    points: dto.data.map((point) => ({
      id: point.id,
      latitude: point.latitud,
      longitude: point.longitud,
      price: point.precio,
      currency: known<CatalogCurrency>(point.moneda, CATALOG_CURRENCIES),
      operation: known<CatalogOperation>(point.operacion, CATALOG_OPERATIONS),
      propertyType: known<CatalogPropertyType>(point.tipo_propiedad, CATALOG_PROPERTY_TYPES),
      title: point.titulo,
    })),
    totalMatches: dto.total_matches,
    viewportMatches: dto.viewport_matches,
    returnedPoints: dto.returned_points,
    truncated: dto.truncated,
  };
}
