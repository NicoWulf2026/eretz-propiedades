import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { getPreviewQualityGate } from "@/lib/preview-quality-gate";
import { supabase } from "@/lib/supabase-client";
import type {
  Property,
  PropertyFilters,
  PropertySearchResult,
  SupabaseProperty,
} from "@/types/property";

export const PROPERTY_PAGE_SIZE = 24;
const TIMEOUT_MS = 20_000;
const PREVIEW_SCAN_BATCH_SIZE = 250;
const MAX_PREVIEW_SCAN_BATCHES = 1_100;
const columns = [
  "id", "inmobiliaria_id", "url", "titulo", "descripcion", "precio", "moneda",
  "precio_usd", "precio_ars", "expensas", "expensas_moneda", "tipo_propiedad",
  "operacion", "ambientes", "dormitorios", "banos", "toilettes", "cocheras",
  "antiguedad", "piso", "superficie_total", "superficie_cubierta",
  "superficie_terreno", "direccion", "barrio", "ciudad", "provincia", "pais",
  "latitud", "longitud", "imagenes", "video_url", "plano_url", "amenities",
  "agente_nombre", "agente_telefono", "fecha_publicacion", "estado", "created_at",
  "updated_at", "apto_credito",
].join(",");

function operationValue(operation: PropertyFilters["operation"]) {
  return operation === "temporario" ? "alquiler_temporario" : operation;
}

function decodeCursor(cursor: string) {
  const [value, id] = cursor.split(":");
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && /^\d+$/.test(id ?? "")
    ? { value: numericValue, id: id as string }
    : null;
}

function cursorFor(property: Property, sort: PropertyFilters["sort"]) {
  const value =
    sort === "price_asc" || sort === "price_desc"
      ? property.price
      : sort === "area_desc"
        ? property.totalArea
        : Number(property.id);
  return value == null ? null : `${value}:${property.id}`;
}

async function timed<T>(request: PromiseLike<T>): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await Promise.race([
      request,
      new Promise<never>((_, reject) =>
        controller.signal.addEventListener("abort", () => reject(new Error("timeout"))),
      ),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

function hasActiveFilters(filters: PropertyFilters) {
  return Boolean(
    filters.q || filters.operation || filters.propertyType || filters.province || filters.city ||
    filters.neighborhood || filters.minPrice || filters.maxPrice || filters.currency ||
    filters.minRooms || filters.minBedrooms || filters.minBathrooms || filters.minGarages ||
    filters.minArea || filters.hasImages || filters.hasPrice || filters.sort !== "recent",
  );
}

function buildSearchQuery(
  filters: PropertyFilters,
  cursor: ReturnType<typeof decodeCursor>,
  isPrevious: boolean,
  includeCount: boolean,
) {
  let query = supabase!
    .from("propiedades")
    .select(columns, includeCount ? { count: "exact" } : undefined)
    .eq("estado", "activa");
  if (filters.q) query = query.ilike("titulo", `%${filters.q}%`);
  if (filters.operation) query = query.eq("operacion", operationValue(filters.operation));
  if (filters.propertyType && filters.propertyType !== "otro") query = query.eq("tipo_propiedad", filters.propertyType);
  if (filters.province) query = query.eq("provincia", filters.province);
  if (filters.city) query = query.eq("ciudad", filters.city);
  if (filters.neighborhood) query = query.eq("barrio", filters.neighborhood);
  if (filters.currency) query = query.eq("moneda", filters.currency);
  if (filters.minPrice) query = query.gte("precio", filters.minPrice);
  if (filters.maxPrice) query = query.lte("precio", filters.maxPrice);
  if (filters.minRooms) query = query.gte("ambientes", filters.minRooms);
  if (filters.minBedrooms) query = query.gte("dormitorios", filters.minBedrooms);
  if (filters.minBathrooms) query = query.gte("banos", filters.minBathrooms);
  if (filters.minGarages) query = query.gte("cocheras", filters.minGarages);
  if (filters.minArea) query = query.gte("superficie_total", filters.minArea);
  if (filters.hasPrice) query = query.gt("precio", 0);
  if (filters.hasImages) query = query.not("imagenes", "is", null);
  if (filters.sort === "price_asc" || filters.sort === "price_desc") query = query.gt("precio", 0);
  if (filters.sort === "area_desc") query = query.gt("superficie_total", 0);

  if (filters.sort === "price_asc") {
    if (cursor) query = isPrevious
      ? query.or(`precio.lt.${cursor.value},and(precio.eq.${cursor.value},id.lt.${cursor.id})`)
      : query.or(`precio.gt.${cursor.value},and(precio.eq.${cursor.value},id.gt.${cursor.id})`);
    return query.order("precio", { ascending: !isPrevious, nullsFirst: false }).order("id", { ascending: !isPrevious });
  }
  if (filters.sort === "price_desc") {
    if (cursor) query = isPrevious
      ? query.or(`precio.gt.${cursor.value},and(precio.eq.${cursor.value},id.gt.${cursor.id})`)
      : query.or(`precio.lt.${cursor.value},and(precio.eq.${cursor.value},id.lt.${cursor.id})`);
    return query.order("precio", { ascending: isPrevious, nullsFirst: false }).order("id", { ascending: isPrevious });
  }
  if (filters.sort === "area_desc") {
    if (cursor) query = isPrevious
      ? query.or(`superficie_total.gt.${cursor.value},and(superficie_total.eq.${cursor.value},id.gt.${cursor.id})`)
      : query.or(`superficie_total.lt.${cursor.value},and(superficie_total.eq.${cursor.value},id.lt.${cursor.id})`);
    return query.order("superficie_total", { ascending: isPrevious, nullsFirst: false }).order("id", { ascending: isPrevious });
  }
  if (cursor) query = isPrevious ? query.gt("id", cursor.id) : query.lt("id", cursor.id);
  return query.order("id", { ascending: isPrevious });
}

export async function searchProperties(filters: PropertyFilters): Promise<PropertySearchResult> {
  if (!supabase) {
    return { properties: [], count: null, page: 1, pageSize: PROPERTY_PAGE_SIZE, hasNext: false, hasPrevious: false, nextCursor: null, previousCursor: null, source: "unconfigured", error: true };
  }
  try {
    const gate = getPreviewQualityGate();
    const initialCursor = decodeCursor(filters.cursor);
    const isPrevious = Boolean(initialCursor && filters.direction === "prev");
    const chunkSize = gate.enabled ? PREVIEW_SCAN_BATCH_SIZE : PROPERTY_PAGE_SIZE + 1;
    const accepted: Property[] = [];
    let scanCursor = initialCursor;
    let rawCount: number | null = null;
    let exhausted = false;
    for (let batch = 0; batch < MAX_PREVIEW_SCAN_BATCHES; batch += 1) {
      const includeCount = !gate.enabled && !filters.cursor && batch === 0;
      const { data, error, count } = await timed(
        buildSearchQuery(filters, scanCursor, isPrevious, includeCount).limit(chunkSize),
      );
      if (error) throw new Error(error.message);
      if (batch === 0) rawCount = count ?? null;
      const mapped = ((data ?? []) as unknown as SupabaseProperty[]).map(mapSupabasePropertyToProperty);
      accepted.push(...(gate.enabled ? mapped.filter((property) => gate.isVisible(property.id)) : mapped));
      exhausted = mapped.length < chunkSize;
      if (accepted.length > PROPERTY_PAGE_SIZE || exhausted || !gate.enabled) break;
      const rawLast = mapped[mapped.length - 1];
      const nextScanCursor = rawLast ? decodeCursor(cursorFor(rawLast, filters.sort) ?? "") : null;
      if (!nextScanCursor) {
        exhausted = true;
        break;
      }
      scanCursor = nextScanCursor;
      if (batch === MAX_PREVIEW_SCAN_BATCHES - 1) throw new Error("preview gate scan limit reached");
    }
    const hasExtra = accepted.length > PROPERTY_PAGE_SIZE;
    const properties = hasExtra ? accepted.slice(0, PROPERTY_PAGE_SIZE) : accepted;
    if (isPrevious) properties.reverse();
    return {
      properties,
      count: gate.enabled
        ? (!filters.cursor && !hasActiveFilters(filters) ? gate.visibleCount : null)
        : rawCount,
      page: filters.page,
      pageSize: PROPERTY_PAGE_SIZE,
      hasNext: isPrevious ? true : hasExtra || !exhausted,
      hasPrevious: isPrevious ? hasExtra : filters.page > 1,
      nextCursor: properties.length && (isPrevious || hasExtra)
        ? cursorFor(properties[properties.length - 1], filters.sort)
        : null,
      previousCursor: properties.length && (isPrevious ? hasExtra : filters.page > 1)
        ? cursorFor(properties[0], filters.sort)
        : null,
      source: "supabase",
      error: false,
    };
  } catch {
    return { properties: [], count: null, page: filters.page, pageSize: PROPERTY_PAGE_SIZE, hasNext: false, hasPrevious: filters.page > 1, nextCursor: null, previousCursor: null, source: "error", error: true };
  }
}

export async function getPropertyById(id: string): Promise<Property | null> {
  if (!supabase || !/^\d+$/.test(id)) return null;
  const gate = getPreviewQualityGate();
  if (gate.enabled && !gate.isVisible(id)) return null;
  const { data, error } = await timed(
    supabase.from("propiedades").select(columns).eq("estado", "activa").eq("id", id).maybeSingle(),
  );
  if (error || !data) return null;
  return mapSupabasePropertyToProperty(data as unknown as SupabaseProperty);
}

export async function getRelatedProperties(property: Property): Promise<Property[]> {
  if (!supabase) return [];
  const gate = getPreviewQualityGate();
  const collected: Property[] = [];
  let beforeId: string | null = null;
  const limit = gate.enabled ? PREVIEW_SCAN_BATCH_SIZE : 4;
  for (let batch = 0; batch < MAX_PREVIEW_SCAN_BATCHES && collected.length < 4; batch += 1) {
    let query = supabase
      .from("propiedades")
      .select(columns)
      .eq("estado", "activa")
      .neq("id", property.id)
      .eq("operacion", operationValue(property.operation))
      .eq("tipo_propiedad", property.rawPropertyType ?? property.propertyType)
      .order("id", { ascending: false })
      .limit(limit);
    if (property.province) query = query.eq("provincia", property.province);
    if (beforeId) query = query.lt("id", beforeId);
    const { data, error } = await timed(query);
    if (error) return [];
    const mapped = ((data ?? []) as unknown as SupabaseProperty[]).map(mapSupabasePropertyToProperty);
    collected.push(...(gate.enabled ? mapped.filter((item) => gate.isVisible(item.id)) : mapped));
    if (mapped.length < limit || !gate.enabled) break;
    beforeId = mapped[mapped.length - 1]?.id ?? null;
    if (!beforeId) break;
  }
  return collected.slice(0, 4);
}

export async function getHomeInventory() {
  if (!supabase) return { count: 0, recent: [] as Property[], error: true };
  try {
    const gate = getPreviewQualityGate();
    if (!gate.enabled) {
      const [countResult, recentResult] = await Promise.all([
        timed(supabase.from("propiedades").select("id", { count: "exact", head: true }).eq("estado", "activa")),
        timed(supabase.from("propiedades").select(columns).eq("estado", "activa").order("id", { ascending: false }).limit(6)),
      ]);
      if (countResult.error || recentResult.error) throw new Error("public query failed");
      return { count: countResult.count ?? 0, recent: ((recentResult.data ?? []) as unknown as SupabaseProperty[]).map(mapSupabasePropertyToProperty), error: false };
    }
    const recent: Property[] = [];
    let beforeId: string | null = null;
    for (let batch = 0; batch < MAX_PREVIEW_SCAN_BATCHES && recent.length < 6; batch += 1) {
      let query = supabase.from("propiedades").select(columns).eq("estado", "activa").order("id", { ascending: false }).limit(PREVIEW_SCAN_BATCH_SIZE);
      if (beforeId) query = query.lt("id", beforeId);
      const { data, error } = await timed(query);
      if (error) throw new Error(error.message);
      const mapped = ((data ?? []) as unknown as SupabaseProperty[]).map(mapSupabasePropertyToProperty);
      recent.push(...mapped.filter((property) => gate.isVisible(property.id)));
      if (mapped.length < PREVIEW_SCAN_BATCH_SIZE) break;
      beforeId = mapped[mapped.length - 1]?.id ?? null;
      if (!beforeId) break;
    }
    return { count: gate.visibleCount ?? 0, recent: recent.slice(0, 6), error: false };
  } catch {
    return { count: 0, recent: [] as Property[], error: true };
  }
}
