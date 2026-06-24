import type {
  Property,
  PropertyCurrency,
  PropertyOperation,
  PropertyStatus,
  PropertyType,
  SupabaseProperty,
} from "@/types/property";

const tokkoIconPath = "static.tokkobroker.com/tfw/img/prop-icons";
const sourceAgencyByDomain: Record<string, string> = {
  "inmobiliariamendocasa.com.ar": "Mendocasa Lavalle",
  "pagliaropropiedades.com.ar": "Juan I. Pagliaro Propiedades",
  "svestudioinmobiliario.com.ar": "SV Inmobiliaria",
};

const blockedImagePatterns = [
  tokkoIconPath,
  "/prop-icons",
  "/imgs/inmobiliaria",
  "inmobiliaria-",
  "mascara-galeria",
  "rounded-cds",
  "footer",
  "logo",
  "tour",
  "virtual",
  "placeholder",
  "no-photo",
  "no_image",
  "sin-imagen",
  "sin_imagen",
];

function cleanText(value: string | null | undefined) {
  if (!value) {
    return "";
  }

  return value
    .replace(/Apto crÃ©dito/g, "Apto cr\u00e9dito")
    .replace(/Propiedad sin tÃ­tulo/g, "Propiedad sin t\u00edtulo")
    .replace(/Propiedad sin tÃtulo/g, "Propiedad sin t\u00edtulo")
    .replace(/Ã¡/g, "a")
    .replace(/Ã©/g, "e")
    .replace(/Ã­/g, "i")
    .replace(/Ã³/g, "o")
    .replace(/Ãº/g, "u")
    .replace(/Ã±/g, "n")
    .replace(/Ã/g, "A")
    .replace(/Ã‰/g, "E")
    .replace(/Ã/g, "I")
    .replace(/Ã“/g, "O")
    .replace(/Ãš/g, "U")
    .replace(/Ã‘/g, "N")
    .trim();
}

function toStringOrNull(value: string | number | null | undefined) {
  return value === null || value === undefined ? null : String(value);
}

function toNumberOrNull(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsedValue = Number(value);

  return Number.isFinite(parsedValue) ? parsedValue : null;
}

function getHostname(value: string | null | undefined) {
  if (!value) {
    return "";
  }

  try {
    const url = value.startsWith("http") ? value : `https://${value}`;
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return "";
  }
}

function getSourceAgencyName(item: SupabaseProperty) {
  const sourceHostname = getHostname(item.url);

  return sourceAgencyByDomain[sourceHostname] ?? null;
}

function isValidPropertyImage(imageUrl: string | null | undefined) {
  if (!imageUrl) {
    return false;
  }

  const normalizedUrl = imageUrl.toLowerCase();

  const isBlockedFallback = blockedImagePatterns.some((pattern) =>
    normalizedUrl.includes(pattern),
  );
  const isBlocked360Image = /(?:^|[\/_.-])360(?:[\/_.-]|$)/.test(normalizedUrl);

  return !isBlockedFallback && !isBlocked360Image;
}

function buildImages(item: SupabaseProperty) {
  const safeImages = [
    item.imagen_principal_real,
    ...(item.imagenes ?? []),
  ].filter((imageUrl): imageUrl is string => isValidPropertyImage(imageUrl));

  const uniqueImages = Array.from(new Set(safeImages));

  return uniqueImages;
}

function buildBadges(item: SupabaseProperty): string[] {
  const badges = new Set<string>();

  if (item.apto_credito) {
    badges.add("Apto cr\u00e9dito");
  }

  if ((item.cocheras ?? 0) > 0) {
    badges.add("Cochera");
  }

  item.amenities?.slice(0, 2).forEach((amenity) => {
    const cleanAmenity = cleanText(amenity);
    if (cleanAmenity) {
      badges.add(cleanAmenity);
    }
  });

  return Array.from(badges);
}

function normalizeText(value: string | null) {
  return cleanText(value).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function normalizeCurrency(value: string | null): PropertyCurrency {
  return normalizeText(value).includes("ars") || normalizeText(value).includes("pesos")
    ? "ARS"
    : "USD";
}

function normalizeNullableCurrency(value: string | null): PropertyCurrency | null {
  return value ? normalizeCurrency(value) : null;
}

function normalizeOperation(value: string | null): PropertyOperation {
  const operation = normalizeText(value);

  // venta_y_alquiler debe chequearse antes de "alquiler" y "venta" por separado
  if (operation.includes("venta_y_alquiler") || operation === "venta y alquiler") {
    return "venta_y_alquiler";
  }

  if (operation.includes("alquiler")) {
    return "alquiler";
  }

  if (operation.includes("tempor")) {
    return "temporario";
  }

  if (operation.includes("inver")) {
    return "inversion";
  }

  if (operation.includes("consultar") || operation === "consultar") {
    return "consultar";
  }

  if (operation.includes("venta")) {
    return "venta";
  }

  // Operacion desconocida: se guarda como "consultar" (Decision 22)
  return "consultar";
}

function normalizePropertyType(value: string | null): PropertyType {
  const propertyType = normalizeText(value);

  if (propertyType.includes("depart")) {
    return "departamento";
  }

  if (propertyType.includes("casa")) {
    return "casa";
  }

  if (propertyType === "ph" || propertyType.includes("propiedad horizontal")) {
    return "ph";
  }

  if (propertyType.includes("terreno") || propertyType.includes("lote")) {
    return "terreno";
  }

  if (propertyType.includes("oficina")) {
    return "oficina";
  }

  if (propertyType.includes("local")) {
    return "local";
  }

  return "otro";
}

function normalizeStatus(value: string | null): PropertyStatus {
  const status = normalizeText(value);

  if (status.includes("paus")) {
    return "pausada";
  }

  if (status.includes("reserv")) {
    return "reservada";
  }

  // "vendida" debe chequearse antes de "no_detectada" para evitar falso positivo
  if (status === "vendida" || (status.includes("vend") && !status.includes("no_detect"))) {
    return "vendida";
  }

  if (status.includes("alquil")) {
    return "alquilada";
  }

  if (status.includes("no_detect") || status.includes("no detect")) {
    return "no_detectada_en_ultimo_scraping";
  }

  if (status.includes("descon")) {
    return "desconocida";
  }

  return "activa";
}

export function mapSupabasePropertyToProperty(item: SupabaseProperty): Property {
  const images = buildImages(item);
  // Sprint F: tiene_imagen_real solo en la view; si no está presente, usar images.length > 0
  const hasRealImage = images.length > 0 && (item.tiene_imagen_real ?? images.length > 0);

  return {
    id: String(item.id),
    agencyId: toStringOrNull(item.inmobiliaria_id),
    sourceUrl: item.url ?? "",
    externalId: null,
    dedupHash: null,
    title: cleanText(item.titulo) || "Propiedad sin t\u00edtulo",
    description: cleanText(item.descripcion),
    price: item.precio ?? 0,
    currency: normalizeCurrency(item.moneda),
    priceUsd: item.precio_usd,
    priceArs: item.precio_ars,
    expenses: item.expensas,
    expensesCurrency: normalizeNullableCurrency(item.expensas_moneda),
    propertyType: normalizePropertyType(item.tipo_propiedad),
    operation: normalizeOperation(item.operacion),
    rooms: item.ambientes ?? 0,
    bedrooms: item.dormitorios ?? 0,
    bathrooms: item.banos ?? 0,
    toilettes: item.toilettes ?? 0,
    garages: item.cocheras ?? 0,
    age: item.antiguedad,
    floor: toNumberOrNull(item.piso),
    totalArea: item.superficie_total ?? 0,
    coveredArea: item.superficie_cubierta ?? 0,
    landArea: item.superficie_terreno,
    address: cleanText(item.direccion),
    neighborhood: cleanText(item.barrio),
    // Sprint F: ciudad_final/provincia_final solo presentes al queryar la view;
    // ciudad/provincia son columnas directas de propiedades (fallback principal).
    city: cleanText(item.ciudad_final ?? item.ciudad),
    province: cleanText(item.provincia_final ?? item.provincia),
    country: item.pais ?? "Argentina",
    latitude: item.latitud,
    longitude: item.longitud,
    images,
    hasRealImage,
    videoUrl: item.video_url,
    floorPlanUrl: item.plano_url,
    amenities: item.amenities?.map(cleanText).filter(Boolean) ?? [],
    agencyName:
      getSourceAgencyName(item) ||
      cleanText(item.inmobiliaria_nombre) ||
      "InmoCapital",
    agencyWeb: item.inmobiliaria_web ?? null,
    agencyPhone: item.inmobiliaria_telefono ?? null,
    agencyEmail: item.inmobiliaria_email ?? null,
    agentName: cleanText(item.agente_nombre) || null,
    agentPhone: item.agente_telefono,
    extractionSource: item.fuente_extraccion,
    originCms: item.cms_origen,
    publishedAt: item.fecha_publicacion,
    createdAt: item.created_at ?? "",
    updatedAt: item.updated_at ?? "",
    status: normalizeStatus(item.estado),
    mortgageEligible: item.apto_credito ?? false,
    badges: buildBadges(item),
  };
}
