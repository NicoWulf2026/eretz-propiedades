"use client";

import { activeChips } from "@/components/explorer/ActiveChips";
import { filtersToSearchParams } from "@/lib/property-query";
import type { PropertyFilters } from "@/types/property";

function reset(filters: PropertyFilters, patch: Partial<PropertyFilters>): PropertyFilters {
  return { ...filters, ...patch, page: 1, cursor: "", direction: "next" };
}
function href(basePath: string, filters: PropertyFilters) {
  const search = filtersToSearchParams(filters).toString();
  return `${basePath}${search ? `?${search}` : ""}`;
}

// Fase H: acciones de "sin resultados" — sólo se muestran cuando aplican.
export function NoResults({ filters, basePath = "/" }: { filters: PropertyFilters; basePath?: string }) {
  const chips = activeChips(filters);
  const last = chips[chips.length - 1];
  const hasPrice = filters.minPrice !== null || filters.maxPrice !== null;
  const hasLocation = Boolean(filters.neighborhood || filters.city || filters.province);
  const widenLocation: Partial<PropertyFilters> = filters.neighborhood
    ? { neighborhood: "" }
    : filters.city
      ? { city: "" }
      : { province: "" };
  const hasViewport = Boolean(filters.viewport);
  const anything = chips.length > 0 || hasViewport;
  return (
    <div className="state-panel">
      <span aria-hidden="true">⌕</span>
      <h2>No encontramos propiedades</h2>
      <p>{anything ? "Probá ampliar la búsqueda con estas opciones." : "Todavía no hay propiedades públicas para mostrar."}</p>
      <div className="state-actions">
        {last ? <a className="secondary-button" href={href(basePath, last.next)}>Quitar “{last.label}”</a> : null}
        {hasPrice ? <a className="secondary-button" href={href(basePath, reset(filters, { minPrice: null, maxPrice: null }))}>Ampliar precio</a> : null}
        {hasLocation ? <a className="secondary-button" href={href(basePath, reset(filters, widenLocation))}>Ampliar ubicación</a> : null}
        {hasViewport ? <a className="secondary-button" href={href(basePath, reset(filters, { viewport: null }))}>Quitar filtro del mapa</a> : null}
        {anything ? <a className="primary-button" href={basePath}>Limpiar todos</a> : null}
      </div>
    </div>
  );
}
