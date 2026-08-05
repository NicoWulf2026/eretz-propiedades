"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
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
  const [interactive, setInteractive] = useState(false);
  const activate = useCallback(() => setInteractive(true), []);
  useEffect(() => {
    // The static map skeleton is immediately useful. Load the heavy interactive
    // layer on intent, with a bounded fallback for users who simply wait.
    const fallbackTimer = setTimeout(activate, 8_000);
    return () => clearTimeout(fallbackTimer);
  }, [activate]);
  const baseFilters = { ...filters, cursor: "", page: 1, direction: "next" as const, viewport: null };
  return (
    <section aria-label={label} className="property-map-shell">
      {interactive ? (
        <Leaflet
          properties={properties}
          baseSearch={filtersToSearchParams(baseFilters).toString()}
          initialViewport={filters.viewport}
          selectedId={selectedId}
          onSelect={onSelect}
          returnTo={returnTo}
        />
      ) : (
        <div className="map-progressive-placeholder" role="status" onPointerDown={activate} onMouseEnter={activate}>
          <span className="map-placeholder-pin" aria-hidden="true" />
          <strong>Preparando el mapa interactivo</strong>
          <small>Mapa nacional. La capa para mover, acercar y explorar se activa al interactuar.</small>
          <button type="button" className="secondary-button" onClick={activate}>Activar ahora</button>
        </div>
      )}
      <p id="map-alternative" className="sr-only">Todos los resultados del mapa también están disponibles en el listado de propiedades.</p>
    </section>
  );
}
