import type { GeoPoint, MapViewport, MapZone, PropertyFilters, PropertySort } from "@/types/property";

// Predicado SQL de una zona del mapa. Números ya validados en el parser (finitos y
// acotados) → seguros de inlinear. Rectángulo = BETWEEN; radio = haversine (km)
// con acos clampeado para evitar errores de dominio. Sin PostGIS.
function zonePredicate(zone: MapZone): string {
  if (zone.kind === "box") {
    return `(p.latitud BETWEEN ${Number(zone.south)} AND ${Number(zone.north)} AND p.longitud BETWEEN ${Number(zone.west)} AND ${Number(zone.east)})`;
  }
  const lat = Number(zone.lat), lng = Number(zone.lng), km = Number(zone.km);
  const cosExpr = `cos(radians(${lat}))*cos(radians(p.latitud))*cos(radians(p.longitud) - radians(${lng})) + sin(radians(${lat}))*sin(radians(p.latitud))`;
  return `(p.latitud IS NOT NULL AND p.longitud IS NOT NULL AND (6371 * acos(least(1, greatest(-1, ${cosExpr})))) <= ${km})`;
}

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
  // Multi-ubicación: OR entre términos; cada término cotejado contra
  // provincia/ciudad/barrio/dirección. El bloque completo se une con AND al resto,
  // así que una propiedad debe coincidir con AL MENOS una ubicación pedida.
  if (filters.locations.length) {
    const clauses = filters.locations.map((loc) => {
      const value = `%${loc}%`;
      const cols = ["p.provincia", "p.ciudad", "p.barrio", "p.direccion"];
      return `(${cols.map((col) => `${col} ILIKE ${addParam(params, value)}`).join(" OR ")})`;
    });
    conditions.push(`(${clauses.join(" OR ")})`);
  }
  // Multi-zona del mapa: OR entre zonas (rectángulo/radio), AND con el resto.
  if (filters.zones.length) {
    conditions.push(`(${filters.zones.map(zonePredicate).join(" OR ")})`);
  }
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
  // Precio: "with" = publicado; "consult" = a consultar (sin precio). El valor por
  // defecto ("") no filtra, así que "Todas" nunca excluye las de consultar.
  if (filters.priceMode === "with") conditions.push("p.precio > 0 AND p.moneda IS NOT NULL");
  else if (filters.priceMode === "consult") conditions.push("(p.precio IS NULL OR p.precio <= 0 OR p.moneda IS NULL)");
  if (filters.hasLocation) conditions.push("p.latitud IS NOT NULL AND p.longitud IS NOT NULL");
  if (filters.hasVideo) conditions.push("NULLIF(p.video_url, '') IS NOT NULL");
  if (filters.hasFloorPlan) conditions.push("NULLIF(p.plano_url, '') IS NOT NULL");
  // Tri-state NULL-safe: "no" es apto_credito FALSE explícito; "sininfo" es NULL.
  // Un dato ausente (NULL) nunca cae en "no".
  if (filters.mortgageState === "si") conditions.push("p.apto_credito IS TRUE");
  else if (filters.mortgageState === "no") conditions.push("p.apto_credito IS FALSE");
  else if (filters.mortgageState === "sininfo") conditions.push("p.apto_credito IS NULL");
  if (extra) {
    add("p.latitud <= ?", extra.north);
    add("p.latitud >= ?", extra.south);
    add("p.longitud <= ?", extra.east);
    add("p.longitud >= ?", extra.west);
  }
  return { where: conditions.join(" AND "), params };
}

export type CursorPayload = { version: 1; sort: PropertySort; value: string | number; id: string };

// Keyset de orden TOTAL y estable: (expresión de orden, id) con desempate único por
// id. El mismo operador se aplica a la expresión y al id, de modo que la frontera del
// cursor nunca repite ni omite filas. `direction: "prev"` invierte el operador.
export function buildCursorClause(
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

const recentExpression = "(CASE WHEN p.estado = 'activa' THEN 1e10 ELSE 0 END + p.id)";

export function sortSpec(sort: PropertySort, near?: GeoPoint | null) {
  switch (sort) {
    case "price_asc": return { expression: "COALESCE(p.precio, 1e30)", ascending: true };
    case "price_desc": return { expression: "COALESCE(p.precio, 0)", ascending: false };
    case "area_desc": return { expression: "COALESCE(p.superficie_total, p.superficie_cubierta, 0)", ascending: false };
    case "rooms_desc": return { expression: "COALESCE(p.ambientes, 0)", ascending: false };
    case "price_m2_asc": return { expression: "COALESCE(p.precio / NULLIF(p.superficie_total, 0), 1e30)", ascending: true };
    // Cercanía: distancia euclídea al cuadrado respecto de un punto de referencia
    // (suficiente para ordenar, sin PostGIS). lat/lng ya vienen validados como
    // números finitos y acotados, por eso se inlinean como literales seguros. Las
    // propiedades sin coordenadas van al final (1e30) y desempatan por id.
    case "nearest": {
      if (!near) return { expression: recentExpression, ascending: false };
      const dLat = `(p.latitud - (${Number(near.lat)}))`;
      const dLng = `(p.longitud - (${Number(near.lng)}))`;
      return {
        expression: `(CASE WHEN p.latitud IS NULL OR p.longitud IS NULL THEN 1e30 ELSE (${dLat}*${dLat} + ${dLng}*${dLng}) END)`,
        ascending: true,
      };
    }
    // Orden predeterminado (recencia): las activas primero, luego por id descendente
    // (proxy de ingesta). El escalón se pliega en un único valor float para conservar
    // un cursor keyset comparable; 1e10 supera cualquier id real, así que una activa
    // siempre ordena por encima de una no confirmada sin importar el id.
    default: return { expression: recentExpression, ascending: false };
  }
}
