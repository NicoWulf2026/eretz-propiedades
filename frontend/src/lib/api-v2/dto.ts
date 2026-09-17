export const API_V2_CONTRACT = "eretz_api_property_v1" as const;
export const API_V2_RANKING = "eretz_ranking_tecnico_v1" as const;

export type ApiV2NamedGeoDto = { nombre: string | null };
export type ApiV2LocalityDto = ApiV2NamedGeoDto & {
  id: string | null;
  procedencia: "CANONICAL_NORMALIZED" | "UNKNOWN";
};
export type ApiV2SearchAreaDto = {
  nivel: "LOCALIDAD" | "MUNICIPIO" | "DEPARTAMENTO" | "PROVINCIA" | "SIN_AREA";
  nombre: string | null;
  id: string | null;
  origen: "localidad" | "municipio" | "departamento" | "provincia" | "sin_area";
};
export type ApiV2GeographyDto = {
  localidad: ApiV2LocalityDto;
  municipio: ApiV2NamedGeoDto;
  departamento: ApiV2NamedGeoDto;
  provincia: ApiV2NamedGeoDto;
  barrio: ApiV2NamedGeoDto;
  area_busqueda: ApiV2SearchAreaDto;
  estado: "GEO_CONFLICT" | null;
};
export type ApiV2RankingDto = {
  ranking_version: typeof API_V2_RANKING;
  total: number;
  partes: {
    coincidencia: number;
    ubicacion: number;
    completitud: number;
    imagenes: number;
  };
};
export type ApiV2PropertyDto = {
  id: string;
  source_url?: string | null;
  agency_id?: string | null;
  titulo: string | null;
  descripcion: string | null;
  operacion: string | null;
  tipo_propiedad: string | null;
  precio: number | null;
  moneda: string | null;
  ambientes: number | null;
  dormitorios: number | null;
  banos: number | null;
  superficie_total: number | null;
  superficie_cubierta: number | null;
  imagenes: string[];
  latitud: number | null;
  longitud: number | null;
  geo?: ApiV2GeographyDto | null;
  alcances: string[];
  ranking?: ApiV2RankingDto | null;
};

export type ApiV2PageDto = {
  contrato: typeof API_V2_CONTRACT;
  total: number;
  limit: number;
  offset: number;
  data: ApiV2PropertyDto[];
};
export type ApiV2SearchPageDto = ApiV2PageDto & {
  ranking: typeof API_V2_RANKING | null;
  sort: "relevance" | "price_asc" | "price_desc";
  consulta: string | null;
};
export type ApiV2MapItemDto = Pick<ApiV2PropertyDto, "id" | "precio" | "moneda" | "operacion" | "tipo_propiedad" | "titulo"> & {
  latitud: number;
  longitud: number;
};
export type ApiV2MapResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  total_matches: number;
  viewport_matches: number;
  returned_points: number;
  truncated: boolean;
  limit: number;
  data: ApiV2MapItemDto[];
};
export type ApiV2AgencyResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  data: {
    agency_id: string;
    name: string;
    logo: string | null;
    website: string | null;
    contact: {
      status: "AVAILABLE" | "UNAVAILABLE";
      phone: string | null;
      whatsapp: string | null;
      email: string | null;
    };
  };
};
export type ApiV2BatchResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  items: ApiV2PropertyDto[];
  missing_ids: string[];
  requested_ids: string[];
};
export type ApiV2AreaDto = {
  nivel: ApiV2SearchAreaDto["nivel"];
  nombre: string;
  propiedades: number;
};
export type ApiV2AreasResponseDto = { contrato: typeof API_V2_CONTRACT; data: ApiV2AreaDto[] };
export type ApiV2NeighborhoodsResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  canonizado: false;
  data: Array<{ nombre: string; propiedades: number }>;
};
export type ApiV2SuggestionDto =
  | {
      tipo: "area";
      nivel: ApiV2SearchAreaDto["nivel"];
      nombre: string;
      propiedades: number;
    }
  | {
      tipo: "barrio";
      nivel: null;
      nombre: string;
      propiedades: number;
    };
export type ApiV2SuggestionsResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  data: ApiV2SuggestionDto[];
};
export type ApiV2FacetValueDto = { valor: string | number; propiedades: number };
export type ApiV2FiltersResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  filtros: {
    operacion: ApiV2FacetValueDto[];
    tipo_propiedad: ApiV2FacetValueDto[];
    moneda: ApiV2FacetValueDto[];
    area_nivel: ApiV2FacetValueDto[];
  };
  rango_de_precio: Array<{ moneda: string; minimo: number; maximo: number }>;
  sin_dato: Record<"operacion" | "tipo_propiedad" | "precio" | "localidad" | "latitud", number>;
};
export type ApiV2StatsResponseDto = {
  contrato: typeof API_V2_CONTRACT;
  propiedades: number;
  con_localidad_canonica: number;
  en_conflicto_geografico: number;
  area_de_busqueda_por_nivel: Partial<Record<ApiV2SearchAreaDto["nivel"], number>>;
  database_writes: 0;
};
