"use client";

import type { ExplorerMode, PropertySort } from "@/types/property";

type ContextBarProps = {
  totalCount: number | null;
  count: number | null;
  mapCount: number | null;
  sort: PropertySort;
  mode: ExplorerMode;
  viewportApplied: boolean;
  onRemoveViewport: () => void;
  // Pagination range (e.g. "1–24 de 2.847")
  page?: number;
  pageSize?: number;
};

const sortLabels: Record<PropertySort, string> = {
  relevance: "Relevancia",
  recent: "Más recientes",
  price_asc: "Menor precio",
  price_desc: "Mayor precio",
  area_desc: "Mayor superficie",
  rooms_desc: "Más ambientes",
  price_m2_asc: "Menor precio por m²",
};

const modeLabels: Record<ExplorerMode, string> = {
  balanced: "Exploración",
  analysis: "Análisis",
  results: "Resultados amplios",
  map: "Mapa protagonista",
  results_only: "Solo resultados",
  map_only: "Solo mapa",
};

function formatRange(page: number, pageSize: number, total: number): string {
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `Mostrando ${from.toLocaleString("es-AR")}–${to.toLocaleString("es-AR")} de ${total.toLocaleString("es-AR")}`;
}

export function ContextBar({
  totalCount,
  count,
  mapCount,
  sort,
  mode,
  viewportApplied,
  onRemoveViewport,
  page = 1,
  pageSize = 24,
}: ContextBarProps) {
  const withoutLocation =
    count !== null && mapCount !== null ? Math.max(0, count - mapCount) : null;

  return (
    <div className="context-bar">
      <div className="container context-bar-inner">
        {/* Left: counts */}
        <div className="context-bar-counts">
          {totalCount !== null && (
            <div className="context-bar-total">
              {totalCount.toLocaleString("es-AR")} propiedades disponibles en ERETZ
            </div>
          )}
          <div className="context-bar-result">
            {count !== null
              ? `${count.toLocaleString("es-AR")} coinciden con tu búsqueda`
              : "Cargando resultados…"}
          </div>
          {count !== null && mapCount !== null && (
            <div className="context-bar-breakdown">
              <span>{mapCount.toLocaleString("es-AR")} visibles en el mapa</span>
              {withoutLocation !== null && withoutLocation > 0 && (
                <span className="context-bar-separator">·</span>
              )}
              {withoutLocation !== null && withoutLocation > 0 && (
                <span>{withoutLocation.toLocaleString("es-AR")} sin ubicación exacta</span>
              )}
            </div>
          )}
          {count !== null && count > 0 && (
            <div className="context-bar-range">
              {formatRange(page, pageSize, count)}
            </div>
          )}
        </div>

        {/* Right: meta */}
        <div className="context-bar-meta">
          <div className="context-bar-tags">
            <span className="context-bar-tag">
              <span className="context-bar-tag-label">Orden</span>
              <span className="context-bar-tag-value">{sortLabels[sort] || "Relevancia"}</span>
            </span>
            <span className="context-bar-tag">
              <span className="context-bar-tag-label">Vista</span>
              <span className="context-bar-tag-value">{modeLabels[mode] || "Exploración"}</span>
            </span>
          </div>
          {viewportApplied && (
            <div className="context-bar-viewport">
              <span className="context-bar-viewport-badge">Zona del mapa aplicada</span>
              <button
                type="button"
                onClick={onRemoveViewport}
                className="context-bar-viewport-remove"
              >
                Quitar filtro del mapa
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
