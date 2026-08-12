import type { PropertyFilters } from "@/types/property";

// Agrupación de los filtros avanzados del explorador. Los grupos salen de los
// campos que ya existen en el panel: no se inventan categorías nuevas ni se
// agregan filtros. El contador por grupo permite ver de un vistazo dónde quedó
// algo aplicado sin abrir los cuatro bloques.
export type FilterGroupId = "ubicacion" | "precio" | "caracteristicas" | "publicacion";

export const FILTER_GROUPS: ReadonlyArray<{ id: FilterGroupId; label: string; hint: string }> = [
  { id: "ubicacion", label: "Ubicación", hint: "Provincia, ciudad y zonas" },
  { id: "precio", label: "Precio", hint: "Moneda y rango de precio" },
  { id: "caracteristicas", label: "Características", hint: "Ambientes, superficie, fotos" },
  { id: "publicacion", label: "Publicación", hint: "Publicador, antigüedad, orden" },
];

// Un filtro cuenta como activo cuando el usuario fijó un valor. Los vacíos
// ("" / null / undefined / false) y los valores por defecto no suman.
function on(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.length > 0;
  return false;
}

// Cuenta filtros activos por grupo. Devuelve siempre las cuatro claves; la UI
// decide no mostrar el contador cuando vale 0.
export function filterGroupCounts(filters: PropertyFilters): Record<FilterGroupId, number> {
  const counts: Record<FilterGroupId, number> = {
    ubicacion: 0, precio: 0, caracteristicas: 0, publicacion: 0,
  };

  for (const value of [filters.province, filters.city, filters.neighborhood, filters.locations]) {
    if (on(value)) counts.ubicacion += 1;
  }
  // "Cerca de" es un filtro de ubicación aunque no tenga campo de texto propio.
  if (filters.near) counts.ubicacion += 1;

  for (const value of [filters.currency, filters.minPrice, filters.maxPrice, filters.priceMode]) {
    if (on(value)) counts.precio += 1;
  }

  for (const value of [
    filters.minRooms, filters.minBedrooms, filters.minBathrooms,
    filters.minArea, filters.maxArea, filters.hasLocation, filters.hasImages,
  ]) {
    if (on(value)) counts.caracteristicas += 1;
  }

  if (on(filters.publisher)) counts.publicacion += 1;
  if (on(filters.recentDays)) counts.publicacion += 1;
  // "recent" es el orden por defecto: sólo cuenta si el usuario eligió otro.
  if (on(filters.sort) && filters.sort !== "recent") counts.publicacion += 1;

  return counts;
}

export function totalGroupCount(filters: PropertyFilters): number {
  return Object.values(filterGroupCounts(filters)).reduce((sum, n) => sum + n, 0);
}
