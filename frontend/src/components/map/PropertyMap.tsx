"use client";

import dynamic from "next/dynamic";
import type { PropertyFilters, PropertySummary } from "@/types/property";
import { filtersToSearchParams } from "@/lib/property-query";

const Leaflet = dynamic(
  () => import("@/components/map/PropertyLeafletMap").then((module) => module.PropertyLeafletMap),
  { ssr: false, loading: () => <div className="map-loading" role="status">Cargando mapa…</div> },
);

type Props = {
  properties: PropertySummary[];
  filters: PropertyFilters;
  selectedId?: string;
  onSelect?: (id: string) => void;
  label?: string;
  returnTo?: string;
};

export function PropertyMap({ properties, filters, selectedId = "", onSelect, label = "Mapa de resultados", returnTo = "/" }: Props) {
  const baseFilters = { ...filters, cursor: "", page: 1, direction: "next" as const, viewport: null };
  return (
    <section aria-label={label} className="property-map-shell">
      <Leaflet
        properties={properties}
        baseSearch={filtersToSearchParams(baseFilters).toString()}
        initialViewport={filters.viewport}
        selectedId={selectedId}
        onSelect={onSelect}
        returnTo={returnTo}
      />
      <p id="map-alternative" className="sr-only">Todos los resultados del mapa también están disponibles en el listado de propiedades.</p>
    </section>
  );
}
