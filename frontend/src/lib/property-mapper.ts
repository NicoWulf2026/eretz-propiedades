import { displayableImages } from "@/lib/image-quality";
import type {
  Property,
  PropertyCurrency,
  PropertyOperation,
  PropertyStatus,
  PropertyType,
  QualitySignals,
  SupabaseProperty,
} from "@/types/property";
import { safeExternalUrl } from "@/lib/safe-url";
import { assessLocationConfidence, hasValidArgentinaCoordinates, type GeoPointStats } from "@/lib/geo-confidence";

// Preserva el estado real de scraping. No inventa disponibilidad: cualquier estado
// distinto de "activa" que el Quality Gate autorice se conserva como no confirmado.
export function normalizeStatus(estado: string | null | undefined): PropertyStatus {
  const value = (estado ?? "").trim().toLowerCase();
  if (value === "activa") return "activa";
  if (value === "no_detectada_en_ultimo_scraping") return "no_detectada_en_ultimo_scraping";
  return "desconocida";
}

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

function validImage(value: unknown): value is string {
  const url = safeExternalUrl(value);
  if (!url) return false;
  const normalized = url.toLowerCase();
  return !blockedImages.some((pattern) => normalized.includes(pattern));
}

function safeEmail(value: unknown): string | null {
  const email = cleanText(value).toLowerCase();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254 ? email : null;
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
    hasCoordinates: hasValidArgentinaCoordinates(item.latitud, item.longitud),
    hasImages: images.length > 0,
  };
}

export function mapSupabasePropertyToProperty(item: SupabaseProperty, pointStats?: GeoPointStats | null): Property {
  // `rawImages` conserva el dato de origen tal cual llegó. `images` es lo que se
  // muestra: se descartan los recursos que no representan la propiedad (tiles de
  // mapa, Open Graph del home, samples de theme, logos del publicador...), que el
  // histórico almacenó antes de que existiera el detector de ingesta. El frontend
  // no clasifica; recibe la lista ya depurada.
  const rawImages = Array.from(new Set((item.imagenes ?? []).filter(validImage)));
  const images = displayableImages(rawImages, cleanText(item.publisher_name) || null);
  const quality = qualitySignals(item, images);
  const rawType = cleanText(item.tipo_propiedad) || null;
  const normalizedTitle = cleanText(item.titulo).toLowerCase();
  const propertyType =
    normalizePropertyType(item.tipo_propiedad) === "cochera" &&
    normalizedTitle.includes("edificio comercial")
      ? "otro"
      : normalizePropertyType(item.tipo_propiedad);
  const locationConfidence = assessLocationConfidence({
    latitude: item.latitud,
    longitude: item.longitud,
    address: item.direccion,
    neighborhood: item.barrio,
    city: item.ciudad,
    province: item.provincia,
    pointStats,
  }).level;

  return {
    id: String(item.id),
    agencyId: item.inmobiliaria_id == null ? null : String(item.inmobiliaria_id),
    publisher: cleanText(item.publisher_name)
      ? {
          id: item.inmobiliaria_id == null ? null : String(item.inmobiliaria_id),
          name: cleanText(item.publisher_name),
          phone: cleanText(item.publisher_phone) || cleanText(item.agente_telefono) || null,
          email: safeEmail(item.publisher_email),
          website: safeExternalUrl(item.publisher_website),
          verified: typeof item.publisher_verified === "boolean" ? item.publisher_verified : null,
        }
      : cleanText(item.agente_nombre)
        ? {
            id: null,
            name: cleanText(item.agente_nombre),
            phone: cleanText(item.agente_telefono) || null,
            email: null,
            website: null,
            verified: null,
          }
        : null,
    sourceUrl: safeExternalUrl(item.url),
    title: quality.hasValidTitle ? cleanText(item.titulo) : "Propiedad sin título",
    description: quality.hasDescription ? cleanText(item.descripcion) : null,
    price: positiveNumber(item.precio),
    currency: normalizeCurrency(item.moneda),
    priceUsd: positiveNumber(item.precio_usd),
    priceArs: positiveNumber(item.precio_ars),
    expenses: positiveNumber(item.expensas),
    expensesCurrency: normalizeCurrency(item.expensas_moneda),
    propertyType,
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
    locationConfidence,
    images,
    videoUrl: safeExternalUrl(item.video_url),
    floorPlanUrl: safeExternalUrl(item.plano_url),
    amenities: Array.from(new Set((item.amenities ?? []).map(cleanText).filter(Boolean))).slice(0, 24),
    agentName: cleanText(item.agente_nombre) || null,
    agentPhone: cleanText(item.agente_telefono) || null,
    publishedAt: item.fecha_publicacion,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    status: normalizeStatus(item.estado),
    mortgageEligible: item.apto_credito === true,
    quality,
  };
}
