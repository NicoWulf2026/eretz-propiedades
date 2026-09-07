import {
  API_V2_CONTRACT,
  API_V2_RANKING,
  type ApiV2GeographyDto,
  type ApiV2PageDto,
  type ApiV2PropertyDto,
  type ApiV2RankingDto,
  type ApiV2SearchPageDto,
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

function nullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
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
  for (const key of ["id", "source_url", "agency_id"] as const) {
    if (typeof value[key] !== "string" || value[key].length === 0) valid = issue(issues, `${path}.${key}`, "expected non-empty string");
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
  if (!geography(value.geo, `${path}.geo`, issues)) valid = false;
  if (value.ranking !== undefined && !ranking(value.ranking, `${path}.ranking`, issues)) valid = false;
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
    if (value.ranking !== API_V2_RANKING) envelopeValid = issue(issues, "$.ranking", "unexpected ranking version");
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
    if (parsed.success && search && parsed.data.ranking === undefined) {
      issue(issues, `$.data[${index}].ranking`, "search result requires technical ranking");
    } else if (parsed.success) data.push(parsed.data);
    else issues.push(...parsed.issues);
  });
  const parsed = { ...value, data } as unknown as ApiV2PageDto | ApiV2SearchPageDto;
  return { success: true, data: parsed, issues };
}
