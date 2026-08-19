import "server-only";

import postgres, { type Sql } from "postgres";
import { cleanText, mapSupabasePropertyToProperty, normalizeCurrency } from "@/lib/property-mapper";
import { assessLocationConfidence, hasValidArgentinaCoordinates, type GeoPointStats } from "@/lib/geo-confidence";
import { propertyLocation } from "@/lib/property-presenter";
import { getPreviewQualityGate } from "@/lib/preview-quality-gate";
import { parsePropertyFilters } from "@/lib/property-query";
import { addParam, buildCursorClause, buildWhere, normalizeSearch, sortSpec, type CursorPayload } from "@/lib/property-sql";
import { entitySlug, slugify } from "@/lib/slug";
import type {
  AgentProfile,
  AgentSummary,
  MapSearchResponse,
  MapViewport,
  Property,
  PropertyFilters,
  PropertySearchResult,
  PropertySummary,
  PropertySort,
  LocationConfidence,
  RealEstateProfile,
  RealEstateSummary,
  SearchSuggestion,
  SupabaseProperty,
} from "@/types/property";

export const PROPERTY_PAGE_SIZE = 24;
const SCAN_BATCH_SIZE = 96;
const MAX_LIST_SCAN_BATCHES = 3000; // Increased to allow skipping large blocks of excluded properties without truncating pagination
const QUERY_CACHE_TTL_MS = 300_000;
const DETAIL_CACHE_TTL_MS = 300_000;
const MAX_QUERY_CACHE_ENTRIES = 160;

type DbPropertyRow = SupabaseProperty & { __sort_value: string | number };
type MapCandidate = {
  id: string | number;
  inmobiliaria_id: string | number | null;
  titulo: string | null;
  precio: number | null;
  moneda: string | null;
  latitud: number;
  longitud: number;
  direccion: string | null;
  barrio: string | null;
  ciudad: string | null;
  provincia: string | null;
  __sort_value: string | number;
};
type ClassifiedMapCandidate = MapCandidate & { locationConfidence: Exclude<LocationConfidence, "none"> };
type TimedPromise<T> = { expiresAt: number; value: Promise<T> };
// `failed` separa "la consulta no devolvió nada" de "la consulta no se pudo hacer".
export type DirectoryResult<T> = { items: T[]; failed: boolean };

let client: Sql | null = null;
const searchCache = new Map<string, TimedPromise<PropertySearchResult>>();
const detailCache = new Map<string, TimedPromise<Property | null>>();
const mapCache = new Map<string, TimedPromise<MapSearchResponse>>();
const suggestionCache = new Map<string, TimedPromise<SearchSuggestion[]>>();
const countsCache = new Map<string, TimedPromise<{ count: number; mapCount: number }>>();
const directoryCache = new Map<string, TimedPromise<RealEstateSummary[]>>();
const agentCache = new Map<string, TimedPromise<AgentSummary[]>>();
const pointStatsCache = new Map<string, { expiresAt: number; value: GeoPointStats }>();
const POINT_STATS_CACHE_LIMIT = 4_000;

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
      // Vercel can create several function instances. Keep the per-instance pool
      // deliberately small and use Supabase's transaction pooler in Preview.
      max: 2,
      idle_timeout: 20,
      connect_timeout: 10,
      max_lifetime: 300,
      prepare: false,
      ssl: "require",
      // Keep session startup pooler-safe. Read-only and timeout defaults live on
      // the dedicated role; every application operation also opens an explicit
      // READ ONLY transaction below.
      connection: {
        application_name: "eretz-preview-readonly",
      },
      onnotice: () => undefined,
    });
  }
  return client;
}

function isRetryableConnectionError(error: unknown) {
  const code = typeof error === "object" && error !== null && "code" in error
    ? String((error as { code?: unknown }).code ?? "")
    : "";
  return ["CONNECTION_CLOSED", "CONNECT_TIMEOUT", "ECONNRESET", "ETIMEDOUT", "57P01", "57P02", "57P03"].includes(code);
}

async function readOnly<T>(work: (sql: Sql) => Promise<T>) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const sql = db();
    if (!sql) throw new Error("ERETZ database is not configured");
    try {
      return await sql.begin("read only", async (transaction) => work(transaction as unknown as Sql));
    } catch (error) {
      if (attempt > 0 || !isRetryableConnectionError(error)) throw error;
      if (client === sql) client = null;
      await sql.end({ timeout: 0 }).catch(() => undefined);
    }
  }
  throw new Error("ERETZ database connection could not be recovered");
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
    locationConfidence: property.locationConfidence,
    images: property.images.slice(0, 1),
    publishedAt: property.publishedAt,
    updatedAt: property.updatedAt,
    status: property.status,
    mortgageEligible: property.mortgageEligible,
    // Recorte para la variante "completa" de la tarjeta; datos reales condicionales.
    description: property.description ? property.description.slice(0, 220) : null,
    amenities: property.amenities.slice(0, 6),
  };
}

function coordinateKey(latitude: unknown, longitude: unknown) {
  return `${Number(latitude)}:${Number(longitude)}`;
}

async function getPointStats(
  rows: Array<{ latitud: number | null; longitud: number | null }>,
): Promise<Map<string, GeoPointStats>> {
  const now = Date.now();
  const result = new Map<string, GeoPointStats>();
  const missing = new Map<string, { latitude: number; longitude: number }>();
  for (const row of rows) {
    if (!hasValidArgentinaCoordinates(row.latitud, row.longitud)) continue;
    const key = coordinateKey(row.latitud, row.longitud);
    const cached = pointStatsCache.get(key);
    if (cached && cached.expiresAt > now) result.set(key, cached.value);
    else missing.set(key, { latitude: Number(row.latitud), longitude: Number(row.longitud) });
  }
  if (missing.size > 0) {
    const targets = [...missing.values()];
    const statsRows = await readOnly((sql) => sql.unsafe<Array<{
      latitud: number;
      longitud: number;
      point_properties: number;
      point_addresses: number;
      point_cities: number;
      point_provinces: number;
      point_agencies: number;
    }>>(`WITH targets AS MATERIALIZED (
        SELECT DISTINCT latitud, longitud
        FROM unnest($1::double precision[], $2::double precision[]) AS t(latitud, longitud)
      )
      SELECT t.latitud, t.longitud, count(p.id)::int AS point_properties,
        count(DISTINCT nullif(lower(btrim(p.direccion)), ''))::int AS point_addresses,
        count(DISTINCT nullif(lower(btrim(p.ciudad)), ''))::int AS point_cities,
        count(DISTINCT nullif(lower(btrim(p.provincia)), ''))::int AS point_provinces,
        count(DISTINCT p.inmobiliaria_id)::int AS point_agencies
      FROM targets t
      JOIN public.propiedades p ON p.latitud = t.latitud AND p.longitud = t.longitud
      GROUP BY t.latitud, t.longitud`, [
        targets.map((target) => target.latitude) as never,
        targets.map((target) => target.longitude) as never,
      ]));
    for (const row of statsRows) {
      const key = coordinateKey(row.latitud, row.longitud);
      const value: GeoPointStats = {
        propertyCount: Number(row.point_properties),
        addressCount: Number(row.point_addresses),
        cityCount: Number(row.point_cities),
        provinceCount: Number(row.point_provinces),
        agencyCount: Number(row.point_agencies),
      };
      result.set(key, value);
      pointStatsCache.set(key, { expiresAt: now + QUERY_CACHE_TTL_MS, value });
    }
    while (pointStatsCache.size > POINT_STATS_CACHE_LIMIT) {
      const oldest = pointStatsCache.keys().next().value;
      if (!oldest) break;
      pointStatsCache.delete(oldest);
    }
  }
  return result;
}

async function mapRowsToProperties<T extends SupabaseProperty>(rows: T[]) {
  const stats = await getPointStats(rows);
  return rows.map((row) => mapSupabasePropertyToProperty(
    row,
    stats.get(coordinateKey(row.latitud, row.longitud)),
  ));
}

async function mapRowsToSummaries<T extends SupabaseProperty>(rows: T[]) {
  return (await mapRowsToProperties(rows)).map(toSummary);
}

async function getSearchCountsUncached(filters: PropertyFilters): Promise<{ count: number; mapCount: number }> {
  const gate = await getPreviewQualityGate();
  if (!databaseUrl() || !gate.enabled) return { count: 0, mapCount: 0 };
  
  // Do not apply viewport to counts because we want the total for the search query!
  const { where, params } = buildWhere(filters, undefined);
  
  try {
    const publisherJoin = filters.q || filters.publisher ? "LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id" : "";
    const statement = `SELECT p.id, p.latitud, p.longitud FROM public.propiedades p ${publisherJoin} WHERE ${where}`;
    
    // We only need id, latitud, longitud. It should be fast even for many rows.
    const rows = await readOnly(async (sql) => sql.unsafe<{id: string | number, latitud: number | null, longitud: number | null}[]>(statement, params as never[]));
    
    let matching = 0;
    let map = 0;
    for (const row of rows) {
      if (gate.isVisible(String(row.id))) {
        matching++;
        if (row.latitud !== null && row.longitud !== null) {
          map++;
        }
      }
    }
    return { count: matching, mapCount: map };
  } catch (error) {
    console.error("ERETZ public property counts failed", error instanceof Error ? error.message : "unknown error");
    return { count: 0, mapCount: 0 };
  }
}

function getSearchCounts(filters: PropertyFilters): Promise<{ count: number; mapCount: number }> {
  // Discard pagination and viewport from cache key for counts
  const countFilters = { ...filters, cursor: "", page: 1, direction: "next" as const, viewport: null };
  return cachedQuery(
    countsCache,
    JSON.stringify(countFilters),
    QUERY_CACHE_TTL_MS,
    () => getSearchCountsUncached(countFilters)
  );
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

async function queryBatch(filters: PropertyFilters, limit: number, cursor: CursorPayload | null, viewport?: MapViewport) {
  const { where, params } = buildWhere(filters, viewport);
  const sort = sortSpec(filters.sort, filters.near);
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
  const publisherJoin = filters.q || filters.publisher
    ? "LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id"
    : "";
  const statement = `SELECT p.id, p.inmobiliaria_id, p.titulo, p.precio, p.moneda, p.latitud, p.longitud,
      p.direccion, p.barrio, p.ciudad, p.provincia, ${sort.expression} AS __sort_value
    FROM public.propiedades p
    ${publisherJoin}
    WHERE ${where}${cursorClause}
    ORDER BY ${sort.expression} DESC, p.id DESC
    LIMIT ${limitParam}`;
  return readOnly(async (sql) => sql.unsafe<MapCandidate[]>(statement, params as never[]));
}

function emptyResult(filters: PropertyFilters, source: PropertySearchResult["source"], error: boolean, invalidCursor = false): PropertySearchResult {
  return {
    properties: [], count: null, totalCount: null, mapCount: null, page: filters.page, pageSize: PROPERTY_PAGE_SIZE,
    hasNext: false, hasPrevious: filters.page > 1, nextCursor: null, previousCursor: null,
    source, error, invalidCursor,
  };
}

async function searchPropertiesUncached(filters: PropertyFilters): Promise<PropertySearchResult> {
  if (!databaseUrl()) return emptyResult(filters, "unconfigured", true);
  const gate = await getPreviewQualityGate();
  if (!gate.enabled) return emptyResult(filters, "unconfigured", true);
  const decoded = decodeCursor(filters.cursor, filters.sort);
  if (filters.cursor && !decoded) return emptyResult(filters, "database", false, true);
  try {
    const accepted: DbPropertyRow[] = [];
    let scanCursor = decoded;
    for (let batch = 0; batch < MAX_LIST_SCAN_BATCHES && accepted.length <= PROPERTY_PAGE_SIZE; batch += 1) {
      const rows = await queryBatch(filters, SCAN_BATCH_SIZE, scanCursor);
      for (const row of rows) {
        if (gate.isVisible(row.id)) accepted.push(row);
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
    const [counts, properties] = await Promise.all([
      getSearchCounts(filters),
      mapRowsToSummaries(pageItems),
    ]);
    
    return {
      properties,
      count: counts.count,
      totalCount: gate.visibleCount,
      mapCount: counts.mapCount,
      page: filters.page,
      pageSize: PROPERTY_PAGE_SIZE,
      hasNext: filters.direction === "prev" ? filters.page > 1 : hasExtra,
      hasPrevious: filters.direction === "prev" ? hasExtra : filters.page > 1,
      nextCursor: last ? encodeCursor(last, filters.sort) : null,
      previousCursor: first ? encodeCursor(first, filters.sort) : null,
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
  const gate = await getPreviewQualityGate();
  if (!gate.enabled || !gate.isVisible(id)) return null;
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(`SELECT ${projection}, p.id AS __sort_value
      FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
      WHERE p.id = $1 LIMIT 1`, [Number(id)]));
    return rows[0] ? (await mapRowsToProperties([rows[0]]))[0] : null;
  } catch {
    return null;
  }
}

export function getPropertyById(id: string): Promise<Property | null> {
  return cachedQuery(detailCache, id, DETAIL_CACHE_TTL_MS, () => getPropertyByIdUncached(id));
}

// Resumen de un conjunto de ids (favoritos, comparar, recientes). Server-only,
// capado, gate-filtrado y en el orden solicitado. Nunca filtra por estado: el
// Quality Gate es la autoridad de visibilidad.
export async function getPropertiesByIds(ids: string[]): Promise<PropertySummary[]> {
  if (!databaseUrl()) return [];
  const clean = Array.from(new Set(ids.map(String).filter((x) => /^\d+$/.test(x)))).slice(0, 60);
  if (clean.length === 0) return [];
  const gate = await getPreviewQualityGate();
  if (!gate.enabled) return [];
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(
      `SELECT ${summaryProjection}, p.id AS __sort_value
       FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
       WHERE p.id = ANY($1)`, [clean.map(Number) as never]));
    const visibleRows = rows.filter((row) => gate.isVisible(row.id));
    const summaries = await mapRowsToSummaries(visibleRows);
    const byId = new Map<string, PropertySummary>();
    for (const property of summaries) {
      byId.set(property.id, property);
    }
    return clean.map((id) => byId.get(id)).filter((x): x is PropertySummary => Boolean(x));
  } catch (error) {
    console.error("ERETZ getPropertiesByIds failed", error instanceof Error ? error.message : "unknown error");
    return [];
  }
}

// ---------------------------------------------------------- Directorio de inmobiliarias
type DirectoryRow = {
  id: string | number;
  nombre: string | null;
  web: string | null;
  verificada: boolean | null;
  total: number;
  ciudad: string | null;
  provincia: string | null;
  telefono?: string | null;
  email_principal?: string | null;
};

function toRealEstateSummary(row: DirectoryRow): RealEstateSummary {
  const id = String(row.id);
  const name = row.nombre?.trim() || `Inmobiliaria ${id}`;
  return {
    id,
    name,
    slug: entitySlug(id, name),
    verified: row.verificada === true,
    website: row.web?.trim() || null,
    city: row.ciudad?.trim() || null,
    province: row.provincia?.trim() || null,
    listingsCount: Number(row.total) || 0,
  };
}

// Nota: el conteo es directo de la base. Hoy el Quality Gate autoriza el catálogo
// completo (visibleCount == total), así que coincide con el conteo gate-visible;
// la ficha de cada inmobiliaria sí aplica el gate al listar sus propiedades.
const directoryCountUncached = async (query: string): Promise<RealEstateSummary[]> => {
  if (!databaseUrl()) return [];
  const clean = query.trim().slice(0, 60).replace(/[(),.*%]/g, " ").trim();
  const params: unknown[] = [];
  const nameFilter = clean ? `WHERE i.nombre ILIKE ${addParam(params, `%${clean}%`)}` : "";
  const limitParam = addParam(params, 60);
  try {
    const rows = await readOnly((sql) => sql.unsafe<DirectoryRow[]>(
      `SELECT i.id, i.nombre, i.web, i.verificada,
         count(p.id)::int AS total,
         mode() WITHIN GROUP (ORDER BY p.ciudad) AS ciudad,
         mode() WITHIN GROUP (ORDER BY p.provincia) AS provincia
       FROM public.inmobiliarias_main i
       JOIN public.propiedades p ON p.inmobiliaria_id = i.id
       ${nameFilter}
       GROUP BY i.id, i.nombre, i.web, i.verificada
       HAVING count(p.id) > 0
       ORDER BY count(p.id) DESC, i.nombre ASC
       LIMIT ${limitParam}`, params as never[]));
    return rows.map(toRealEstateSummary);
  } catch (error) {
    console.error("ERETZ getRealEstateDirectory failed", error instanceof Error ? error.message : "unknown error");
    throw error;
  }
};

// Devuelve `failed` para que el directorio pueda decir "no pudimos cargar" en
// vez de afirmar "no hay inmobiliarias", que es información falsa cuando lo que
// ocurrió fue un error de base.
export async function getRealEstateDirectory(query = ""): Promise<DirectoryResult<RealEstateSummary>> {
  try {
    const items = await cachedQuery(directoryCache, normalizeSearch(query.trim().slice(0, 60)), QUERY_CACHE_TTL_MS, () => directoryCountUncached(query));
    return { items, failed: false };
  } catch {
    return { items: [], failed: true };
  }
}

// Existencia de una inmobiliaria, para validar reclamos antes de persistirlos.
// A diferencia de getRealEstateById NO atrapa el error: quien llama necesita
// distinguir "no existe" (404) de "la base no respondió" (503). Devolver false
// ante un fallo transitorio marcaría como inexistente un perfil que sí existe.
export async function realEstateExists(id: string): Promise<boolean> {
  if (!/^\d+$/.test(id)) return false;
  if (!databaseUrl()) throw new Error("database is not configured");
  const rows = await readOnly((sql) => sql.unsafe<{ ok: number }[]>(
    "SELECT 1 AS ok FROM public.inmobiliarias_main WHERE id = $1 LIMIT 1", [Number(id)]));
  return rows.length > 0;
}

export async function getRealEstateById(id: string): Promise<RealEstateProfile | null> {
  if (!databaseUrl() || !/^\d+$/.test(id)) return null;
  try {
    const rows = await readOnly((sql) => sql.unsafe<DirectoryRow[]>(
      `SELECT i.id, i.nombre, i.web, i.verificada,
         COALESCE(NULLIF(i.telefono_principal, ''), NULLIF(i.telefono, '')) AS telefono,
         i.email_principal,
         count(p.id)::int AS total,
         mode() WITHIN GROUP (ORDER BY p.ciudad) AS ciudad,
         mode() WITHIN GROUP (ORDER BY p.provincia) AS provincia
       FROM public.inmobiliarias_main i
       LEFT JOIN public.propiedades p ON p.inmobiliaria_id = i.id
       WHERE i.id = $1
       GROUP BY i.id, i.nombre, i.web, i.verificada, i.telefono_principal, i.telefono, i.email_principal
       LIMIT 1`, [Number(id)]));
    const row = rows[0];
    if (!row) return null;
    return { ...toRealEstateSummary(row), phone: row.telefono?.trim() || null, email: row.email_principal?.trim() || null };
  } catch (error) {
    console.error("ERETZ getRealEstateById failed", error instanceof Error ? error.message : "unknown error");
    return null;
  }
}

// Propiedades de una inmobiliaria (gate-aplicado, orden por recencia neutral).
export async function getPropertiesByAgency(id: string, limit = 48): Promise<PropertySummary[]> {
  if (!databaseUrl() || !/^\d+$/.test(id)) return [];
  const gate = await getPreviewQualityGate();
  if (!gate.enabled) return [];
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(
      `SELECT ${summaryProjection}, (CASE WHEN p.estado = 'activa' THEN 1e10 ELSE 0 END + p.id) AS __sort_value
       FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
       WHERE p.inmobiliaria_id = $1
       ORDER BY __sort_value DESC
       LIMIT $2`, [Number(id), Math.min(Math.max(1, limit), 96)]));
    return mapRowsToSummaries(rows.filter((row) => gate.isVisible(row.id)));
  } catch (error) {
    console.error("ERETZ getPropertiesByAgency failed", error instanceof Error ? error.message : "unknown error");
    return [];
  }
}

// ---------------------------------------------------------- Directorio de agentes
// Los agentes no tienen entidad propia: se derivan de las publicaciones
// (agente_nombre). Sólo aparecen agentes con datos reales; si la columna está
// vacía, el directorio queda vacío (no se inventa contenido). El slug es el
// nombre normalizado (sin id, porque no existe uno estable).
type AgentRow = {
  nombre: string | null;
  total: number;
  ciudad: string | null;
  provincia: string | null;
  telefono?: string | null;
};

function toAgentSummary(row: AgentRow): AgentSummary {
  const name = row.nombre?.trim() || "Agente";
  return {
    slug: slugify(name),
    name,
    city: row.ciudad?.trim() || null,
    province: row.provincia?.trim() || null,
    listingsCount: Number(row.total) || 0,
  };
}

const agentDirectoryUncached = async (query: string, limit: number): Promise<AgentSummary[]> => {
  if (!databaseUrl()) return [];
  const clean = query.trim().slice(0, 60).replace(/[(),.*%]/g, " ").trim();
  const params: unknown[] = [];
  const nameFilter = clean ? `AND p.agente_nombre ILIKE ${addParam(params, `%${clean}%`)}` : "";
  const limitParam = addParam(params, limit);
  try {
    const rows = await readOnly((sql) => sql.unsafe<AgentRow[]>(
      `SELECT p.agente_nombre AS nombre, count(*)::int AS total,
         mode() WITHIN GROUP (ORDER BY p.ciudad) AS ciudad,
         mode() WITHIN GROUP (ORDER BY p.provincia) AS provincia,
         mode() WITHIN GROUP (ORDER BY p.agente_telefono) AS telefono
       FROM public.propiedades p
       WHERE p.agente_nombre IS NOT NULL AND btrim(p.agente_nombre) <> '' ${nameFilter}
       GROUP BY p.agente_nombre
       HAVING count(*) > 0
       ORDER BY count(*) DESC, p.agente_nombre ASC
       LIMIT ${limitParam}`, params as never[]));
    return rows.map(toAgentSummary);
  } catch (error) {
    console.error("ERETZ getAgentDirectory failed", error instanceof Error ? error.message : "unknown error");
    throw error;
  }
};

export async function getAgentDirectory(query = ""): Promise<DirectoryResult<AgentSummary>> {
  try {
    const items = await cachedQuery(agentCache, `dir:${normalizeSearch(query.trim().slice(0, 60))}`, QUERY_CACHE_TTL_MS, () => agentDirectoryUncached(query, 60));
    return { items, failed: false };
  } catch {
    return { items: [], failed: true };
  }
}

// Resuelve un slug de agente contra el conjunto real (sin id estable): agrega
// todos los agentes y encuentra el de slug coincidente. Devuelve su perfil.
export async function getAgentBySlug(slug: string): Promise<AgentProfile | null> {
  if (!databaseUrl() || !slug) return null;
  const rows = await agentDirectoryUncachedFull();
  const match = rows.find((row) => slugify(row.nombre?.trim() || "") === slug);
  if (!match) return null;
  const summary = toAgentSummary(match);
  return { ...summary, phone: match.telefono?.trim() || null };
}

// Conjunto acotado de agentes para resolver slugs (con teléfono representativo).
const agentDirectoryUncachedFull = async (): Promise<AgentRow[]> => {
  if (!databaseUrl()) return [];
  try {
    return await readOnly((sql) => sql.unsafe<AgentRow[]>(
      `SELECT p.agente_nombre AS nombre, count(*)::int AS total,
         mode() WITHIN GROUP (ORDER BY p.ciudad) AS ciudad,
         mode() WITHIN GROUP (ORDER BY p.provincia) AS provincia,
         mode() WITHIN GROUP (ORDER BY p.agente_telefono) AS telefono
       FROM public.propiedades p
       WHERE p.agente_nombre IS NOT NULL AND btrim(p.agente_nombre) <> ''
       GROUP BY p.agente_nombre
       ORDER BY count(*) DESC
       LIMIT 2000`, []));
  } catch (error) {
    console.error("ERETZ agentDirectoryFull failed", error instanceof Error ? error.message : "unknown error");
    return [];
  }
};

// Publicaciones de un agente por nombre exacto (gate-aplicado).
export async function getPropertiesByAgent(name: string, limit = 48): Promise<PropertySummary[]> {
  if (!databaseUrl() || !name.trim()) return [];
  const gate = await getPreviewQualityGate();
  if (!gate.enabled) return [];
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(
      `SELECT ${summaryProjection}, (CASE WHEN p.estado = 'activa' THEN 1e10 ELSE 0 END + p.id) AS __sort_value
       FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
       WHERE p.agente_nombre = $1
       ORDER BY __sort_value DESC
       LIMIT $2`, [name.trim(), Math.min(Math.max(1, limit), 96)]));
    return mapRowsToSummaries(rows.filter((row) => gate.isVisible(row.id)));
  } catch (error) {
    console.error("ERETZ getPropertiesByAgent failed", error instanceof Error ? error.message : "unknown error");
    return [];
  }
}

// Otras publicaciones de la MISMA propiedad física: mismas señales fuertes
// (misma dirección exacta y ciudad). Señal data-backed de duplicado sin depender
// de la tabla de grupos. Gate-aplicado; excluye la publicación actual.
export async function getOtherPublications(property: Property, limit = 6): Promise<PropertySummary[]> {
  const address = property.address?.trim();
  if (!databaseUrl() || !address || !/^\d+$/.test(property.id)) return [];
  const gate = await getPreviewQualityGate();
  if (!gate.enabled) return [];
  const params: unknown[] = [Number(property.id), address];
  let clause = "p.id <> $1 AND btrim(p.direccion) <> '' AND lower(btrim(p.direccion)) = lower(btrim($2))";
  const city = property.city?.trim();
  if (city) { params.push(city); clause += ` AND p.ciudad = $${params.length}`; }
  params.push(Math.min(Math.max(1, limit), 12));
  const limitIdx = params.length;
  try {
    const rows = await readOnly((sql) => sql.unsafe<DbPropertyRow[]>(
      `SELECT ${summaryProjection}, p.id AS __sort_value
       FROM public.propiedades p LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id
       WHERE ${clause}
       ORDER BY (CASE WHEN p.estado = 'activa' THEN 1 ELSE 0 END) DESC, p.id DESC
       LIMIT $${limitIdx}`, params as never[]));
    return mapRowsToSummaries(rows.filter((row) => gate.isVisible(row.id)));
  } catch (error) {
    console.error("ERETZ getOtherPublications failed", error instanceof Error ? error.message : "unknown error");
    return [];
  }
}

export type PriceHistoryPoint = { price: number; currency: string | null; at: string };

// Historial de precios (read-model). Sólo consulta si ERETZ_PRICE_HISTORY=1 y la
// tabla existe; si no, devuelve [] (la ficha no muestra la sección). Nunca genera
// datos ficticios. Ver migración 20260810000000_listing_price_history.
export async function getPriceHistory(id: string): Promise<PriceHistoryPoint[]> {
  if (process.env.ERETZ_PRICE_HISTORY !== "1" || !databaseUrl() || !/^\d+$/.test(id)) return [];
  try {
    const rows = await readOnly((sql) => sql.unsafe<Array<{ precio: number; moneda: string | null; observado_en: string }>>(
      `SELECT precio, moneda, observado_en FROM public.listing_price_history
       WHERE propiedad_id = $1 ORDER BY observado_en ASC LIMIT 50`, [Number(id)]));
    return rows.map((r) => ({ price: Number(r.precio), currency: r.moneda, at: String(r.observado_en) }));
  } catch {
    return [];
  }
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

function clusterMapProperties(valid: ClassifiedMapCandidate[], zoom: number): MapSearchResponse["points"] {
  const marker = (property: ClassifiedMapCandidate) => ({
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
    locationConfidence: property.locationConfidence,
  });
  if (zoom >= 12) {
    return valid.slice(0, 800).map(marker);
  }
  const cell = Math.max(0.008, (zoom <= 6 ? 128 : 48) / (2 ** zoom));
  const groups = new Map<string, { latitude: number; longitude: number; count: number; first: ClassifiedMapCandidate }>();
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
  const gate = await getPreviewQualityGate();
  if (!databaseUrl() || !gate.enabled) return { points: [], visibleCount: 0, scannedCount: 0, truncated: false };
  const mapFilters = { ...filters, direction: "next" as const, cursor: "", sort: "recent" as const };
  // National views need representative coarse clusters, not thousands of rows
  // that collapse into a handful of markers. Increase density only as users zoom.
  const target = viewport.zoom >= 12 ? 700 : viewport.zoom >= 9 ? 1_400 : viewport.zoom >= 7 ? 1_000 : 600;
  const scanBatchSize = Math.ceil(target / 0.75);
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
  const stats = await getPointStats(accepted);
  const classified = accepted.map((property): ClassifiedMapCandidate => ({
    ...property,
    locationConfidence: assessLocationConfidence({
      latitude: property.latitud,
      longitude: property.longitud,
      address: property.direccion,
      neighborhood: property.barrio,
      city: property.ciudad,
      province: property.provincia,
      pointStats: stats.get(coordinateKey(property.latitud, property.longitud)),
    }).level as Exclude<LocationConfidence, "none">,
  }));
  return {
    points: clusterMapProperties(classified, viewport.zoom),
    visibleCount: accepted.length,
    scannedCount,
    truncated,
  };
}

export function searchMap(filters: PropertyFilters, viewport: MapViewport): Promise<MapSearchResponse> {
  return cachedQuery(mapCache, JSON.stringify([filters, viewport]), QUERY_CACHE_TTL_MS, () => searchMapUncached(filters, viewport));
}

// Prioridad de agrupación del autocomplete universal.
const SUGGESTION_PRIORITY: Record<SearchSuggestion["category"], number> = {
  id: 0, provincia: 1, ciudad: 2, barrio: 3, dirección: 4, inmobiliaria: 5, agente: 6, tipo: 7,
};

export function suggestionMatchRank(query: string, label: string | null | undefined): number | null {
  const normalizedQuery = normalizeSearch(query.trim());
  const normalizedLabel = normalizeSearch(label?.trim() ?? "");
  if (!normalizedQuery || !normalizedLabel || !normalizedLabel.includes(normalizedQuery)) return null;
  if (normalizedLabel === normalizedQuery) return 0;
  if (normalizedLabel.startsWith(normalizedQuery)) return 1;
  return 2;
}

async function searchSuggestionsUncached(query: string): Promise<SearchSuggestion[]> {
  const q = query.trim().slice(0, 60);
  if (q.length < 2) return [];
  const gate = await getPreviewQualityGate();
  if (!databaseUrl() || !gate.enabled) return [];
  const suggestions = new Map<string, SearchSuggestion>();
  const add = (category: SearchSuggestion["category"], value: string | null | undefined, context?: string | null) => {
    const label = value?.trim();
    if (!label) return;
    const normalizedLabel = normalizeSearch(label);
    // queryBatch encuentra filas por cualquiera de sus campos. El autocomplete
    // sólo debe exponer el campo que realmente coincide: nunca arrastra barrio,
    // dirección o publicador no relacionados desde la misma fila.
    if (suggestionMatchRank(q, label) === null) return;
    const key = `${category}:${normalizedLabel}`;
    const cleanContext = context?.trim();
    if (!suggestions.has(key)) suggestions.set(key, { id: key, label, category, query: label, context: cleanContext || undefined });
  };
  // ID ERETZ: coincidencia directa a la ficha (sólo si el gate la autoriza — así
  // no se filtra una propiedad no publicable ni una inexistente).
  if (/^\d+$/.test(q) && gate.isVisible(q)) {
    suggestions.set(`id:${q}`, { id: `id:${q}`, label: `Propiedad #${q}`, category: "id", query: q, href: `/propiedad/${q}` });
  }
  const filters = parsePropertyFilters({ q });
  const rows = await queryBatch(filters, 300, null);
  for (const row of rows) {
    if (!gate.isVisible(row.id)) continue;
    add("provincia", row.provincia, row.pais);
    add("ciudad", row.ciudad, row.provincia);
    add("barrio", row.barrio, [row.ciudad, row.provincia].filter(Boolean).join(", "));
    add("dirección", row.direccion, [row.barrio, row.ciudad].filter(Boolean).join(", "));
    add("inmobiliaria", row.publisher_name);
    add("agente", row.agente_nombre);
    add("tipo", row.tipo_propiedad);
    if (suggestions.size >= 48) break;
  }
  return [...suggestions.values()]
    .sort((a, b) => {
      return (suggestionMatchRank(q, a.label) ?? 3) - (suggestionMatchRank(q, b.label) ?? 3)
        || SUGGESTION_PRIORITY[a.category] - SUGGESTION_PRIORITY[b.category]
        || a.label.localeCompare(b.label, "es-AR");
    })
    .slice(0, 12);
}

export function searchSuggestions(query: string): Promise<SearchSuggestion[]> {
  const key = normalizeSearch(query.trim().slice(0, 60));
  return cachedQuery(suggestionCache, key, DETAIL_CACHE_TTL_MS, () => searchSuggestionsUncached(query));
}

export async function getHomeInventory() {
  const result = await searchProperties(parsePropertyFilters({}));
  return { count: result.count ?? 0, recent: result.properties.slice(0, 6), error: result.error };
}
