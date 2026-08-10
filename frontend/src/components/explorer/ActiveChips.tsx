"use client";

import { filtersToSearchParams } from "@/lib/property-query";
import type { PropertyFilters } from "@/types/property";

const OPERATION_LABELS: Record<string, string> = {
  venta: "Comprar", alquiler: "Alquilar", temporario: "Temporario",
  venta_y_alquiler: "Venta y alquiler", consultar: "Consultar",
};
const TYPE_LABELS: Record<string, string> = {
  departamento: "Departamento", casa: "Casa", ph: "PH", terreno: "Terreno",
  oficina: "Oficina", local: "Local", cochera: "Cochera", galpon: "Galpón",
  campo: "Campo", otro: "Otro",
};

type Chip = { key: string; label: string; next: PropertyFilters };

// Quitar un chip conserva el resto de los filtros y reinicia el cursor.
function reset(filters: PropertyFilters, patch: Partial<PropertyFilters>): PropertyFilters {
  return { ...filters, ...patch, page: 1, cursor: "", direction: "next" };
}

export function activeChips(filters: PropertyFilters): Chip[] {
  const chips: Chip[] = [];
  const num = (v: number) => v.toLocaleString("es-AR");
  if (filters.q) chips.push({ key: "q", label: `"${filters.q}"`, next: reset(filters, { q: "" }) });
  if (filters.operation) chips.push({ key: "op", label: OPERATION_LABELS[filters.operation] ?? filters.operation, next: reset(filters, { operation: "" }) });
  if (filters.propertyType) chips.push({ key: "tipo", label: TYPE_LABELS[filters.propertyType] ?? filters.propertyType, next: reset(filters, { propertyType: "" }) });
  if (filters.province) chips.push({ key: "prov", label: filters.province, next: reset(filters, { province: "" }) });
  if (filters.city) chips.push({ key: "city", label: filters.city, next: reset(filters, { city: "" }) });
  if (filters.neighborhood) chips.push({ key: "barrio", label: filters.neighborhood, next: reset(filters, { neighborhood: "" }) });
  // Cada ubicación se puede quitar individualmente (semántica OR).
  filters.locations.forEach((loc, index) => chips.push({
    key: `ubi-${index}`,
    label: loc,
    next: reset(filters, { locations: filters.locations.filter((_, i) => i !== index) }),
  }));
  if (filters.publisher) chips.push({ key: "pub", label: filters.publisher, next: reset(filters, { publisher: "" }) });
  if (filters.currency) chips.push({ key: "mon", label: filters.currency, next: reset(filters, { currency: "" }) });
  if (filters.minPrice !== null) chips.push({ key: "pmin", label: `Desde ${num(filters.minPrice)}`, next: reset(filters, { minPrice: null }) });
  if (filters.maxPrice !== null) chips.push({ key: "pmax", label: `Hasta ${num(filters.maxPrice)}`, next: reset(filters, { maxPrice: null }) });
  if (filters.minRooms !== null) chips.push({ key: "amb", label: `${filters.minRooms}+ amb.`, next: reset(filters, { minRooms: null }) });
  if (filters.minBedrooms !== null) chips.push({ key: "dorm", label: `${filters.minBedrooms}+ dorm.`, next: reset(filters, { minBedrooms: null }) });
  if (filters.minBathrooms !== null) chips.push({ key: "ban", label: `${filters.minBathrooms}+ baños`, next: reset(filters, { minBathrooms: null }) });
  if (filters.minArea !== null) chips.push({ key: "amin", label: `Sup. ${filters.minArea}+ m²`, next: reset(filters, { minArea: null }) });
  if (filters.maxArea !== null) chips.push({ key: "amax", label: `Sup. ≤ ${filters.maxArea} m²`, next: reset(filters, { maxArea: null }) });
  if (filters.recentDays !== null) chips.push({ key: "rec", label: `Últimos ${filters.recentDays} días`, next: reset(filters, { recentDays: null }) });
  if (filters.hasImages) chips.push({ key: "img", label: "Con imágenes", next: reset(filters, { hasImages: false }) });
  if (filters.priceMode === "with") chips.push({ key: "prc", label: "Con precio", next: reset(filters, { priceMode: "" }) });
  if (filters.priceMode === "consult") chips.push({ key: "prc", label: "A consultar", next: reset(filters, { priceMode: "" }) });
  if (filters.hasLocation) chips.push({ key: "loc", label: "Con ubicación", next: reset(filters, { hasLocation: false }) });
  if (filters.mortgageState === "si") chips.push({ key: "cred", label: "Apto crédito", next: reset(filters, { mortgageState: "" }) });
  if (filters.mortgageState === "no") chips.push({ key: "cred", label: "No apto crédito", next: reset(filters, { mortgageState: "" }) });
  if (filters.mortgageState === "sininfo") chips.push({ key: "cred", label: "Crédito sin información", next: reset(filters, { mortgageState: "" }) });
  if (filters.near) chips.push({ key: "near", label: "Cerca de un punto", next: reset(filters, { near: null, sort: filters.sort === "nearest" ? "recent" : filters.sort }) });
  // Cada zona del mapa (rectángulo/radio) se puede quitar individualmente.
  filters.zones.forEach((zone, index) => chips.push({
    key: `zona-${index}`,
    label: zone.kind === "radius" ? `Radio ${zone.km} km` : "Zona del mapa",
    next: reset(filters, { zones: filters.zones.filter((_, i) => i !== index) }),
  }));
  return chips;
}

export function ActiveChips({ filters, basePath = "/", onRemoveViewport }: { filters: PropertyFilters; basePath?: string; onRemoveViewport?: () => void }) {
  const chips = activeChips(filters);
  const hasViewport = Boolean(filters.viewport);
  if (!chips.length && !hasViewport) return null;
  const href = (f: PropertyFilters) => {
    const search = filtersToSearchParams(f).toString();
    return `${basePath}${search ? `?${search}` : ""}`;
  };
  const total = chips.length + (hasViewport ? 1 : 0);
  return (
    <div className="active-chips" role="group" aria-label="Filtros activos">
      {chips.map((chip) => (
        <a key={chip.key} className="chip" href={href(chip.next)}>
          <span>{chip.label}</span>
          <span aria-hidden="true"> ×</span>
          <span className="sr-only"> — quitar filtro</span>
        </a>
      ))}
      {hasViewport ? (
        <button type="button" className="chip chip-viewport" onClick={onRemoveViewport}>
          <span>Zona del mapa aplicada</span>
          <span aria-hidden="true"> ×</span>
          <span className="sr-only"> — quitar filtro del mapa</span>
        </button>
      ) : null}
      {total > 1 ? <a className="chip chip-clear" href={basePath}>Limpiar todos</a> : null}
    </div>
  );
}
