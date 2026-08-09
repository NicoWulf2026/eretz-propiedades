import { operationLabels, typeLabels } from "@/lib/property-presenter";
import type { PropertyFilters } from "@/types/property";

// Etiqueta legible de una búsqueda para "búsquedas recientes". Devuelve "" cuando
// no hay ningún filtro significativo, de modo que la vista por defecto no se
// registra como búsqueda.
export function describeSearch(filters: PropertyFilters): string {
  const parts: string[] = [];
  if (filters.q) parts.push(`“${filters.q}”`);
  if (filters.operation) parts.push(operationLabels[filters.operation]);
  if (filters.propertyType) parts.push(typeLabels[filters.propertyType]);
  const place = [filters.neighborhood, filters.city, filters.province].find(Boolean);
  if (place) parts.push(`en ${place}`);
  const cur = filters.currency ? `${filters.currency} ` : "";
  const min = filters.minPrice != null ? `${cur}${filters.minPrice.toLocaleString("es-AR")}` : null;
  const max = filters.maxPrice != null ? `${cur}${filters.maxPrice.toLocaleString("es-AR")}` : null;
  if (min && max) parts.push(`${min}–${max}`);
  else if (min) parts.push(`desde ${min}`);
  else if (max) parts.push(`hasta ${max}`);
  return parts.join(" · ");
}
