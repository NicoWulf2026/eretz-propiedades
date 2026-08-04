import { operationLabels, propertyLocation, propertyPrice, typeLabels } from "@/lib/property-presenter";
import type { Property } from "@/types/property";

export function propertyShareMessage(property: Property, url: string) {
  const facts = [
    `${typeLabels[property.propertyType]} en ${operationLabels[property.operation].toLowerCase()}`,
    propertyPrice(property),
    property.rooms ? `${property.rooms} ambiente${property.rooms === 1 ? "" : "s"}` : null,
    property.bedrooms ? `${property.bedrooms} dormitorio${property.bedrooms === 1 ? "" : "s"}` : null,
    property.totalArea ? `${Intl.NumberFormat("es-AR").format(property.totalArea)} m²` : null,
    propertyLocation(property),
    property.publisher?.name ? `Publica ${property.publisher.name}` : null,
  ].filter(Boolean);
  return `${facts.join(" · ")} — ${url}`;
}

export function contactMessage(property: Property, url: string) {
  return `Hola, consulto por esta propiedad que vi en ERETZ: ${propertyShareMessage(property, url)}`;
}

