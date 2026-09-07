import type { CatalogProperty } from "@/domain/catalog-property";
import { API_V2_RANKING, type ApiV2GeographyDto, type ApiV2PropertyDto } from "@/lib/api-v2/dto";

type GeographyOverrides = Partial<Omit<ApiV2GeographyDto, "localidad" | "area_busqueda">> & {
  localidad?: Partial<ApiV2GeographyDto["localidad"]>;
  area_busqueda?: Partial<ApiV2GeographyDto["area_busqueda"]>;
};

export function apiV2PropertyFixture(
  overrides: Partial<Omit<ApiV2PropertyDto, "geo">> = {},
  geoOverrides: GeographyOverrides = {},
): ApiV2PropertyDto {
  const geo: ApiV2GeographyDto = {
    localidad: { nombre: "Córdoba", id: "14014010", procedencia: "CANONICAL_NORMALIZED" },
    municipio: { nombre: "Córdoba" },
    departamento: { nombre: "Capital" },
    provincia: { nombre: "Córdoba" },
    barrio: { nombre: "Nueva Córdoba" },
    area_busqueda: { nivel: "LOCALIDAD", nombre: "Córdoba", id: "14014010", origen: "localidad" },
    estado: null,
  };
  return {
    id: "property-complete",
    source_url: "https://agency.example/properties/complete",
    agency_id: "agency:example",
    titulo: "Departamento luminoso",
    descripcion: "Descripción real de una propiedad completa.",
    operacion: "venta",
    tipo_propiedad: "departamento",
    precio: 150000,
    moneda: "USD",
    ambientes: 3,
    dormitorios: 2,
    banos: 1,
    superficie_total: 80,
    superficie_cubierta: 72,
    imagenes: ["https://images.example/property.jpg"],
    latitud: -31.4201,
    longitud: -64.1888,
    geo: {
      ...geo,
      ...geoOverrides,
      localidad: { ...geo.localidad, ...geoOverrides.localidad },
      area_busqueda: { ...geo.area_busqueda, ...geoOverrides.area_busqueda },
    },
    alcances: ["FICHA", "LISTADO", "AREA_BUSQUEDA", "FILTRO_PRECIO", "MAPA"],
    ...overrides,
  };
}

export const completeApiV2Property = apiV2PropertyFixture();

export const apiV2FixtureMatrix = {
  complete: completeApiV2Property,
  withoutPrice: apiV2PropertyFixture({ id: "without-price", precio: null, moneda: null }),
  zeroPrice: apiV2PropertyFixture({ id: "zero-price", precio: 0 }),
  withoutLocation: apiV2PropertyFixture(
    { id: "without-location", latitud: null, longitud: null },
    {
      localidad: { nombre: null, id: null, procedencia: "UNKNOWN" },
      municipio: { nombre: null },
      departamento: { nombre: null },
      provincia: { nombre: null },
      barrio: { nombre: null },
      area_busqueda: { nivel: "SIN_AREA", nombre: null, id: null, origen: "sin_area" },
    },
  ),
  withoutImages: apiV2PropertyFixture({ id: "without-images", imagenes: [] }),
  withoutBedrooms: apiV2PropertyFixture({ id: "without-bedrooms", dormitorios: null }),
  zeroBedrooms: apiV2PropertyFixture({ id: "zero-bedrooms", dormitorios: 0 }),
  withoutSurface: apiV2PropertyFixture({ id: "without-surface", superficie_total: null, superficie_cubierta: null }),
  zeroSurface: apiV2PropertyFixture({ id: "zero-surface", superficie_total: 0, superficie_cubierta: 0 }),
  rental: apiV2PropertyFixture({ id: "rental", operacion: "alquiler", precio: 650000, moneda: "ARS" }),
  sale: apiV2PropertyFixture({ id: "sale", operacion: "venta" }),
  ars: apiV2PropertyFixture({ id: "ars", precio: 650000, moneda: "ARS" }),
  usd: apiV2PropertyFixture({ id: "usd", precio: 150000, moneda: "USD" }),
  locality: apiV2PropertyFixture({ id: "locality" }),
  municipalityWithoutLocality: apiV2PropertyFixture(
    { id: "municipality" },
    {
      localidad: { nombre: null, id: null, procedencia: "UNKNOWN" },
      municipio: { nombre: "La Calera" },
      area_busqueda: { nivel: "MUNICIPIO", nombre: "La Calera", id: null, origen: "municipio" },
    },
  ),
  department: apiV2PropertyFixture(
    { id: "department" },
    {
      localidad: { nombre: null, id: null, procedencia: "UNKNOWN" },
      municipio: { nombre: null },
      departamento: { nombre: "Colón" },
      area_busqueda: { nivel: "DEPARTAMENTO", nombre: "Colón", id: null, origen: "departamento" },
    },
  ),
  province: apiV2PropertyFixture(
    { id: "province" },
    {
      localidad: { nombre: null, id: null, procedencia: "UNKNOWN" },
      municipio: { nombre: null },
      departamento: { nombre: null },
      area_busqueda: { nivel: "PROVINCIA", nombre: "Córdoba", id: null, origen: "provincia" },
    },
  ),
  withCoordinates: apiV2PropertyFixture({ id: "with-coordinates" }),
  withoutCoordinates: apiV2PropertyFixture({ id: "without-coordinates", latitud: null, longitud: null }),
  longDescription: apiV2PropertyFixture({ id: "long-description", descripcion: "Descripción extensa. ".repeat(100) }),
  emptyDescription: apiV2PropertyFixture({ id: "empty-description", descripcion: "" }),
  partial: apiV2PropertyFixture({
    id: "partial",
    titulo: null,
    descripcion: null,
    operacion: null,
    tipo_propiedad: null,
    precio: null,
    moneda: null,
    ambientes: null,
    dormitorios: null,
    banos: null,
    superficie_total: null,
    superficie_cubierta: null,
    imagenes: [],
    latitud: null,
    longitud: null,
    alcances: ["FICHA", "LISTADO"],
  }),
  ranked: apiV2PropertyFixture({
    id: "ranked",
    ranking: {
      ranking_version: API_V2_RANKING,
      total: 78.5,
      partes: { coincidencia: 50, ubicacion: 12, completitud: 12.5, imagenes: 4 },
    },
  }),
} satisfies Record<string, ApiV2PropertyDto>;

/** Missing agency id contradicts the current API v2 schema and must fail validation. */
export const invalidMissingAgencyDto: unknown = (() => {
  const value = { ...completeApiV2Property } as Partial<ApiV2PropertyDto>;
  delete value.agency_id;
  return value;
})();

export const expectedZeroDomain: Pick<CatalogProperty, "price" | "rooms" | "bedrooms" | "surfaces"> = {
  price: { amount: 0, currency: "USD", rawCurrency: "USD" },
  rooms: 3,
  bedrooms: 0,
  surfaces: { total: 0, covered: 0 },
};
