"use client";

import dynamic from "next/dynamic";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import type { FlyToTarget } from "@/components/map/PropertyLeafletMap";
import type { Property } from "@/types/property";

// ─── Types ───────────────────────────────────────────────────────────────────

type PropertyMapProps = {
  properties: Property[];
  selectedPropertyId?: string | null;
  onSelectProperty?: (id: string) => void;
  flyToTarget?: FlyToTarget;
};

// ─── Constants ────────────────────────────────────────────────────────────────

const MARKER_CAP = 200;

// ─── Dynamic import (SSR off — Leaflet requires window) ───────────────────────

const LeafletMap = dynamic(
  () =>
    import("@/components/map/PropertyLeafletMap").then(
      (module) => module.PropertyLeafletMap,
    ),
  {
    loading: () => (
      <div className="grid h-full min-h-[360px] place-items-center bg-[#eef3f8]">
        <div className="rounded-lg border border-ink-950/10 bg-white/92 px-5 py-4 text-center shadow-soft">
          <p className="text-sm font-semibold text-ink-950">Cargando mapa</p>
          <p className="mt-1 text-xs text-ink-950/56">Preparando propiedades geolocalizadas</p>
        </div>
      </div>
    ),
    ssr: false,
  },
);

// ─── Helpers ─────────────────────────────────────────────────────────────────

function hasCoordinates(property: Property) {
  return (
    typeof property.latitude === "number" &&
    Number.isFinite(property.latitude) &&
    typeof property.longitude === "number" &&
    Number.isFinite(property.longitude)
  );
}

// ─── SVG icons ────────────────────────────────────────────────────────────────

function ExpandIcon() {
  return (
    <svg
      className="size-3.5 shrink-0"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 5V2a1 1 0 011-1h3M9 1h3a1 1 0 011 1v3M13 9v3a1 1 0 01-1 1H9M5 13H2a1 1 0 01-1-1V9" />
    </svg>
  );
}

function CollapseIcon() {
  return (
    <svg
      className="size-3.5 shrink-0"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 1v3a1 1 0 01-1 1H1M13 5h-3a1 1 0 01-1-1V1M1 9h3a1 1 0 011 1v3M9 13v-3a1 1 0 011-1h3" />
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export const PropertyMap = memo(function PropertyMap({
  properties,
  selectedPropertyId,
  onSelectProperty,
  flyToTarget,
}: PropertyMapProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const geolocated = useMemo(() => properties.filter(hasCoordinates), [properties]);
  const isCapped = geolocated.length > MARKER_CAP;
  const markerProperties = useMemo(
    () => (isCapped ? geolocated.slice(0, MARKER_CAP) : geolocated),
    [geolocated, isCapped],
  );

  // ESC to close fullscreen
  useEffect(() => {
    if (!isFullscreen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setIsFullscreen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isFullscreen]);

  const toggleFullscreen = useCallback(() => setIsFullscreen((v) => !v), []);

  const mapContent = (
    <div
      className={`relative flex flex-col bg-[#eef3f8] ${
        isFullscreen ? "h-full" : "h-full min-h-[480px] lg:min-h-[720px]"
      }`}
    >
      {/* Map header */}
      <div className="relative z-10 flex items-center justify-between gap-3 border-b border-ink-950/10 bg-white/92 px-4 py-3 backdrop-blur">
        <div>
          <h2 className="text-sm font-semibold text-ink-950">Mapa interactivo</h2>
          <p className="text-xs text-ink-950/54">
            {isFullscreen
              ? "Presioná ESC o el botón para salir"
              : "Propiedades geolocalizadas con OpenStreetMap"}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <span className="rounded-md bg-ink-950 px-3 py-1 text-xs font-semibold text-white">
            {geolocated.length.toLocaleString("es-AR")}
            {" con ubicación"}
          </span>
          {!isCapped && (
            <span className="hidden rounded-md border border-ink-950/10 bg-white px-3 py-1 text-xs font-semibold text-ink-950/70 sm:inline-flex">
              OSM
            </span>
          )}

          {/* Fullscreen toggle */}
          <button
            type="button"
            aria-label={isFullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
            aria-pressed={isFullscreen}
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-ink-950/20 ${
              isFullscreen
                ? "border-white/20 bg-ink-950 text-white hover:bg-ink-800"
                : "border-ink-950/10 bg-white text-ink-950/70 hover:bg-ink-950/[0.04] hover:text-ink-950"
            }`}
            onClick={toggleFullscreen}
          >
            {isFullscreen ? <CollapseIcon /> : <ExpandIcon />}
            <span className="hidden sm:inline">
              {isFullscreen ? "Cerrar" : "Pantalla completa"}
            </span>
          </button>
        </div>
      </div>

      {/* Cap notice */}
      {isCapped && (
        <div className="relative z-10 border-b border-gold-500/16 bg-gold-500/8 px-4 py-2">
          <p className="text-xs font-medium text-ink-950/72">
            Mostrando las {MARKER_CAP.toLocaleString("es-AR")} propiedades más relevantes en el
            mapa.{" "}
            <span className="text-ink-950/48">Filtrá para ver resultados más específicos.</span>
          </p>
        </div>
      )}

      {/* Map area */}
      <div className="relative z-0 flex-1">
        <LeafletMap
          properties={markerProperties}
          selectedPropertyId={selectedPropertyId}
          onSelectProperty={onSelectProperty}
          flyToTarget={flyToTarget}
        />

        {geolocated.length === 0 && (
          <div className="pointer-events-none absolute inset-0 z-[450] grid place-items-center bg-[#eef3f8]/88 p-5">
            <div className="max-w-sm rounded-lg border border-ink-950/10 bg-white/92 p-5 text-center shadow-soft backdrop-blur">
              <p className="text-sm font-semibold text-ink-950">Sin coordenadas disponibles</p>
              <p className="mt-2 text-sm leading-6 text-ink-950/62">
                El mapa queda listo para mostrar propiedades cuando Supabase entregue latitud y
                longitud.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // Same element type always — only CSS changes — so Leaflet never unmounts.
  return (
    <div
      id="map"
      className={
        isFullscreen
          ? "fixed inset-0 z-[9999] overflow-hidden"
          : "min-h-[480px] overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-lift lg:sticky lg:top-20 lg:h-[calc(100vh-5.5rem)] lg:min-h-[720px]"
      }
    >
      {mapContent}
    </div>
  );
});
