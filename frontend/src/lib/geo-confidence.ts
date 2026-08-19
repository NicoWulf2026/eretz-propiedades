import type { LocationConfidence } from "@/types/property";

export type AddressQuality = "street_number" | "street" | "development" | "locality" | "insufficient";

export type GeoPointStats = {
  propertyCount: number;
  addressCount: number;
  cityCount: number;
  provinceCount: number;
  agencyCount: number;
};

export type GeoConfidenceInput = {
  latitude: number | null | undefined;
  longitude: number | null | undefined;
  address: string | null | undefined;
  neighborhood: string | null | undefined;
  city: string | null | undefined;
  province: string | null | undefined;
  pointStats?: GeoPointStats | null;
};

export type GeoConfidenceAssessment = {
  level: LocationConfidence;
  score: number;
  addressQuality: AddressQuality;
  reasons: string[];
};

const DEVELOPMENT_PATTERN = /\b(barrio|country|club de campo|urbanizaci[oó]n|loteo|chacras|haras|nordelta)\b/iu;
const NAVIGATION_NOISE_PATTERN = /\b(inicio|propiedades|tasaciones|qui[eé]nes somos|contacto)\b.*\b(inicio|propiedades|tasaciones|contacto)\b/iu;
const STREET_NUMBER_PATTERN = /\p{L}[^0-9]{0,80}[0-9]{1,5}(?:[^0-9]|$)/u;

function normalized(value: string | null | undefined) {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

export function hasValidArgentinaCoordinates(latitude: unknown, longitude: unknown) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lng)
    && lat >= -55.2 && lat <= -21.7
    && lng >= -73.7 && lng <= -53.5;
}

export function classifyAddressQuality(
  address: string | null | undefined,
  city?: string | null,
  province?: string | null,
): AddressQuality {
  const value = normalized(address);
  const lowered = value.toLocaleLowerCase("es-AR");
  if (value.length < 5 || value.length > 180 || NAVIGATION_NOISE_PATTERN.test(lowered)) return "insufficient";
  if (DEVELOPMENT_PATTERN.test(lowered)) return "development";
  const localityValues = [city, province]
    .map((item) => normalized(item).toLocaleLowerCase("es-AR"))
    .filter(Boolean);
  if (localityValues.includes(lowered)) return "locality";
  if (STREET_NUMBER_PATTERN.test(value)) return "street_number";
  if (/\p{L}/u.test(value) && value.split(/\s+/).length >= 2) return "street";
  return "insufficient";
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

/**
 * Heurística conservadora y determinista. El número sólo sirve para explicar y
 * testear las reglas internas: la interfaz pública comunica categorías, no una
 * falsa precisión científica.
 */
export function assessLocationConfidence(input: GeoConfidenceInput): GeoConfidenceAssessment {
  const addressQuality = classifyAddressQuality(input.address, input.city, input.province);
  if (!hasValidArgentinaCoordinates(input.latitude, input.longitude)) {
    return { level: "none", score: 0, addressQuality, reasons: ["missing_or_invalid_coordinates"] };
  }

  const reasons: string[] = [];
  let score = 45;
  score += ({ street_number: 25, street: 12, development: 8, locality: 3, insufficient: -12 })[addressQuality];
  if (normalized(input.city)) score += 5;
  if (normalized(input.province)) score += 5;
  if (normalized(input.neighborhood)) score += 3;

  const stats = input.pointStats;
  if (!stats) {
    reasons.push("point_statistics_unavailable");
    return { level: "approximate", score: clampScore(score), addressQuality, reasons };
  }

  score += stats.propertyCount <= 3 ? 10
    : stats.propertyCount <= 9 ? 6
      : stats.propertyCount <= 49 ? 0
        : stats.propertyCount <= 199 ? -6
          : stats.propertyCount <= 499 ? -12 : -25;
  score += stats.addressCount <= 1 ? 5
    : stats.addressCount <= 5 ? 0
      : stats.addressCount <= 9 ? -5
        : stats.addressCount <= 24 ? -15 : -25;
  if (stats.cityCount > 1) score -= 25;
  if (stats.provinceCount > 1) score -= 30;
  score = clampScore(score);

  if (stats.provinceCount > 1) reasons.push("conflicting_provinces");
  if (stats.cityCount > 1) reasons.push("conflicting_cities");
  if (stats.propertyCount >= 500) reasons.push("extreme_point_reuse");
  if (stats.addressCount >= 10) reasons.push("many_addresses_at_point");
  if (addressQuality === "insufficient") reasons.push("insufficient_address");

  const doubtful = stats.provinceCount > 1
    || stats.cityCount >= 3
    || stats.propertyCount >= 500
    || (stats.propertyCount >= 200 && (stats.addressCount >= 5 || stats.agencyCount >= 10))
    || (addressQuality === "insufficient" && stats.addressCount >= 10)
    || score < 30;
  if (doubtful) return { level: "doubtful", score, addressQuality, reasons };

  const high = score >= 80
    && addressQuality === "street_number"
    && Boolean(normalized(input.city))
    && Boolean(normalized(input.province))
    && stats.propertyCount <= 49
    && stats.cityCount <= 1
    && stats.provinceCount <= 1;
  return { level: high ? "high" : "approximate", score, addressQuality, reasons };
}

export function locationConfidenceLabel(level: LocationConfidence) {
  if (level === "high") return "Ubicación";
  if (level === "approximate") return "Ubicación aproximada";
  if (level === "doubtful") return "Ubicación dudosa";
  return "Sin ubicación en mapa";
}

export function locationConfidenceDescription(level: LocationConfidence) {
  if (level === "high") return "La publicación aporta una dirección completa y señales geográficas consistentes.";
  if (level === "approximate") return "La ubicación mostrada es orientativa y puede representar una zona general.";
  if (level === "doubtful") return "La coordenada disponible presenta señales inconsistentes. Confirmá la ubicación con el anunciante.";
  return "El anunciante no informó una ubicación cartográfica utilizable.";
}
