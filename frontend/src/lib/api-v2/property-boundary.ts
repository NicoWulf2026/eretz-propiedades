import "server-only";

import type { CatalogProperty } from "@/domain/catalog-property";
import type { CatalogSearchQuery } from "@/domain/catalog-search";
import { assessLocationConfidence, hasValidArgentinaCoordinates } from "@/lib/geo-confidence";
import { cleanText, normalizeCurrency, normalizeOperation, normalizePropertyType } from "@/lib/property-mapper";
import { clusterMapMarkers } from "@/lib/map-points";
import type { MapSearchResponse, MapViewport, Property, PropertyFilters, PropertySearchResult, PropertySummary } from "@/types/property";
import { getApiV2Agency, getApiV2Map, getApiV2Property, searchApiV2Properties } from "./client";
import type { ApiV2ErrorKind } from "./errors";

export type PublicReadFailure = { kind: ApiV2ErrorKind; message: string };

export function validateApiV2ExplorerParams(params: URLSearchParams): string | null {
  const allowed = {
    operacion: ["venta", "alquiler", "temporario"],
    tipo: ["departamento", "casa", "terreno", "local", "cochera", "oficina", "galpon"],
    moneda: ["USD", "ARS"],
    orden: ["relevance", "price_asc", "price_desc"],
  } as const;
  const scalarParams = ["q", "operacion", "tipo", "provincia", "ciudad", "barrio", "area_id", "area_nivel", "area_nombre", "moneda", "precio_min", "precio_max", "ambientes", "dormitorios", "banos", "superficie", "orden", "pagina"];
  const duplicated = scalarParams.find((key) => params.getAll(key).length > 1);
  if (duplicated) return `El parámetro ${duplicated} no puede repetirse.`;
  for (const [key, values] of Object.entries(allowed)) {
    const value = params.get(key);
    if (value && !(values as readonly string[]).includes(key === "moneda" ? value.toUpperCase() : value)) return `El parámetro ${key} no es válido.`;
  }
  const page = params.get("pagina");
  if (page && (!/^\d+$/.test(page) || Number(page) < 1)) return "La página solicitada no es válida.";
  for (const key of ["precio_min", "precio_max", "ambientes", "dormitorios", "banos", "superficie"]) {
    const value = params.get(key);
    if (value && (!/^\d+(?:\.\d+)?$/.test(value) || Number(value) < 0)) return `El parámetro ${key} no es válido.`;
  }
  const sort = params.get("orden");
  if ((sort === "price_asc" || sort === "price_desc" || params.has("precio_min") || params.has("precio_max")) && !params.get("moneda")) {
    return "Los rangos y el orden por precio requieren moneda.";
  }
  return null;
}

export function unsupportedExplorerFilters(filters: PropertyFilters): string[] {
  const unsupported: string[] = [];
  if (filters.locations.length > 1) unsupported.push("ubicaciones múltiples");
  if (filters.zones.length || filters.viewport) unsupported.push("zona dibujada");
  if (filters.minGarages !== null) unsupported.push("cocheras");
  if (filters.maxArea !== null || filters.minCoveredArea !== null || filters.minLandArea !== null) unsupported.push("superficies avanzadas");
  if (filters.maxExpenses !== null || filters.maxAge !== null) unsupported.push("expensas/antigüedad");
  if (filters.publisher || filters.recentDays !== null) unsupported.push("publicador/fecha");
  if (filters.hasImages || filters.priceMode || filters.hasLocation || filters.hasVideo || filters.hasFloorPlan || filters.mortgageState) unsupported.push("disponibilidad avanzada");
  if (filters.near) unsupported.push("cercanía");
  return unsupported;
}

export function propertyFiltersToCatalogQuery(filters: PropertyFilters): CatalogSearchQuery {
  return {
    text: [filters.q, filters.locations[0] ?? ""].filter(Boolean).join(" "),
    operation: filters.operation === "temporario" ? "alquiler_temporario" : filters.operation === "venta" || filters.operation === "alquiler" ? filters.operation : null,
    propertyType: ["departamento", "casa", "terreno", "local", "cochera", "oficina", "galpon"].includes(filters.propertyType)
      ? filters.propertyType as CatalogSearchQuery["propertyType"] : null,
    area: filters.selectedArea ? { level: filters.selectedArea.level, name: filters.selectedArea.name } : null,
    locality: filters.selectedArea ? null : filters.city || null,
    neighborhood: filters.neighborhood || null,
    agencyId: null,
    minPrice: filters.minPrice,
    maxPrice: filters.maxPrice,
    currency: filters.currency || null,
    rooms: filters.minRooms,
    bedrooms: filters.minBedrooms,
    bathrooms: filters.minBathrooms,
    minSurface: filters.minArea,
    maxSurface: null,
    sort: filters.sort === "price_asc" || filters.sort === "price_desc"
      ? { kind: "user_selected", value: filters.sort }
      : { kind: "technical_relevance" },
    pagination: { page: filters.page, pageSize: 24 },
  };
}

export function catalogPropertyToSummary(property: CatalogProperty): PropertySummary {
  const hasCoordinates = hasValidArgentinaCoordinates(property.latitude, property.longitude);
  const locality = cleanText(property.geography.locality.name) || null;
  const municipality = cleanText(property.geography.municipality.name) || null;
  const department = cleanText(property.geography.department.name) || null;
  const province = cleanText(property.geography.province.name) || null;
  const neighborhood = cleanText(property.geography.neighborhood.name) || null;
  const images = [...property.images];
  return {
    id: property.id,
    agencyId: property.agencyId,
    publisher: null,
    title: cleanText(property.title) || "Propiedad sin título",
    description: cleanText(property.description) || null,
    price: property.price.amount,
    currency: normalizeCurrency(property.price.rawCurrency),
    propertyType: normalizePropertyType(property.rawPropertyType),
    rawPropertyType: property.rawPropertyType,
    operation: normalizeOperation(property.rawOperation),
    rooms: property.rooms,
    bedrooms: property.bedrooms,
    bathrooms: property.bathrooms,
    garages: null,
    toilettes: null,
    totalArea: property.surfaces.total,
    coveredArea: property.surfaces.covered,
    landArea: null,
    expenses: null,
    expensesCurrency: null,
    address: null,
    neighborhood,
    city: locality,
    municipality,
    department,
    province,
    country: null,
    latitude: hasCoordinates ? property.latitude : null,
    longitude: hasCoordinates ? property.longitude : null,
    locationConfidence: assessLocationConfidence({ latitude: property.latitude, longitude: property.longitude, address: null, neighborhood, city: locality, province }).level,
    images,
    publishedAt: null,
    updatedAt: null,
    status: "desconocida",
    mortgageEligible: null,
    amenities: [],
  };
}

export function catalogPropertyToProperty(property: CatalogProperty): Property {
  const summary = catalogPropertyToSummary(property);
  return {
    ...summary,
    sourceUrl: property.sourceUrl,
    priceUsd: summary.currency === "USD" ? summary.price : null,
    priceArs: summary.currency === "ARS" ? summary.price : null,
    age: null,
    floor: null,
    videoUrl: null,
    floorPlanUrl: null,
    agentName: null,
    agentPhone: null,
    createdAt: null,
    quality: {
      hasValidTitle: Boolean(cleanText(property.title)),
      hasDescription: Boolean(cleanText(property.description)),
      hasPrice: property.price.amount !== null,
      hasCurrency: summary.currency !== null,
      hasLocation: Boolean(summary.neighborhood || summary.city || summary.municipality || summary.department || summary.province),
      hasCoordinates: summary.latitude !== null && summary.longitude !== null,
      hasImages: summary.images.length > 0,
    },
  };
}

export async function getApiV2DetailForPublicId(id: string): Promise<{ status: "FOUND"; property: Property } | { status: "NOT_FOUND" } | { status: "UNAVAILABLE" }> {
  const response = await getApiV2Property(id);
  if (response.status === "FAILURE") {
    if (response.error.kind === "NOT_FOUND") return { status: "NOT_FOUND" };
    return { status: "UNAVAILABLE" };
  }
  const property = catalogPropertyToProperty(response.data);
  if (response.data.agencyId) {
    const agency = await getApiV2Agency(response.data.agencyId);
    if (agency.status !== "FAILURE") {
      property.publisher = {
        id: agency.data.agency_id,
        name: agency.data.name,
        phone: agency.data.contact.phone,
        email: agency.data.contact.email,
        website: agency.data.website,
        verified: null,
      };
    }
  }
  return { status: "FOUND", property };
}

export async function searchApiV2ForExplorer(filters: PropertyFilters): Promise<{ result: PropertySearchResult | null; failure: PublicReadFailure | null; windowExhausted: boolean }> {
  const unsupported = unsupportedExplorerFilters(filters);
  if (unsupported.length) return { result: null, failure: { kind: "BAD_REQUEST", message: `Filtros todavía no soportados por API v2: ${unsupported.join(", ")}` }, windowExhausted: false };
  const response = await searchApiV2Properties(propertyFiltersToCatalogQuery(filters));
  if (response.status === "FAILURE") return { result: null, failure: { kind: response.error.kind, message: response.error.message }, windowExhausted: false };
  const page = response.data;
  return {
    result: {
      properties: page.properties.map(catalogPropertyToSummary), count: page.total, totalCount: page.total, mapCount: null,
      page: page.page, pageSize: page.pageSize, hasNext: page.hasNext, hasPrevious: page.hasPrevious,
      nextCursor: page.hasNext ? "offset" : null, previousCursor: page.hasPrevious ? "offset" : null,
      source: "database", error: false, invalidCursor: false,
    },
    failure: null,
    windowExhausted: page.searchWindowExhausted,
  };
}

export async function searchApiV2MapForExplorer(filters: PropertyFilters, viewport: MapViewport): Promise<{ result: MapSearchResponse | null; failure: PublicReadFailure | null; totalMatches: number | null; viewportMatches: number | null }> {
  const query = propertyFiltersToCatalogQuery({ ...filters, viewport: null, zones: [] });
  const request = new URLSearchParams({ north: String(viewport.north), south: String(viewport.south), east: String(viewport.east), west: String(viewport.west), limit: "2000" });
  const searchRequest = new URLSearchParams();
  if (query.text) searchRequest.set("q", query.text);
  if (query.operation) searchRequest.set("operacion", query.operation);
  if (query.propertyType) searchRequest.set("tipo", query.propertyType);
  if (query.area) { searchRequest.set("nivel", query.area.level); searchRequest.set("area", query.area.name); }
  if (query.locality) searchRequest.set("localidad", query.locality);
  if (query.neighborhood) searchRequest.set("barrio", query.neighborhood);
  if (query.currency) searchRequest.set("moneda", query.currency);
  if (query.minPrice !== null) searchRequest.set("precio_min", String(query.minPrice));
  if (query.maxPrice !== null) searchRequest.set("precio_max", String(query.maxPrice));
  if (query.rooms !== null) searchRequest.set("ambientes", String(query.rooms));
  if (query.bedrooms !== null) searchRequest.set("dormitorios", String(query.bedrooms));
  if (query.bathrooms !== null) searchRequest.set("banos", String(query.bathrooms));
  if (query.minSurface !== null) searchRequest.set("superficie_min", String(query.minSurface));
  searchRequest.forEach((value, key) => request.set(key, value));
  const response = await getApiV2Map(request);
  if (response.status === "FAILURE") return { result: null, failure: { kind: response.error.kind, message: response.error.message }, totalMatches: null, viewportMatches: null };
  const markers = response.data.points.map((point) => ({
    kind: "property" as const, id: point.id, latitude: point.latitude, longitude: point.longitude,
    price: point.price, currency: normalizeCurrency(point.currency), propertyType: normalizePropertyType(point.propertyType),
    title: cleanText(point.title) || "Propiedad sin título", location: "Ubicación aproximada", locationConfidence: "approximate" as const,
  }));
  return {
    result: { points: clusterMapMarkers(markers, viewport.zoom), visibleCount: response.data.viewportMatches, scannedCount: response.data.returnedPoints, truncated: response.data.truncated },
    failure: null, totalMatches: response.data.totalMatches, viewportMatches: response.data.viewportMatches,
  };
}
