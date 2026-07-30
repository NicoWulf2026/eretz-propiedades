"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { track } from "@/lib/analytics";
import type { Property } from "@/types/property";

const Leaflet = dynamic(
  () => import("@/components/map/PropertyLeafletMap").then((module) => module.PropertyLeafletMap),
  { ssr: false, loading: () => <div className="map-loading">Cargando mapa…</div> },
);

export function PropertyMap({ properties, label = "Mapa de resultados" }: { properties: Property[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const geolocated = properties.filter((property) => property.latitude !== null && property.longitude !== null);
  if (!geolocated.length) {
    return <div className="empty-panel"><p className="font-bold">Sin ubicaciones verificadas</p><p className="mt-1 text-sm">Estas propiedades no incluyen coordenadas públicas válidas.</p></div>;
  }
  return (
    <section aria-label={label}>
      <button type="button" className="secondary-button mb-3" aria-expanded={open} onClick={() => { setOpen((value) => !value); if (!open) track("map_opened"); }}>
        {open ? "Ocultar mapa" : `Ver mapa (${geolocated.length})`}
      </button>
      {open && (
        <div className="h-[420px] overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 shadow-sm">
          <Leaflet properties={geolocated} />
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">El mapa muestra únicamente las propiedades de esta página con coordenadas válidas; nunca descarga todo el inventario.</p>
    </section>
  );
}

