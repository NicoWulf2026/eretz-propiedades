import "server-only";

import postgres, { type Sql } from "postgres";
import { cleanText, mapSupabasePropertyToProperty, normalizeCurrency } from "@/lib/property-mapper";
import { propertyLocation } from "@/lib/property-presenter";
import { getPreviewQualityGate } from "@/lib/preview-quality-gate";
import { parsePropertyFilters } from "@/lib/property-query";
import type {
  MapSearchResponse,
  MapViewport,
  Property,
  PropertyFilters,
  PropertySearchResult,
  PropertySummary,
  PropertySort,
  SearchSuggestion,
  SupabaseProperty,
} from "@/types/property";

export const PROPERTY_PAGE_SIZE = 24;
const SCAN_BATCH_SIZE = 96;
const MAX_LIST_SCAN_BATCHES = 60;
const STATEMENT_TIMEOUT_MS = 30_000;
const QUERY_CACHE_TTL_MS = 300_000;
const DETAIL_CACHE_TTL_MS = 300_000;
const MAX_QUERY_CACHE_ENTRIES = 160;

type DbPropertyRow = SupabaseProperty & { __sort_value: string | number };
type MapCandidate = {
  id: string | number;
  titulo: string | null;
  precio: number | null;
  moneda: string | null;
  latitud: number;
  longitud: number;
  barrio: string | null;
  ciudad: string | null;
  provincia: string | null;
  __sort_value: string | number;
};
type CursorPayload = { version: 1; sort: PropertySort; value: string | number; id: string };
type TimedPromise<T> = { expiresAt: number; value: Promise<T> };

let client: Sql | null = null;
const searchCache = new Map<string, TimedPromise<PropertySearchResult>>();
const detailCache = new Map<string, TimedPromise<Property | null>>();
const mapCache = new Map<string, TimedPromise<MapSearchResponse>>();
const suggestionCache = new Map<string, TimedPromise<SearchSuggestion[]>>();

function cachedQuery<T>(
  store: Map<string, TimedPromise<T>>,
  key: string,
  ttl: number,
  work: () => Promise<T>,
  isCacheable: (result: T) => boolean = () => true,
) {
  const now = Date.now();
  const existing = store.get(key);
  if (existing && existing.expiresAt > now) return existing.value;
  if (existing) store.delete(key);
  const value = work().then((result) => {
    if (!isCacheable(result) && store.get(key)?.value === value) store.delete(key);
    return result;
  }).catch((error) => {
    if (store.get(key)?.value === value) store.delete(key);
    throw error;
  });
  store.set(key, { expiresAt: now + ttl, value });
  if (store.size > MAX_QUERY_CACHE_ENTRIES) {
    const oldest = store.keys().next().value;
    if (oldest) store.delete(oldest);
  }
  return value;
}

function databaseUrl() {
  return process.env.SUPABASE_DATABASE_URL?.trim() || process.env.DATABASE_URL?.trim() || "";
}

function db() {
  const url = databaseUrl();
  if (!url) return null;
  if (!client) {
    client = postgres(url, {
      max: 4,
      idle_timeout: 20,
      connect_timeout: 10,
      prepare: false,
      ssl: "require",
      onnotice: () => undefined,
    });
  }
  return client;
}

async function readOnly<T>(work: (sql: Sql) => Promise<T>) {
  const sql = db();
  if (!sql) throw new Error("ERETZ database is not configured");
  return sql.begin(async (transaction) => {
    await transaction.unsafe("SET TRANSACTION READ ONLY");
    await transaction.unsafe(`SET LOCAL statement_timeout = '${STATEMENT_TIMEOUT_MS}ms'`);
    return work(transaction as unknown as Sql);
  }) as Promise<T>;
}

const projection = `
  p.id, p.inmobiliaria_id, p.url, p.titulo, p.descripcion, p.precio, p.moneda,
  p.precio_usd, p.precio_ars, p.expensas, p.expensas_moneda, p.tipo_propiedad,
  p.operacion, p.ambientes, p.dormitorios, p.banos, p.toilettes, p.cocheras,
  p.antiguedad, p.piso, p.superficie_total, p.superficie_cubierta,
  p.superficie_terreno, p.direccion, p.barrio, p.ciudad, p.provincia, p.pais,
  p.latitud, p.longitud, p.imagenes, p.video_url, p.plano_url, p.amenities,
  p.agente_nombre, p.agente_telefono, p.fuente_extraccion, p.cms_origen,
  p.fecha_publicacion, p.estado, p.created_at, p.updated_at, p.apto_credito,
  i.nombre AS publisher_name,
  COALESCE(NULLIF(i.telefono_principal, ''), NULLIF(i.telefono, '')) AS publisher_phone,
  i.email_principal AS publisher_email,
  i.web AS publisher_website,
  i.verificada AS publisher_verified`;

const summaryProjection = `
  p.id, p.inmobiliaria_id, NULL::text AS url, p.titulo, NULL::text AS descripcion,
  p.precio, p.moneda, NULL::numeric AS precio_usd, NULL::numeric AS precio_ars,
  NULL::numeric AS expensas, NULL::text AS expensas_moneda, p.tipo_propiedad,
  p.operacion, p.ambientes, p.dormitorios, p.banos, NULL::integer AS toilettes,
  p.cocheras, NULL::integer AS antiguedad, NULL::text AS piso, p.superficie_total,
  p.superficie_cubierta, NULL::numeric AS superficie_terreno, p.direccion, p.barrio,
  p.ciudad, p.provincia, p.pais, p.latitud, p.longitud,
  CASE WHEN cardinality(p.imagenes) > 0 THEN p.imagenes[1:1] ELSE ARRAY[]::text[] END AS imagenes,
  NULL::text AS video_url, NULL::text AS plano_url, ARRAY[]::text[] AS amenities,
  p.agente_nombre, p.agente_telefono, NULL::text AS fuente_extraccion,
  NULL::text AS cms_origen, p.fecha_publicacion, p.estado, p.created_at, p.updated_at,
  p.apto_credito, i.nombre AS publisher_name,
  COALESCE(NULLIF(i.telefono_principal, ''), NULLIF(i.telefono, '')) AS publisher_phone,
  i.email_principal AS publisher_email, i.web AS publisher_website,
  i.verificada AS publisher_verified`;

function toSummary(property: Property): PropertySummary {
  return {
    id: property.id,
    agencyId: property.agencyId,
    publisher: property.publisher,
    title: property.title,
    price: property.price,
    currency: property.currency,
    propertyType: property.propertyType,
    rawPropertyType: property.rawPropertyType,
    operation: property.operation,
    rooms: property.rooms,
    bedrooms: property.bedrooms,
    bathrooms: property.bathrooms,
    garages: property.garages,
    totalArea: property.totalArea,
    coveredArea: property.coveredArea,
    address: property.address,
    neighborhood: property.neighborhood,
    city: property.city,
    province: property.province,
    country: property.country,
    latitude: property.latitude,
    longitude: property.longitude,
    images: property.images.slice(0, 1),
    publishedAt: property.publishedAt,
    updatedAt: property.updatedAt,
    status: property.status,
    mortgageEligible: property.mortgageEligible,
  };
}

function normalizeSearch(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function addParam(params: unknown[], value: unknown) {
  params.push(value);
  return `$${params.length}`;
}

function buildWhere(filters: PropertyFilters, extra?: MapViewport) {
  const params: unknown[] = [];
  const conditions = ["p.estado = 'activa'"];
  const add = (condition: string, value: unknown) => conditions.push(condition.replace("?", addParam(params, value)));
  if (filters.q) {
    const query = `%${normalizeSearch(filters.q)}%`;
    add(`translate(lower(concat_ws(' ', p.titulo, p.provincia, p.ciudad, p.barrio, p.direccion, i.nombre, p.tipo_propiedad)), 'áéíóúüñ', 'aeiouun') LIKE ?`, query);
  }
  if (filters.operation) add("p.operacion = ?", filters.operation === "temporario" ? "alquiler_temporario" : filters.operation);
  if (filters.propertyType) add("lower(p.tipo_propiedad) LIKE ?", `%${filters.propertyType}%`);
  if (filters.province) add("p.provincia ILIKE ?", `%${filters.province}%`);
  if (filters.city) add("p.ciudad ILIKE ?", `%${filters.city}%`);
  if (filters.neighborhood) add("p.barrio ILIKE ?", `%${filters.neighborhood}%`);
  if (filters.currency) add("upper(p.moneda) = ?", filters.currency);
  if (filters.minPrice !== null) add("p.precio >= ?", filters.minPrice);
  if (filters.maxPrice !== null) add("p.precio <= ?", filters.maxPrice);
  if (filters.minRooms !== null) add("p.ambientes >= ?", filters.minRooms);
  if (filters.minBedrooms !== null) add("p.dormitorios >= ?", filters.minBedrooms);
  if (filters.minBathrooms !== null) add("p.banos >= ?", filters.minBathrooms);
  if (filters.minGarages !== null) add("p.cocheras >= ?", filters.minGarages);
  if (filters.minArea !== null) add("p.superficie_total >= ?", filters.minArea);
  if (filters.maxArea !== null) add("p.superficie_total <= ?", filters.maxArea);
  if (filters.minCoveredArea !== null) add("p.superficie_cubierta >= ?", filters.minCoveredArea);
  if (filters.minLandArea !== null) add("p.superficie_terreno >= ?", filters.minLandArea);
  if (filters.maxExpenses !== null) add("p.expensas <= ?", filters.maxExpenses);
  if (filters.maxAge !== null) add("p.antiguedad <= ?", filters.maxAge);
  if (filters.publisher) {
    const publisherValue = `%${filters.publisher}%`;
    const first = addParam(params, publisherValue);
    const second = addParam(params, publisherValue);
    conditions.push(`(i.nombre ILIKE ${first} OR p.agente_nombre ILIKE ${second})`);
  }
  if (filters.recentDays !== null) add("COALESCE(p.fecha_publicacion, p.updated_at, p.created_at) >= now() - (? * interval '1 day')", filters.recentDays);
  if (filters.hasImages) conditions.push("cardinality(p.imagenes) > 0");
  if (filters.hasPrice) conditions.push("p.precio > 0 AND p.moneda IS NOT NULL");
  if (filters.hasLocation) conditions.push("p.latitud IS NOT NULL AND p.longitud IS NOT NULL");
  if (filters.hasVideo) conditions.push("NULLIF(p.video_url, '') IS NOT NULL");
  if (filters.hasFloorPlan) conditions.push("NULLIF(p.plano_url, '') IS NOT NULL");
  if (filters.mortgageEligible) conditions.push("p.apto_credito IS TRUE");
  if (extra) {
    add("p.latitud <= ?", extra.north);
    add("p.latitud >= ?", extra.south);
    add("p.longitud <= ?", extra.east);
    add("p.longitud >= ?", extra.west);
  }
  return { where: conditions.join(" AND "), params };
}

function sortSpec(sort: PropertySort) {
  switch (sort) {
    case "price_asc": return { expression: "COALESCE(p.precio, 1e30)", ascending: true };
    case "price_desc": return { expression: "COALESCE(p.precio, 0)", ascending: false };
    case "area_desc": return { expression: "COALESCE(p.superficie_total, p.superficie_cubierta, 0)", ascending: false };
    case "rooms_desc": return { expression: "COALESCE(p.ambientes, 0)", ascending: false };
    case "price_m2_asc": return { expression: "COALESCE(p.precio / NULLIF(p.superficie_total, 0), 1e30)", ascending: true };
    // The primary key is monotonic with ingestion and indexed. It is the neutral,
    // stable preview recency signal; publication date remains available as a real filter.
    default: return { expression: "p.id", ascending: false };
  }
}

function decodeCursor(cursor: string, sort: PropertySort): CursorPayload | null {
  if (!cursor) return null;
  try {
    const value = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8")) as Partial<CursorPayload>;
    if (value.version !== 1 || value.sort !== sort || !/^\d+$/.test(String(value.id ?? ""))) return null;
    if (typeof value.value !== "number" && typeof value.value !== "string") return null;
    return value as CursorPayload;
  } catch {
    return null;
  }
}

function encodeCursor(row: DbPropertyRow, sort: PropertySort) {
  return Buffer.from(JSON.stringify({ version: 1, sort, value: row.__sort_value, id: String(row.id) } satisfies CursorPayload)).toString("base64url");
}

function buildCursorClause(
  params: unknown[],
  cursor: CursorPayload | null,
  expression: string,
  ascending: boolean,
  direction: "next" | "prev",
) {
  if (!cursor) return "";
  const reverse = direction === "prev";
  const operator = ascending !== reverse ? ">" : "<";
  const valueParam = addParam(params, cursor.value);
  const idParam = addParam(params, Number(cursor.id));
  return ` AND (${expression} ${operator} ${valueParam} OR (${expression} = ${valueParam} AND p.id ${operator} ${idParam}))`;
}

async function queryBatch(filters: PropertyFilters, limit: number, cursor: CursorPayload | null, viewport?: MapViewport) {
  const { where, params } = buildWhere(filters, viewport);
  const sort = sortSpec(filters.sort);
  const cursorClause = buildCursorClause(params, cursor, sort.expression, sort.ascending, filters.direction);
  const reverse = filters.direction === "prev";
  const order = sort.ascending !== reverse ? "ASC" : "DESC";
  const limitParam = addParam(params, limit);
  const statement = `SELECT ${summaryProjection}, ${sort.expression} AS __sort_value
    FROM public.propiedades p
    LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
    WHERE ${where}${cursorClause}
    ORDER BY ${sort.expression} ${order}, p.id ${order}
    LIMIT ${limitParam}`;
  return readOnly(async (sql) => sql.unsafe<DbPropertyRow[]>(statement, params as never[]));
}

async function queryMapBatch(filters: PropertyFilters, limit: number, cursor: CursorPayload | null, viewport: MapViewport) {
  const { where, params } = buildWhere(filters, viewport);
  const sort = sortSpec("recent");
  const cursorClause = buildCursorClause(params, cursor, sort.expression, false, "next");
  const limitParam = addParam(params, limit);
  const statement = `SELECT p.id, p.titulo, p.precio, p.moneda, p.latitud, p.longitud,
      p.barrio, p.ciudad, p.provincia, ${sort.expression} AS __sort_value
    FROM public.propiedades p
    LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
    WHERE ${where}${cursorClause}
    ORDER BY ${sort.expression} DESC, p.id DESC
    LIMIT ${limitParam}`;
  return readOnly(async (sql) => sql.unsafe<MapCandidate[]>(statement, params as never[]));
}

function emptyResult(filters: PropertyFilters, source: PropertySearchResult["source"], error: boolean, invalidCursor = false): PropertySearchResult {
  return {
    properties: [], count: null, page: filters.page, pageSize: PROPERTY_PAGE_SIZE,
    hasNext: false, hasPrevious: filters.page > 1, nextCursor: null, previousCursor: null,
    source, error, invalidCursor,
  };
}

function hasFilters(filters: PropertyFilters) {
  return Boolean(
    filters.q || filters.operation || filters.propertyType || filters.province || filters.city ||
    filters.neighborhood || filters.publisher || filters.currency || filters.minPrice || filters.maxPrice ||
    filters.minRooms || filters.minBedrooms || filters.minBathrooms || filters.minGarages || filters.minArea ||
    filters.maxArea || filters.minCoveredArea || filters.minLandArea || filters.maxExpenses || filters.maxAge ||
    filters.recentDays || filters.hasImages || filters.hasPrice || filters.hasLocation || filters.hasVideo ||
    filters.hasFloorPlan || filters.mortgageEligible
  );
}

async function searchPropertiesUncached(filters: PropertyFilters): Promise<PropertySearchResult> {
  if (!databaseUrl()) return emptyResult(filters, "unconfigured", true);
  const gate = getPreviewQualityGate();
  if (!gate.enabled) return emptyResult(filters, "unconfigured", true);
  const decoded = decodeCursor(filters.cursor, filters.sort);
  if (filters.cursor && !decoded) return emptyResult(filters, "database", false, true);
  try {
    const accepted: Array<{ row: DbPropertyRow; property: PropertySummary }> = [];
    let scanCursor = decoded;
    for (let batch = 0; batch < MAX_LIST_SCAN_BATCHES && accepted.length <= PROPERTY_PAGE_SIZE; batch += 1) {
      const rows = await queryBatch(filters, SCAN_BATCH_SIZE, scanCursor);
      for (const row of rows) {
        if (gate.isVisible(row.id)) accepted.push({ row, property: toSummary(mapSupabasePropertyToProperty(row)) });
        if (accepted.length > PROPERTY_PAGE_SIZE) break;
      }
      if (rows.length < SCAN_BATCH_SIZE) break;
      const last = rows.at(-1);
      if (!last) break;
      scanCursor = { version: 1, sort: filters.sort, value: last.__sort_value, id: String(last.id) };
    }
    const hasExtra = accepted.length > PROPERTY_PAGE_SIZE;
    let pageItems = accepted.slice(0, PROPERTY_PAGE_SIZE);
    if (filters.direction === "prev") pageItems = pageItems.reverse();
    const first = pageItems[0];
    const last = pageItems.at(-1);
    return {
      properties: pageItems.map((item) => item.property),
      count: hasFilters(filters) ? null : gate.visibleCount,
      page: filters.page,
      pageSize: PROPERTY_PAGE_SIZE,
      hasNext: filters.direction === "prev" ? filters.page > 1 : hasExtra,
      hasPrevious: filters.direction === "prev" ? hasExtra : filters.page > 1,
      nextCursor: last ? encodeCursor(last.row, filters.sort) : null,
      previousCursor: first ? encodeCursor(first.row, filters.sort) : null,
      source: "database",
      error: false,
      invalidCursor: false,
    };
  } catch (error) {
    console.error("ERETZ public property search failed", error instanceof Error ? error.message : "unknown error");
    return emptyResult(filters, "error", true);
  }
}

export function searchProperties(filters: PropertyFilters): Promise<PropertySearchResult> {
  return cachedQuery(
    searchCache,
    JSON.stringify(filters),
    QUERY_CACHE_TTL_MS,
    () => searchPropertiesUncached(filters),
    (result) => !result.error,
  );
}

async function getPropertyByIdUncached(id: string): Promise<Property | null> {
  if (!databaseUrl() || !/^\d+$/.test(id)) return null;
  const gate = getPreviewQualityGate();
  if (!gate.enabled || !gate.isVisible(id)) return null;
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(`SELECT ${projection}, p.id AS __sort_value
      FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
      WHERE p.estado = 'activa' AND p.id = $1 LIMIT 1`, [Number(id)]));
    return rows[0] ? mapSupabasePropertyToProperty(rows[0]) : null;
  } catch {
    return null;
  }
}

export function getPropertyById(id: string): Promise<Property | null> {
  return cachedQuery(detailCache, id, DETAIL_CACHE_TTL_MS, () => getPropertyByIdUncached(id));
}

export async function getRelatedProperties(property: Property): Promise<PropertySummary[]> {
  const filters = parsePropertyFilters({
    operacion: property.operation,
    tipo: property.propertyType,
    provincia: property.province ?? undefined,
  });
  const result = await searchProperties(filters);
  return result.properties.filter((item) => item.id !== property.id).slice(0, 4);
}

function clusterMapProperties(valid: MapCandidate[], zoom: number): MapSearchResponse["points"] {
  const marker = (property: MapCandidate) => ({
    kind: "property" as const,
    id: String(property.id),
    latitude: Number(property.latitud),
    longitude: Number(property.longitud),
    price: Number(property.precio) > 0 ? Number(property.precio) : null,
    currency: normalizeCurrency(property.moneda),
    title: cleanText(property.titulo) || "Propiedad sin título",
    location: propertyLocation({
      neighborhood: cleanText(property.barrio) || null,
      city: cleanText(property.ciudad) || null,
      province: cleanText(property.provincia) || null,
    }),
  });
  if (zoom >= 12) {
    return valid.slice(0, 800).map(marker);
  }
  const cell = Math.max(0.008, (zoom <= 6 ? 128 : 48) / (2 ** zoom));
  const groups = new Map<string, { latitude: number; longitude: number; count: number; first: MapCandidate }>();
  for (const property of valid) {
    const latitude = Number(property.latitud);
    const longitude = Number(property.longitud);
    const key = `${Math.floor(latitude / cell)}:${Math.floor(longitude / cell)}`;
    const group = groups.get(key);
    if (group) {
      group.latitude += latitude;
      group.longitude += longitude;
      group.count += 1;
    } else {
      groups.set(key, { latitude, longitude, count: 1, first: property });
    }
  }
  return [...groups.entries()].slice(0, 800).map(([key, group]) => group.count === 1 ? marker(group.first) : {
    kind: "cluster" as const,
    id: `cluster-${key}`,
    latitude: group.latitude / group.count,
    longitude: group.longitude / group.count,
    count: group.count,
  });
}

async function searchMapUncached(filters: PropertyFilters, viewport: MapViewport): Promise<MapSearchResponse> {
  const gate = getPreviewQualityGate();
  if (!databaseUrl() || !gate.enabled) return { points: [], visibleCount: 0, scannedCount: 0, truncated: false };
  const mapFilters = { ...filters, direction: "next" as const, cursor: "", sort: "recent" as const };
  const target = viewport.zoom >= 12 ? 800 : viewport.zoom >= 9 ? 1_600 : 2_000;
  const scanBatchSize = Math.ceil(target / 0.68);
  const accepted: MapCandidate[] = [];
  let scanCursor: CursorPayload | null = null;
  let scannedCount = 0;
  let truncated = false;
  for (let batch = 0; batch < 2 && accepted.length < target; batch += 1) {
    const rows = await queryMapBatch(mapFilters, scanBatchSize, scanCursor, viewport);
    scannedCount += rows.length;
    for (const row of rows) {
      if (gate.isVisible(row.id)) accepted.push(row);
      if (accepted.length >= target) {
        truncated = true;
        break;
      }
    }
    if (rows.length < scanBatchSize) break;
    const last = rows.at(-1);
    if (!last) break;
    scanCursor = { version: 1, sort: "recent", value: last.__sort_value, id: String(last.id) };
    if (batch === 1) truncated = true;
  }
  return {
    points: clusterMapProperties(accepted, viewport.zoom),
    visibleCount: accepted.length,
    scannedCount,
    truncated,
  };
}

export function searchMap(filters: PropertyFilters, viewport: MapViewport): Promise<MapSearchResponse> {
  return cachedQuery(mapCache, JSON.stringify([filters, viewport]), QUERY_CACHE_TTL_MS, () => searchMapUncached(filters, viewport));
}

async function searchSuggestionsUncached(query: string): Promise<SearchSuggestion[]> {
  const q = query.trim().slice(0, 60);
  if (q.length < 2) return [];
  const filters = parsePropertyFilters({ q });
  const gate = getPreviewQualityGate();
  if (!databaseUrl() || !gate.enabled) return [];
  const rows = await queryBatch(filters, 300, null);
  const suggestions = new Map<string, SearchSuggestion>();
  const add = (category: SearchSuggestion["category"], value: string | null | undefined) => {
    const label = value?.trim();
    if (!label) return;
    const key = `${category}:${normalizeSearch(label)}`;
    if (!suggestions.has(key)) suggestions.set(key, { id: key, label, category, query: label });
  };
  for (const row of rows) {
    if (!gate.isVisible(row.id)) continue;
    add("provincia", row.provincia);
    add("ciudad", row.ciudad);
    add("barrio", row.barrio);
    add("dirección", row.direccion);
    add("inmobiliaria", row.publisher_name);
    add("tipo", row.tipo_propiedad);
    if (suggestions.size >= 12) break;
  }
  return [...suggestions.values()].slice(0, 12);
}

export function searchSuggestions(query: string): Promise<SearchSuggestion[]> {
  const key = normalizeSearch(query.trim().slice(0, 60));
  return cachedQuery(suggestionCache, key, DETAIL_CACHE_TTL_MS, () => searchSuggestionsUncached(query));
}

export async function getHomeInventory() {
  const result = await searchProperties(parsePropertyFilters({}));
  return { count: result.count ?? 0, recent: result.properties.slice(0, 6), error: result.error };
}
