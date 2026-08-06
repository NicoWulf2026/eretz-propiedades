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

const money = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export function propertyPrice(property: Pick<Property, "price" | "currency">) {
  if (!property.price || !property.currency) return "Precio a consultar";
  return `${property.currency} ${money.format(property.price)}`;
}

export function propertyLocation(property: Pick<Property, "neighborhood" | "city" | "province">) {
  const values = [property.neighborhood, property.city, property.province].filter(
    (value, index, all): value is string => Boolean(value) && all.indexOf(value) === index,
  );
  return values.length ? values.join(", ") : "Ubicación no especificada";
}

export function propertySpecs(property: Pick<Property, "rooms" | "bedrooms" | "bathrooms" | "garages" | "totalArea" | "coveredArea">) {
  const specs: string[] = [];
  if (property.rooms) specs.push(`${property.rooms} amb.`);
  if (property.bedrooms) specs.push(`${property.bedrooms} dorm.`);
  if (property.bathrooms) specs.push(`${property.bathrooms} baño${property.bathrooms > 1 ? "s" : ""}`);
  if (property.garages) specs.push(`${property.garages} coch.`);
  if (property.totalArea) specs.push(`${money.format(property.totalArea)} m² tot.`);
  else if (property.coveredArea) specs.push(`${money.format(property.coveredArea)} m² cub.`);
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
