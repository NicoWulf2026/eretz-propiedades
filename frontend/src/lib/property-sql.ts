import type { MapViewport, PropertyFilters, PropertySort } from "@/types/property";

// SQL puro (sin acceso a base ni `server-only`) para poder testear el contrato de
// cobertura y el orden neutral. El Quality Gate se aplica en la app y es la única
// autoridad de visibilidad.

export function normalizeSearch(value: string) {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function addParam(params: unknown[], value: unknown) {
  params.push(value);
  return `$${params.length}`;
}

export function buildWhere(filters: PropertyFilters, extra?: MapViewport) {
  const params: unknown[] = [];
  // NO se filtra por `estado`: una propiedad autorizada por el Quality Gate debe ser
  // alcanzable aunque su estado sea `no_detectada_en_ultimo_scraping` o `desconocida`.
  // El gate (aplicado en la app) excluye lo no publicable (REVIEW_REQUIRED, etc.).
  const conditions: string[] = ["TRUE"];
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

export function sortSpec(sort: PropertySort) {
  switch (sort) {
    case "price_asc": return { expression: "COALESCE(p.precio, 1e30)", ascending: true };
    case "price_desc": return { expression: "COALESCE(p.precio, 0)", ascending: false };
    case "area_desc": return { expression: "COALESCE(p.superficie_total, p.superficie_cubierta, 0)", ascending: false };
    case "rooms_desc": return { expression: "COALESCE(p.ambientes, 0)", ascending: false };
    case "price_m2_asc": return { expression: "COALESCE(p.precio / NULLIF(p.superficie_total, 0), 1e30)", ascending: true };
    // Orden predeterminado (recencia): las activas primero, luego por id descendente
    // (proxy de ingesta). El escalón se pliega en un único valor float para conservar
    // un cursor keyset comparable; 1e10 supera cualquier id real, así que una activa
    // siempre ordena por encima de una no confirmada sin importar el id.
    default: return { expression: "(CASE WHEN p.estado = 'activa' THEN 1e10 ELSE 0 END + p.id)", ascending: false };
  }
}
