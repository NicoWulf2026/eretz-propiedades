import type {
  PropertyCurrency,
  PropertyFilters,
  PropertyOperation,
  PropertySort,
  PropertyType,
} from "@/types/property";

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
  "recent", "price_asc", "price_desc", "area_desc", "rooms_desc", "price_m2_asc",
]);
const modes = new Set(["map", "balanced", "results", "map_only", "results_only"] as const);

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

export function parsePropertyFilters(params: SearchParams): PropertyFilters {
  const operation = one(params.operacion) as PropertyOperation;
  const propertyType = one(params.tipo) as PropertyType;
  const currency = one(params.moneda).toUpperCase() as PropertyCurrency;
  let sort = one(params.orden) as PropertySort;

  if (!sorts.has(sort)) sort = "recent";
  if ((sort === "price_asc" || sort === "price_desc") && !currencies.has(currency)) {
    sort = "recent";
  }

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
    hasPrice: one(params.precio) === "1",
    hasLocation: one(params.ubicacion) === "1",
    hasVideo: one(params.video) === "1",
    hasFloorPlan: one(params.plano) === "1",
    mortgageEligible: one(params.credito) === "1",
    sort,
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
    ["precio", filters.hasPrice ? "1" : ""],
    ["ubicacion", filters.hasLocation ? "1" : ""],
    ["video", filters.hasVideo ? "1" : ""],
    ["plano", filters.hasFloorPlan ? "1" : ""],
    ["credito", filters.mortgageEligible ? "1" : ""],
    ["orden", filters.sort === "recent" ? "" : filters.sort],
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
