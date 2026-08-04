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
const sorts = new Set<PropertySort>(["recent", "price_asc", "price_desc", "area_desc"]);

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

export function parsePropertyFilters(params: SearchParams): PropertyFilters {
  const operation = one(params.operacion) as PropertyOperation;
  const propertyType = one(params.tipo) as PropertyType;
  const currency = one(params.moneda).toUpperCase() as PropertyCurrency;
  let sort = one(params.orden) as PropertySort;

  if (!sorts.has(sort)) sort = "recent";
  if ((sort === "price_asc" || sort === "price_desc") && !currencies.has(currency)) {
    sort = "recent";
  }

  const cursorCandidate = one(params.cursor);
  const cursor = /^\d+(?:\.\d+)?:\d+$/.test(cursorCandidate) ? cursorCandidate : "";
  const requestedPage = Math.min(Math.max(1, Math.floor(positive(params.pagina) ?? 1)), 10_000);
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
    hasImages: one(params.imagenes) === "1",
    hasPrice: one(params.precio) === "1",
    sort,
    page: cursor ? requestedPage : 1,
    cursor,
    direction: cursor && one(params.direccion) === "prev" ? "prev" : "next",
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
    ["imagenes", filters.hasImages ? "1" : ""],
    ["precio", filters.hasPrice ? "1" : ""],
    ["orden", filters.sort === "recent" ? "" : filters.sort],
    ["pagina", filters.page > 1 ? filters.page : ""],
    ["cursor", filters.cursor],
    ["direccion", filters.cursor && filters.direction === "prev" ? "prev" : ""],
  ];
  values.forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== false) params.set(key, String(value));
  });
  return params;
}
