import type {
  Property,
  PropertyCurrency,
  PropertyOperation,
  PropertyType,
  QualitySignals,
  SupabaseProperty,
} from "@/types/property";
import { safeExternalUrl } from "@/lib/safe-url";

const blockedImages = [
  "static.tokkobroker.com/tfw/img/prop-icons",
  "/prop-icons",
  "/imgs/inmobiliaria",
  "mascara-galeria",
  "footer",
  "logo",
  "placeholder",
  "no-photo",
  "no_image",
  "sin-imagen",
  "sin_imagen",
];

export function cleanText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value.replace(/\s+/g, " ").trim();
}

function positiveNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

export function normalizeCurrency(value: unknown): PropertyCurrency | null {
  const normalized = cleanText(value).toUpperCase();
  if (normalized === "USD" || normalized.includes("DOLAR")) return "USD";
  if (normalized === "ARS" || normalized.includes("PESO ARG")) return "ARS";
  if (normalized === "EUR" || normalized.includes("EURO")) return "EUR";
  if (normalized === "UYU" || normalized.includes("PESO URU")) return "UYU";
  return null;
}

export function normalizeOperation(value: unknown): PropertyOperation {
  const normalized = cleanText(value).toLowerCase().replace(/\s+/g, "_");
  if (normalized.includes("venta_y_alquiler")) return "venta_y_alquiler";
  if (normalized.includes("tempor")) return "temporario";
  if (normalized.includes("alquiler")) return "alquiler";
  if (normalized.includes("venta")) return "venta";
  return "consultar";
}

export function normalizePropertyType(value: unknown): PropertyType {
  const normalized = cleanText(value).toLowerCase();
  if (normalized.includes("depart")) return "departamento";
  if (normalized.includes("casa")) return "casa";
  if (normalized === "ph" || normalized.includes("horizontal")) return "ph";
  if (normalized.includes("terreno") || normalized.includes("lote")) return "terreno";
  if (normalized.includes("oficina")) return "oficina";
  if (normalized.includes("local")) return "local";
  if (normalized.includes("cochera") || normalized.includes("garage")) return "cochera";
  if (normalized.includes("galp")) return "galpon";
  if (normalized.includes("campo") || normalized.includes("chacra")) return "campo";
  return "otro";
}

function validCoordinates(latitude: unknown, longitude: unknown) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -55.2 &&
    lat <= -21.7 &&
    lng >= -73.7 &&
    lng <= -53.5
  );
}

function validImage(value: unknown): value is string {
  const url = safeExternalUrl(value);
  if (!url) return false;
  const normalized = url.toLowerCase();
  return !blockedImages.some((pattern) => normalized.includes(pattern));
}

function qualitySignals(item: SupabaseProperty, images: string[]): QualitySignals {
  const title = cleanText(item.titulo);
  return {
    hasValidTitle:
      title.length >= 4 && !/^(propiedad|inmueble)\s+(sin\s+t[ií]tulo|en\s+(venta|alquiler))$/i.test(title),
    hasDescription: cleanText(item.descripcion).length >= 20,
    hasPrice: positiveNumber(item.precio) !== null,
    hasCurrency: normalizeCurrency(item.moneda) !== null,
    hasLocation: Boolean(cleanText(item.barrio) || cleanText(item.ciudad) || cleanText(item.provincia)),
    hasCoordinates: validCoordinates(item.latitud, item.longitud),
    hasImages: images.length > 0,
  };
}

export function mapSupabasePropertyToProperty(item: SupabaseProperty): Property {
  const images = Array.from(new Set((item.imagenes ?? []).filter(validImage)));
  const quality = qualitySignals(item, images);
  const rawType = cleanText(item.tipo_propiedad) || null;

  return {
    id: String(item.id),
    agencyId: item.inmobiliaria_id == null ? null : String(item.inmobiliaria_id),
    sourceUrl: safeExternalUrl(item.url),
    title: quality.hasValidTitle ? cleanText(item.titulo) : "Propiedad sin título",
    description: quality.hasDescription ? cleanText(item.descripcion) : null,
    price: positiveNumber(item.precio),
    currency: normalizeCurrency(item.moneda),
    priceUsd: positiveNumber(item.precio_usd),
    priceArs: positiveNumber(item.precio_ars),
    expenses: positiveNumber(item.expensas),
    expensesCurrency: normalizeCurrency(item.expensas_moneda),
    propertyType: normalizePropertyType(item.tipo_propiedad),
    rawPropertyType: rawType,
    operation: normalizeOperation(item.operacion),
    rooms: positiveNumber(item.ambientes),
    bedrooms: positiveNumber(item.dormitorios),
    bathrooms: positiveNumber(item.banos),
    toilettes: positiveNumber(item.toilettes),
    garages: positiveNumber(item.cocheras),
    age: positiveNumber(item.antiguedad),
    floor: positiveNumber(item.piso),
    totalArea: positiveNumber(item.superficie_total),
    coveredArea: positiveNumber(item.superficie_cubierta),
    landArea: positiveNumber(item.superficie_terreno),
    address: cleanText(item.direccion) || null,
    neighborhood: cleanText(item.barrio) || null,
    city: cleanText(item.ciudad) || null,
    province: cleanText(item.provincia) || null,
    country: cleanText(item.pais) || null,
    latitude: quality.hasCoordinates ? Number(item.latitud) : null,
    longitude: quality.hasCoordinates ? Number(item.longitud) : null,
    images,
    videoUrl: safeExternalUrl(item.video_url),
    floorPlanUrl: safeExternalUrl(item.plano_url),
    amenities: Array.from(new Set((item.amenities ?? []).map(cleanText).filter(Boolean))).slice(0, 24),
    agentName: cleanText(item.agente_nombre) || null,
    agentPhone: cleanText(item.agente_telefono) || null,
    publishedAt: item.fecha_publicacion,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    status: "activa",
    mortgageEligible: item.apto_credito === true,
    quality,
  };
}

