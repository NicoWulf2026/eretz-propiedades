import type { Property, PropertyOperation, PropertyStatus, PropertyType } from "@/types/property";

// Sólo "activa" es disponibilidad confirmada. El resto (autorizado por el Quality
// Gate) se muestra con una indicación neutral, sin afirmar vigencia.
export function isAvailabilityConfirmed(status: PropertyStatus) {
  return status === "activa";
}

export function availabilityLabel(status: PropertyStatus): string | null {
  return isAvailabilityConfirmed(status) ? null : "Disponibilidad no confirmada";
}

export const operationLabels: Record<PropertyOperation, string> = {
  venta: "Venta",
  alquiler: "Alquiler",
  temporario: "Alquiler temporario",
  consultar: "Consultar",
  venta_y_alquiler: "Venta y alquiler",
};

export const typeLabels: Record<PropertyType, string> = {
  departamento: "Departamento",
  casa: "Casa",
  ph: "PH",
  terreno: "Terreno",
  oficina: "Oficina",
  local: "Local",
  cochera: "Cochera",
  galpon: "Galpón",
  campo: "Campo",
  otro: "Propiedad",
};

export const UNTITLED_PROPERTY = "Propiedad sin título";

const operationPhrases: Partial<Record<PropertyOperation, string>> = {
  venta: "en venta",
  alquiler: "en alquiler",
  temporario: "en alquiler temporario",
  venta_y_alquiler: "en venta y alquiler",
};

// Política P9: sin título publicado se compone «{tipo} en {operación} · {localidad}»
// sólo con datos reales, o la combinación parcial disponible. «otro» y «consultar»
// son también lo que se escribe cuando NO hay dato, así que no se afirman.
// Sin nada real: «Propiedad sin título». La verdad sobre el título publicado sigue
// en `quality.hasValidTitle`; esto es sólo presentación.
export function derivedTitle(property: {
  propertyType: PropertyType;
  operation: PropertyOperation;
  city?: string | null;
  neighborhood?: string | null;
}) {
  const type = property.propertyType === "otro" ? null : typeLabels[property.propertyType];
  const operation = operationPhrases[property.operation] ?? null;
  const place = property.city?.trim() || property.neighborhood?.trim() || null;
  if (!type && !operation && !place) return UNTITLED_PROPERTY;
  const head = [type ?? "Propiedad", operation].filter(Boolean).join(" ");
  return place ? `${head} · ${place}` : head;
}

const money = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export function propertyPrice(property: Pick<Property, "price" | "currency">) {
  if (property.price === null || !property.currency) return "Precio a consultar";
  return `${property.currency} ${money.format(property.price)}`;
}

export function propertyLocation(property: Pick<Property, "neighborhood" | "city" | "province"> & Pick<Partial<Property>, "municipality" | "department">) {
  const values = [property.neighborhood, property.city, property.municipality, property.department, property.province].filter(
    (value, index, all): value is string => Boolean(value) && all.indexOf(value) === index,
  );
  return values.length ? values.join(", ") : "Ubicación no especificada";
}

export function propertySpecs(property: Pick<Property, "rooms" | "bedrooms" | "bathrooms" | "garages" | "totalArea" | "coveredArea">) {
  const specs: string[] = [];
  if (property.rooms !== null) specs.push(`${property.rooms} amb.`);
  if (property.bedrooms !== null) specs.push(`${property.bedrooms} dorm.`);
  if (property.bathrooms !== null) specs.push(`${property.bathrooms} baño${property.bathrooms === 1 ? "" : "s"}`);
  if (property.garages !== null) specs.push(`${property.garages} coch.`);
  if (property.totalArea !== null) specs.push(`${money.format(property.totalArea)} m² tot.`);
  else if (property.coveredArea !== null) specs.push(`${money.format(property.coveredArea)} m² cub.`);
  return specs;
}

export function formatDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}
