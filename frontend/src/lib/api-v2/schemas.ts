import {
  API_V2_CONTRACT,
  API_V2_RANKING,
  type ApiV2GeographyDto,
  type ApiV2AreasResponseDto,
  type ApiV2FiltersResponseDto,
  type ApiV2MapResponseDto,
  type ApiV2AgencyResponseDto,
  type ApiV2BatchResponseDto,
  type ApiV2NeighborhoodsResponseDto,
  type ApiV2PageDto,
  type ApiV2PropertyDto,
  type ApiV2RankingDto,
  type ApiV2SearchPageDto,
  type ApiV2SuggestionsResponseDto,
} from "./dto";
import type { ApiV2Issue } from "./errors";

export type ValidationResult<T> =
  | { success: true; data: T; issues: ApiV2Issue[] }
  | { success: false; issues: ApiV2Issue[] };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function optionalNullableString(value: unknown): value is string | null | undefined {
  return value === undefined || nullableString(value);
}

function nullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function nonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

const searchAreaLevels = ["LOCALIDAD", "MUNICIPIO", "DEPARTAMENTO", "PROVINCIA", "SIN_AREA"] as const;

function searchAreaLevel(value: unknown): value is (typeof searchAreaLevels)[number] {
  return typeof value === "string" && searchAreaLevels.includes(value as (typeof searchAreaLevels)[number]);
}

function issue(issues: ApiV2Issue[], path: string, message: string): false {
  issues.push({ path, message });
  return false;
}

function namedGeo(value: unknown, path: string, issues: ApiV2Issue[]): value is { nombre: string | null } {
  if (!record(value)) return issue(issues, path, "expected object");
  return nullableString(value.nombre) || issue(issues, `${path}.nombre`, "expected string or null");
}

function geography(value: unknown, path: string, issues: ApiV2Issue[]): value is ApiV2GeographyDto {
  if (!record(value)) return issue(issues, path, "expected object");
  let valid = true;
  const locality = value.localidad;
  if (!record(locality)) valid = issue(issues, `${path}.localidad`, "expected object");
  else {
    if (!nullableString(locality.nombre)) valid = issue(issues, `${path}.localidad.nombre`, "expected string or null");
    if (!nullableString(locality.id)) valid = issue(issues, `${path}.localidad.id`, "expected string or null");
    if (locality.procedencia !== "CANONICAL_NORMALIZED" && locality.procedencia !== "UNKNOWN") {
      valid = issue(issues, `${path}.localidad.procedencia`, "unknown locality provenance");
    }
  }
  for (const key of ["municipio", "departamento", "provincia", "barrio"] as const) {
    if (!namedGeo(value[key], `${path}.${key}`, issues)) valid = false;
  }
  const area = value.area_busqueda;
  if (!record(area)) valid = issue(issues, `${path}.area_busqueda`, "expected object");
  else {
    const levels = ["LOCALIDAD", "MUNICIPIO", "DEPARTAMENTO", "PROVINCIA", "SIN_AREA"];
    const origins = ["localidad", "municipio", "departamento", "provincia", "sin_area"];
    if (!levels.includes(String(area.nivel))) valid = issue(issues, `${path}.area_busqueda.nivel`, "unknown search area level");
    if (!nullableString(area.nombre)) valid = issue(issues, `${path}.area_busqueda.nombre`, "expected string or null");
    if (!nullableString(area.id)) valid = issue(issues, `${path}.area_busqueda.id`, "expected string or null");
    if (!origins.includes(String(area.origen))) valid = issue(issues, `${path}.area_busqueda.origen`, "unknown search area origin");
  }
  if (value.estado !== null && value.estado !== "GEO_CONFLICT") {
    valid = issue(issues, `${path}.estado`, "unknown geography state");
  }
  return valid;
}

function ranking(value: unknown, path: string, issues: ApiV2Issue[]): value is ApiV2RankingDto {
  if (!record(value)) return issue(issues, path, "expected object");
  let valid = true;
  if (value.ranking_version !== API_V2_RANKING) valid = issue(issues, `${path}.ranking_version`, "unexpected ranking version");
  if (typeof value.total !== "number" || !Number.isFinite(value.total)) valid = issue(issues, `${path}.total`, "expected finite number");
  if (!record(value.partes)) valid = issue(issues, `${path}.partes`, "expected object");
  else {
    for (const key of ["coincidencia", "ubicacion", "completitud", "imagenes"] as const) {
      if (typeof value.partes[key] !== "number" || !Number.isFinite(value.partes[key])) {
        valid = issue(issues, `${path}.partes.${key}`, "expected finite number");
      }
    }
  }
  return valid;
}

export function parseApiV2Property(value: unknown, path = "$"): ValidationResult<ApiV2PropertyDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path, message: "expected object" }] };
  let valid = true;
  if (typeof value.id !== "string" || value.id.length === 0) valid = issue(issues, `${path}.id`, "expected non-empty string");
  for (const key of ["source_url", "agency_id"] as const) {
    if (!optionalNullableString(value[key])) valid = issue(issues, `${path}.${key}`, "expected string, null or absent");
  }
  for (const key of ["titulo", "descripcion", "operacion", "tipo_propiedad", "moneda"] as const) {
    if (!nullableString(value[key])) valid = issue(issues, `${path}.${key}`, "expected string or null");
  }
  for (const key of ["precio", "ambientes", "dormitorios", "banos", "superficie_total", "superficie_cubierta", "latitud", "longitud"] as const) {
    if (!nullableFiniteNumber(value[key])) valid = issue(issues, `${path}.${key}`, "expected finite number or null");
  }
  if (!Array.isArray(value.imagenes) || !value.imagenes.every((item) => typeof item === "string")) {
    valid = issue(issues, `${path}.imagenes`, "expected string array");
  }
  if (!Array.isArray(value.alcances) || !value.alcances.every((item) => typeof item === "string")) {
    valid = issue(issues, `${path}.alcances`, "expected string array");
  }
  if (value.geo !== null && value.geo !== undefined && !geography(value.geo, `${path}.geo`, issues)) valid = false;
  if (value.ranking !== undefined && value.ranking !== null && !ranking(value.ranking, `${path}.ranking`, issues)) valid = false;
  return valid ? { success: true, data: value as ApiV2PropertyDto, issues } : { success: false, issues };
}

export function parseApiV2Page(value: unknown, search = false): ValidationResult<ApiV2PageDto | ApiV2SearchPageDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  let envelopeValid = true;
  if (value.contrato !== API_V2_CONTRACT) envelopeValid = issue(issues, "$.contrato", "unexpected API contract");
  for (const key of ["total", "offset"] as const) {
    const number = value[key];
    if (typeof number !== "number" || !Number.isInteger(number) || number < 0) {
      envelopeValid = issue(issues, `$.${key}`, "expected non-negative integer");
    }
  }
  if (typeof value.limit !== "number" || !Number.isInteger(value.limit) || value.limit < 1) {
    envelopeValid = issue(issues, "$.limit", "expected positive integer");
  }
  if (search) {
    if (value.ranking !== API_V2_RANKING && value.ranking !== null) envelopeValid = issue(issues, "$.ranking", "unexpected ranking version");
    if (!["relevance", "price_asc", "price_desc"].includes(String(value.sort))) envelopeValid = issue(issues, "$.sort", "unexpected sort");
    if (!nullableString(value.consulta)) envelopeValid = issue(issues, "$.consulta", "expected string or null");
  }
  if (!Array.isArray(value.data)) {
    envelopeValid = issue(issues, "$.data", "expected array");
    return { success: false, issues };
  }
  if (!envelopeValid) return { success: false, issues };

  const data: ApiV2PropertyDto[] = [];
  value.data.forEach((item, index) => {
    const parsed = parseApiV2Property(item, `$.data[${index}]`);
    if (parsed.success && search && value.ranking === API_V2_RANKING && parsed.data.ranking === undefined) {
      issue(issues, `$.data[${index}].ranking`, "search result requires technical ranking");
    } else if (parsed.success) data.push(parsed.data);
    else issues.push(...parsed.issues);
  });
  const parsed = { ...value, data } as unknown as ApiV2PageDto | ApiV2SearchPageDto;
  return { success: true, data: parsed, issues };
}

export function parseApiV2Map(value: unknown): ValidationResult<ApiV2MapResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  let valid = value.contrato === API_V2_CONTRACT || issue(issues, "$.contrato", "unexpected API contract");
  for (const key of ["total_matches", "viewport_matches", "returned_points"] as const) {
    if (!nonNegativeInteger(value[key])) valid = issue(issues, `$.${key}`, "expected non-negative integer");
  }
  if (!nonNegativeInteger(value.limit) || value.limit < 1) valid = issue(issues, "$.limit", "expected positive integer");
  if (typeof value.truncated !== "boolean") valid = issue(issues, "$.truncated", "expected boolean");
  if (!Array.isArray(value.data)) return { success: false, issues: [...issues, { path: "$.data", message: "expected array" }] };
  const data: ApiV2MapResponseDto["data"] = [];
  value.data.forEach((item, index) => {
    const path = `$.data[${index}]`;
    if (!record(item)) { issue(issues, path, "expected object"); return; }
    let itemValid = typeof item.id === "string" && item.id.length > 0;
    if (!itemValid) issue(issues, `${path}.id`, "expected non-empty string");
    for (const key of ["latitud", "longitud"] as const) if (!finiteNumber(item[key])) itemValid = issue(issues, `${path}.${key}`, "expected finite number");
    if (!nullableFiniteNumber(item.precio)) itemValid = issue(issues, `${path}.precio`, "expected finite number or null");
    for (const key of ["moneda", "operacion", "tipo_propiedad", "titulo"] as const) if (!nullableString(item[key])) itemValid = issue(issues, `${path}.${key}`, "expected string or null");
    if (itemValid) data.push(item as ApiV2MapResponseDto["data"][number]);
  });
  if (!valid) return { success: false, issues };
  return { success: true, data: { ...value, data } as ApiV2MapResponseDto, issues };
}

export function parseApiV2Agency(value: unknown): ValidationResult<ApiV2AgencyResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value) || value.contrato !== API_V2_CONTRACT || !record(value.data) || !record(value.data.contact)) {
    return { success: false, issues: [{ path: "$", message: "invalid agency envelope" }] };
  }
  const data = value.data;
  const contact = data.contact as Record<string, unknown>;
  let valid = true;
  for (const key of ["agency_id", "name"] as const) if (typeof data[key] !== "string" || !data[key]) valid = issue(issues, `$.data.${key}`, "expected non-empty string");
  for (const key of ["logo", "website"] as const) if (!nullableString(data[key])) valid = issue(issues, `$.data.${key}`, "expected string or null");
  if (contact.status !== "AVAILABLE" && contact.status !== "UNAVAILABLE") valid = issue(issues, "$.data.contact.status", "unexpected contact status");
  for (const key of ["phone", "whatsapp", "email"] as const) if (!nullableString(contact[key])) valid = issue(issues, `$.data.contact.${key}`, "expected string or null");
  return valid ? { success: true, data: value as ApiV2AgencyResponseDto, issues } : { success: false, issues };
}

export function parseApiV2Batch(value: unknown): ValidationResult<ApiV2BatchResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value) || value.contrato !== API_V2_CONTRACT) return { success: false, issues: [{ path: "$", message: "invalid batch envelope" }] };
  if (!Array.isArray(value.items) || !Array.isArray(value.missing_ids) || !Array.isArray(value.requested_ids)) return { success: false, issues: [{ path: "$", message: "invalid batch arrays" }] };
  if (![...value.missing_ids, ...value.requested_ids].every((id) => typeof id === "string")) return { success: false, issues: [{ path: "$", message: "batch ids must be strings" }] };
  const items: ApiV2PropertyDto[] = [];
  value.items.forEach((item, index) => { const parsed = parseApiV2Property(item, `$.items[${index}]`); if (parsed.success) items.push(parsed.data); else issues.push(...parsed.issues); });
  return { success: true, data: { ...value, items } as ApiV2BatchResponseDto, issues };
}

export function parseApiV2Areas(value: unknown): ValidationResult<ApiV2AreasResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  if (value.contrato !== API_V2_CONTRACT) issue(issues, "$.contrato", "unexpected API contract");
  if (!Array.isArray(value.data)) {
    issue(issues, "$.data", "expected array");
    return { success: false, issues };
  }
  if (value.contrato !== API_V2_CONTRACT) return { success: false, issues };
  const data: ApiV2AreasResponseDto["data"] = [];
  value.data.forEach((item, index) => {
    const path = `$.data[${index}]`;
    if (!record(item)) { issue(issues, path, "expected object"); return; }
    let valid = true;
    if (!searchAreaLevel(item.nivel)) valid = issue(issues, `${path}.nivel`, "unknown search area level");
    if (typeof item.nombre !== "string" || !item.nombre.trim()) valid = issue(issues, `${path}.nombre`, "expected non-empty string");
    if (!nonNegativeInteger(item.propiedades)) valid = issue(issues, `${path}.propiedades`, "expected non-negative integer");
    if (valid) data.push(item as ApiV2AreasResponseDto["data"][number]);
  });
  return { success: true, data: { contrato: API_V2_CONTRACT, data }, issues };
}

export function parseApiV2Neighborhoods(value: unknown): ValidationResult<ApiV2NeighborhoodsResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  let envelopeValid = true;
  if (value.contrato !== API_V2_CONTRACT) envelopeValid = issue(issues, "$.contrato", "unexpected API contract");
  if (value.canonizado !== false) envelopeValid = issue(issues, "$.canonizado", "expected explicit false");
  if (!Array.isArray(value.data)) {
    issue(issues, "$.data", "expected array");
    return { success: false, issues };
  }
  if (!envelopeValid) return { success: false, issues };
  const data: ApiV2NeighborhoodsResponseDto["data"] = [];
  value.data.forEach((item, index) => {
    const path = `$.data[${index}]`;
    if (!record(item)) { issue(issues, path, "expected object"); return; }
    let valid = true;
    if (typeof item.nombre !== "string" || !item.nombre.trim()) valid = issue(issues, `${path}.nombre`, "expected non-empty string");
    if (!nonNegativeInteger(item.propiedades)) valid = issue(issues, `${path}.propiedades`, "expected non-negative integer");
    if (valid) data.push(item as ApiV2NeighborhoodsResponseDto["data"][number]);
  });
  return { success: true, data: { contrato: API_V2_CONTRACT, canonizado: false, data }, issues };
}

export function parseApiV2Suggestions(value: unknown): ValidationResult<ApiV2SuggestionsResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  if (value.contrato !== API_V2_CONTRACT) issue(issues, "$.contrato", "unexpected API contract");
  if (!Array.isArray(value.data)) {
    issue(issues, "$.data", "expected array");
    return { success: false, issues };
  }
  if (value.contrato !== API_V2_CONTRACT) return { success: false, issues };
  const data: ApiV2SuggestionsResponseDto["data"] = [];
  value.data.forEach((item, index) => {
    const path = `$.data[${index}]`;
    if (!record(item)) { issue(issues, path, "expected object"); return; }
    let valid = true;
    if (item.tipo !== "area" && item.tipo !== "barrio") valid = issue(issues, `${path}.tipo`, "expected area or barrio");
    if (item.tipo === "area" && !searchAreaLevel(item.nivel)) valid = issue(issues, `${path}.nivel`, "area requires a known level");
    if (item.tipo === "barrio" && item.nivel !== null) valid = issue(issues, `${path}.nivel`, "neighborhood level must be null");
    if (typeof item.nombre !== "string" || !item.nombre.trim()) valid = issue(issues, `${path}.nombre`, "expected non-empty string");
    if (!nonNegativeInteger(item.propiedades)) valid = issue(issues, `${path}.propiedades`, "expected non-negative integer");
    if (valid) data.push(item as ApiV2SuggestionsResponseDto["data"][number]);
  });
  return { success: true, data: { contrato: API_V2_CONTRACT, data }, issues };
}

export function parseApiV2Filters(value: unknown): ValidationResult<ApiV2FiltersResponseDto> {
  const issues: ApiV2Issue[] = [];
  if (!record(value)) return { success: false, issues: [{ path: "$", message: "expected object" }] };
  let envelopeValid = true;
  if (value.contrato !== API_V2_CONTRACT) envelopeValid = issue(issues, "$.contrato", "unexpected API contract");
  if (!record(value.filtros)) envelopeValid = issue(issues, "$.filtros", "expected object");
  if (!Array.isArray(value.rango_de_precio)) envelopeValid = issue(issues, "$.rango_de_precio", "expected array");
  if (!record(value.sin_dato)) envelopeValid = issue(issues, "$.sin_dato", "expected object");
  if (!envelopeValid) return { success: false, issues };

  const parseFacets = (key: keyof ApiV2FiltersResponseDto["filtros"]) => {
    const raw = (value.filtros as Record<string, unknown>)[key];
    if (!Array.isArray(raw)) { issue(issues, `$.filtros.${key}`, "expected array"); return null; }
    const valid: ApiV2FiltersResponseDto["filtros"][typeof key] = [];
    raw.forEach((item, index) => {
      const path = `$.filtros.${key}[${index}]`;
      if (!record(item)) { issue(issues, path, "expected object"); return; }
      const valueValid = typeof item.valor === "string" || finiteNumber(item.valor);
      const countValid = nonNegativeInteger(item.propiedades);
      if (!valueValid) issue(issues, `${path}.valor`, "expected string or finite number");
      if (!countValid) issue(issues, `${path}.propiedades`, "expected non-negative integer");
      if (valueValid && countValid) valid.push(item as ApiV2FiltersResponseDto["filtros"][typeof key][number]);
    });
    return valid;
  };
  const operacion = parseFacets("operacion");
  const tipo_propiedad = parseFacets("tipo_propiedad");
  const moneda = parseFacets("moneda");
  const area_nivel = parseFacets("area_nivel");
  if (!operacion || !tipo_propiedad || !moneda || !area_nivel) return { success: false, issues };

  const rango_de_precio: ApiV2FiltersResponseDto["rango_de_precio"] = [];
  (value.rango_de_precio as unknown[]).forEach((item, index) => {
    const path = `$.rango_de_precio[${index}]`;
    if (!record(item)) { issue(issues, path, "expected object"); return; }
    let valid = true;
    if (typeof item.moneda !== "string" || !item.moneda.trim()) valid = issue(issues, `${path}.moneda`, "expected non-empty string");
    if (!finiteNumber(item.minimo)) valid = issue(issues, `${path}.minimo`, "expected finite number");
    if (!finiteNumber(item.maximo)) valid = issue(issues, `${path}.maximo`, "expected finite number");
    if (valid) rango_de_precio.push(item as ApiV2FiltersResponseDto["rango_de_precio"][number]);
  });
  const missingKeys = ["operacion", "tipo_propiedad", "precio", "localidad", "latitud"] as const;
  for (const key of missingKeys) {
    if (!nonNegativeInteger((value.sin_dato as Record<string, unknown>)[key])) {
      envelopeValid = issue(issues, `$.sin_dato.${key}`, "expected non-negative integer");
    }
  }
  if (!envelopeValid) return { success: false, issues };
  return {
    success: true,
    data: {
      contrato: API_V2_CONTRACT,
      filtros: { operacion, tipo_propiedad, moneda, area_nivel },
      rango_de_precio,
      sin_dato: value.sin_dato as ApiV2FiltersResponseDto["sin_dato"],
    },
    issues,
  };
}
