import { classify, scoreMatch, type Confidence, type DupCandidate } from "@/lib/duplicates";
import { describeSearch } from "@/lib/search-label";
import { parsePropertyFilters } from "@/lib/property-query";
import { operationLabels, propertyLocation, typeLabels } from "@/lib/property-presenter";
import type { Property, PropertySummary } from "@/types/property";

export type DetailFactGroup = {
  title: string;
  items: Array<{ label: string; value: string }>;
};

const integer = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

function present(value: number | null, suffix = ""): string | null {
  return value == null ? null : `${integer.format(value)}${suffix}`;
}

export function propertyDetailTitle(property: Pick<Property, "propertyType" | "neighborhood" | "city" | "province">): string {
  const location = propertyLocation(property);
  return location === "Ubicación no especificada"
    ? typeLabels[property.propertyType]
    : `${typeLabels[property.propertyType]} en ${location}`;
}

export function propertyReturnContext(returnTo: string): string | null {
  try {
    const url = new URL(returnTo, "https://eretz.local");
    const raw = Object.fromEntries(url.searchParams.entries());
    const label = describeSearch(parsePropertyFilters(raw));
    return label || null;
  } catch {
    return null;
  }
}

export function propertyDetailGroups(property: Property): DetailFactGroup[] {
  const main = [
    { label: "Operación", value: operationLabels[property.operation] },
    { label: "Tipo", value: typeLabels[property.propertyType] },
    property.rooms == null ? null : { label: "Ambientes", value: present(property.rooms)! },
    property.bedrooms == null ? null : { label: "Dormitorios", value: present(property.bedrooms)! },
    property.bathrooms == null ? null : { label: "Baños", value: present(property.bathrooms)! },
    property.toilettes == null ? null : { label: "Toilettes", value: present(property.toilettes)! },
    property.garages == null ? null : { label: "Cocheras", value: present(property.garages)! },
  ].filter((item): item is { label: string; value: string } => item !== null);

  const surfaces = [
    property.totalArea == null ? null : { label: "Superficie total", value: present(property.totalArea, " m²")! },
    property.coveredArea == null ? null : { label: "Superficie cubierta", value: present(property.coveredArea, " m²")! },
    property.landArea == null ? null : { label: "Terreno", value: present(property.landArea, " m²")! },
  ].filter((item): item is { label: string; value: string } => item !== null);

  const building = [
    property.age == null ? null : { label: "Antigüedad", value: `${integer.format(property.age)} años` },
    property.floor == null ? null : { label: "Piso", value: present(property.floor)! },
    property.mortgageEligible == null ? null : { label: "Apto crédito", value: property.mortgageEligible ? "Sí" : "No" },
  ].filter((item): item is { label: string; value: string } => item !== null);

  const groups: DetailFactGroup[] = [{ title: "Características", items: main }];
  if (surfaces.length) groups.push({ title: "Superficies", items: surfaces });
  if (building.length) groups.push({ title: "Propiedad", items: building });
  return groups.filter((group) => group.items.length > 0);
}

function duplicateCandidate(property: Property | PropertySummary): DupCandidate {
  return {
    id: property.id,
    operation: property.operation,
    propertyType: property.propertyType,
    city: property.city,
    neighborhood: property.neighborhood,
    address: property.address,
    price: property.price,
    currency: property.currency,
    totalArea: property.totalArea,
    latitude: property.latitude,
    longitude: property.longitude,
    title: property.title,
  };
}

export function publicationMatchConfidence(property: Property, other: PropertySummary): Confidence {
  return classify(scoreMatch(duplicateCandidate(property), duplicateCandidate(other)));
}
