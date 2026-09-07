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
import { API_V2_RANKING, type ApiV2PageDto, type ApiV2PropertyDto, type ApiV2SearchPageDto } from "./dto";

function known<T extends string>(raw: string | null, values: readonly T[]): T | null {
  return raw !== null && values.includes(raw as T) ? (raw as T) : null;
}

export function adaptApiV2Property(dto: ApiV2PropertyDto): CatalogProperty {
  const rawOperation = dto.operacion;
  const rawPropertyType = dto.tipo_propiedad;
  const rawCurrency = dto.moneda;
  return {
    id: dto.id,
    sourceUrl: dto.source_url,
    agencyId: dto.agency_id,
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
    geography: {
      locality: {
        name: dto.geo.localidad.nombre,
        id: dto.geo.localidad.id,
        provenance: dto.geo.localidad.procedencia,
      },
      municipality: { name: dto.geo.municipio.nombre },
      department: { name: dto.geo.departamento.nombre },
      province: { name: dto.geo.provincia.nombre },
      neighborhood: { name: dto.geo.barrio.nombre },
      searchArea: {
        level: dto.geo.area_busqueda.nivel,
        name: dto.geo.area_busqueda.nombre,
        id: dto.geo.area_busqueda.id,
        origin: dto.geo.area_busqueda.origen,
      },
      state: dto.geo.estado,
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

/**
 * API v2 currently ranks `/buscar`, but that endpoint accepts only text,
 * operation and property type. Refuse unsupported combinations rather than
 * pretending filters/sorts were applied.
 */
export function toApiV2SearchRequest(query: CatalogSearchQuery): ApiV2SearchRequest {
  if (query.sort.kind !== "technical_relevance") {
    return { supported: false, reason: "API v2 does not expose explicit user-selected sorting" };
  }
  if (
    query.area || query.locality || query.neighborhood || query.agencyId ||
    query.minPrice !== null || query.maxPrice !== null || query.currency ||
    query.rooms !== null || query.bedrooms !== null || query.bathrooms !== null ||
    query.minSurface !== null || query.maxSurface !== null
  ) {
    return { supported: false, reason: "API v2 /buscar does not accept the requested filter set" };
  }
  const { limit, offset } = catalogPaginationToOffset(query.pagination);
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.text) params.set("q", query.text);
  if (query.operation) params.set("operacion", query.operation);
  if (query.propertyType) params.set("tipo", query.propertyType);
  return { supported: true, path: "/v2/buscar", params };
}

export function adaptApiV2Page(dto: ApiV2PageDto | ApiV2SearchPageDto): CatalogSearchPage {
  const pageSize = dto.limit;
  const page = pageSize > 0 ? Math.floor(dto.offset / pageSize) + 1 : 1;
  return {
    properties: dto.data.map(adaptApiV2Property),
    total: dto.total,
    page,
    pageSize,
    hasPrevious: dto.offset > 0,
    hasNext: dto.offset + dto.data.length < dto.total,
    rankingVersion: "ranking" in dto && dto.ranking === API_V2_RANKING ? API_V2_RANKING : null,
  };
}
