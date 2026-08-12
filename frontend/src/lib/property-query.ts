import type {
  MapZone,
  PriceMode,
  PropertyCurrency,
  PropertyFilters,
  PropertyOperation,
  PropertySort,
  PropertyType,
  TriState,
} from "@/types/property";

export const MAX_ZONES = 6;

// Zonas del mapa: formato compacto `b:n,e,s,w` (rectángulo) o `r:lat,lng,km`
// (radio), separadas por `;`. Validadas a números finitos y acotados.
function parseZones(value: string | string[] | undefined): MapZone[] {
  const raw = (Array.isArray(value) ? value[0] : value) ?? "";
  if (!raw) return [];
  const out: MapZone[] = [];
  for (const part of raw.split(";").slice(0, MAX_ZONES)) {
    const [kind, nums] = part.split(":");
    const n = (nums ?? "").split(",").map(Number);
    if (kind === "b" && n.length === 4 && n.every(Number.isFinite)) {
      const [north, east, south, west] = n;
      if (north > south && east > west && Math.abs(north) <= 90 && Math.abs(south) <= 90 && Math.abs(east) <= 180 && Math.abs(west) <= 180) {
        out.push({ kind: "box", north, east, south, west });
      }
    } else if (kind === "r" && n.length === 3 && n.every(Number.isFinite)) {
      const [lat, lng, km] = n;
      if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180 && km > 0 && km <= 100) {
        out.push({ kind: "radius", lat, lng, km });
      }
    }
  }
  return out;
}

export function serializeZones(zones: MapZone[]): string {
  return zones
    .map((z) => (z.kind === "box" ? `b:${z.north},${z.east},${z.south},${z.west}` : `r:${z.lat},${z.lng},${z.km}`))
    .join(";");
}

export const MAX_LOCATIONS = 10;
const triStates = new Set<TriState>(["si", "no", "sininfo"]);

export type SearchParams = Record<string, string | string[] | undefined>;

const operations = new Set<PropertyOperation>([
  "venta",
  "alquiler",
  "temporario",
  "consultar",
  "venta_y_alquiler",
]);
const propertyTypes = new Set<PropertyType>([
  "departamento",
  "casa",
  "ph",
  "terreno",
  "oficina",
  "local",
  "cochera",
  "galpon",
  "campo",
  "otro",
]);
const currencies = new Set<PropertyCurrency>(["USD", "ARS", "EUR", "UYU"]);
const sorts = new Set<PropertySort>([
  "recent", "price_asc", "price_desc", "area_desc", "rooms_desc", "price_m2_asc", "nearest",
]);
const modes = new Set(["map", "balanced", "results", "map_only", "results_only", "analysis"] as const);

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function text(value: string | string[] | undefined, max = 80) {
  return one(value).replace(/[(),.*%]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

function positive(value: string | string[] | undefined) {
  const number = Number(one(value));
  return Number.isFinite(number) && number > 0 ? number : null;
}

function bounded(value: string | string[] | undefined, min: number, max: number) {
  const number = Number(one(value));
  return Number.isFinite(number) && number >= min && number <= max ? number : null;
}

function parseViewport(params: SearchParams) {
  const north = bounded(params.norte, -90, 90);
  const east = bounded(params.este, -180, 180);
  const south = bounded(params.sur, -90, 90);
  const west = bounded(params.oeste, -180, 180);
  const zoom = bounded(params.zoom, 3, 19);
  if (north === null || east === null || south === null || west === null || zoom === null) return null;
  if (north <= south || east <= west) return null;
  return { north, east, south, west, zoom };
}

// Multi-ubicación: OR entre términos, cada uno cotejado contra provincia/ciudad/
// barrio/dirección. Acepta repeticiones (`ubicaciones=A&ubicaciones=B`) o coma.
function parseLocations(value: string | string[] | undefined): string[] {
  const raw = Array.isArray(value) ? value : [value ?? ""];
  const tokens = raw.flatMap((entry) => String(entry ?? "").split(","));
  const seen = new Set<string>();
  const out: string[] = [];
  for (const token of tokens) {
    const clean = token.replace(/[(),.*%]/g, " ").replace(/\s+/g, " ").trim().slice(0, 60);
    const key = clean.toLowerCase();
    if (clean && !seen.has(key)) { seen.add(key); out.push(clean); }
    if (out.length >= MAX_LOCATIONS) break;
  }
  return out;
}

function parseNear(params: SearchParams) {
  const latRaw = one(params.cerca_lat);
  const lngRaw = one(params.cerca_lng);
  if (!latRaw || !lngRaw) return null; // `bounded("")` daría 0; exigimos valor real
  const lat = bounded(latRaw, -90, 90);
  const lng = bounded(lngRaw, -180, 180);
  return lat === null || lng === null ? null : { lat, lng };
}

function parsePriceMode(value: string | string[] | undefined): PriceMode {
  const v = one(value);
  if (v === "with" || v === "1") return "with"; // "1" = compatibilidad con el checkbox anterior
  if (v === "consult") return "consult";
  return "";
}

function parseTriState(value: string | string[] | undefined): TriState {
  const v = one(value);
  if (v === "1") return "si"; // compatibilidad con el valor booleano anterior
  return triStates.has(v as TriState) ? (v as TriState) : "";
}

export function parsePropertyFilters(params: SearchParams): PropertyFilters {
  const operation = one(params.operacion) as PropertyOperation;
  const propertyType = one(params.tipo) as PropertyType;
  const currency = one(params.moneda).toUpperCase() as PropertyCurrency;
  const near = parseNear(params);
  let sort = one(params.orden) as PropertySort;

  if (!sorts.has(sort)) sort = "recent";
  if ((sort === "price_asc" || sort === "price_desc" || sort === "price_m2_asc") && !currencies.has(currency)) {
    sort = "recent";
  }
  if (sort === "nearest" && !near) sort = "recent";

  const cursorCandidate = one(params.cursor).slice(0, 420);
  const cursor = /^[A-Za-z0-9_-]+$/.test(cursorCandidate) ? cursorCandidate : "";
  const requestedPage = Math.min(Math.max(1, Math.floor(positive(params.pagina) ?? 1)), 10_000);
  const modeCandidate = one(params.modo) as PropertyFilters["mode"];
  return {
    q: text(params.q),
    operation: operations.has(operation) ? operation : "",
    propertyType: propertyTypes.has(propertyType) ? propertyType : "",
    province: text(params.provincia),
    city: text(params.ciudad),
    neighborhood: text(params.barrio),
    locations: parseLocations(params.ubicaciones),
    zones: parseZones(params.zonas),
    minPrice: positive(params.precio_min),
    maxPrice: positive(params.precio_max),
    currency: currencies.has(currency) ? currency : "",
    minRooms: positive(params.ambientes),
    minBedrooms: positive(params.dormitorios),
    minBathrooms: positive(params.banos),
    minGarages: positive(params.cocheras),
    minArea: positive(params.superficie),
    maxArea: positive(params.superficie_max),
    minCoveredArea: positive(params.superficie_cubierta),
    minLandArea: positive(params.terreno),
    maxExpenses: positive(params.expensas_max),
    maxAge: positive(params.antiguedad_max),
    publisher: text(params.publicador),
    recentDays: bounded(params.reciente, 1, 365),
    hasImages: one(params.imagenes) === "1",
    priceMode: parsePriceMode(params.precio),
    hasLocation: one(params.ubicacion) === "1",
    hasVideo: one(params.video) === "1",
    hasFloorPlan: one(params.plano) === "1",
    mortgageState: parseTriState(params.credito),
    sort,
    near,
    page: cursor ? requestedPage : 1,
    cursor,
    direction: cursor && one(params.direccion) === "prev" ? "prev" : "next",
    mode: modes.has(modeCandidate as never) ? modeCandidate : "balanced",
    viewport: parseViewport(params),
    selectedId: /^\d+$/.test(one(params.seleccion)) ? one(params.seleccion) : "",
  };
}

export function filtersToSearchParams(filters: PropertyFilters) {
  const params = new URLSearchParams();
  const values: Array<[string, string | number | null | boolean]> = [
    ["q", filters.q],
    ["operacion", filters.operation],
    ["tipo", filters.propertyType],
    ["provincia", filters.province],
    ["ciudad", filters.city],
    ["barrio", filters.neighborhood],
    ["ubicaciones", filters.locations.length ? filters.locations.join(",") : ""],
    ["zonas", filters.zones.length ? serializeZones(filters.zones) : ""],
    ["precio_min", filters.minPrice],
    ["precio_max", filters.maxPrice],
    ["moneda", filters.currency],
    ["ambientes", filters.minRooms],
    ["dormitorios", filters.minBedrooms],
    ["banos", filters.minBathrooms],
    ["cocheras", filters.minGarages],
    ["superficie", filters.minArea],
    ["superficie_max", filters.maxArea],
    ["superficie_cubierta", filters.minCoveredArea],
    ["terreno", filters.minLandArea],
    ["expensas_max", filters.maxExpenses],
    ["antiguedad_max", filters.maxAge],
    ["publicador", filters.publisher],
    ["reciente", filters.recentDays],
    ["imagenes", filters.hasImages ? "1" : ""],
    ["precio", filters.priceMode],
    ["ubicacion", filters.hasLocation ? "1" : ""],
    ["video", filters.hasVideo ? "1" : ""],
    ["plano", filters.hasFloorPlan ? "1" : ""],
    ["credito", filters.mortgageState],
    ["orden", filters.sort === "recent" ? "" : filters.sort],
    ["cerca_lat", filters.near?.lat ?? null],
    ["cerca_lng", filters.near?.lng ?? null],
    ["pagina", filters.page > 1 ? filters.page : ""],
    ["cursor", filters.cursor],
    ["direccion", filters.cursor && filters.direction === "prev" ? "prev" : ""],
    ["modo", filters.mode === "balanced" ? "" : filters.mode],
    ["norte", filters.viewport?.north ?? null],
    ["este", filters.viewport?.east ?? null],
    ["sur", filters.viewport?.south ?? null],
    ["oeste", filters.viewport?.west ?? null],
    ["zoom", filters.viewport?.zoom ?? null],
    ["seleccion", filters.selectedId],
  ];
  values.forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== false) params.set(key, String(value));
  });
  return params;
}
