"use client";

import { PropertyCard } from "@/components/property/PropertyCard";
import type { PropertyDataSource } from "@/lib/property-service";
import type { Property } from "@/types/property";

export type SortOption =
  | "best-match"
  | "newest"
  | "price-asc"
  | "price-desc"
  | "area-desc"
  | "rooms-desc";

export const sortOptions: Array<{ value: SortOption; label: string }> = [
  { value: "best-match", label: "Mejor match" },
  { value: "newest", label: "Más recientes" },
  { value: "price-asc", label: "Menor precio" },
  { value: "price-desc", label: "Mayor precio" },
  { value: "area-desc", label: "Mayor superficie" },
  { value: "rooms-desc", label: "Más ambientes" },
];

type PropertyListPlaceholderProps = {
  properties: Property[];
  sortBy: SortOption;
  onSortChange: (sort: SortOption) => void;
  totalFiltered?: number;
  totalProperties?: number;
  dataSource?: PropertyDataSource;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onClearFilters?: () => void;
  emptyMessage?: string;
  selectedPropertyId?: string | null;
  onSelectProperty?: (id: string) => void;
  isWideMode?: boolean;
};

// "error" no tiene badge: se muestra un estado de error dedicado, no un rótulo.
const sourceLabels: Partial<Record<PropertyDataSource, string>> = {
  supabase: "Datos reales",
  mock: "Datos demo",
};

function buildCounterLabel(
  totalFiltered: number,
  totalProperties: number,
  visibleCount: number,
): string {
  const filtered = totalFiltered < totalProperties;
  const base = filtered
    ? `${totalFiltered.toLocaleString("es-AR")} de ${totalProperties.toLocaleString("es-AR")} propiedades`
    : `${totalProperties.toLocaleString("es-AR")} propiedades activas`;

  return visibleCount < totalFiltered ? `${base} · ${visibleCount} visibles` : base;
}

export function PropertyListPlaceholder({
  properties,
  sortBy,
  onSortChange,
  totalFiltered = properties.length,
  totalProperties = totalFiltered,
  dataSource = "mock",
  hasMore = false,
  onLoadMore,
  onClearFilters,
  emptyMessage = "Sin resultados para estos filtros.",
  selectedPropertyId,
  onSelectProperty,
  isWideMode = false,
}: PropertyListPlaceholderProps) {
  const counterLabel = buildCounterLabel(totalFiltered, totalProperties, properties.length);
  const isFiltered = totalFiltered < totalProperties;

  return (
    <section
      id="properties"
      className={`min-w-0 rounded-lg border border-ink-950/10 bg-white p-3 shadow-sm sm:p-4 ${
        isWideMode ? "" : "lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto"
      }`}
    >
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold-500">
            Resultados
          </p>
          <h2 className="mt-1 text-xl font-semibold text-ink-950">Propiedades</h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <p className="text-sm text-ink-950/58">{counterLabel}</p>
            {isFiltered && (
              <span className="rounded-md bg-gold-500/14 px-2 py-0.5 text-xs font-semibold text-gold-600">
                Filtrado
              </span>
            )}
            {sourceLabels[dataSource] && (
              <span className="rounded-md border border-ink-950/10 bg-ink-950/[0.02] px-2 py-1 text-xs font-semibold text-ink-950/58">
                {sourceLabels[dataSource]}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-ink-950/45">
            Los precios y la disponibilidad pueden variar. Confirmá siempre la información con la
            inmobiliaria correspondiente.
          </p>
        </div>

        <select
          className="h-10 shrink-0 cursor-pointer rounded-md border border-ink-950/10 bg-white px-3 text-sm font-semibold text-ink-950/72 shadow-sm outline-none transition focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15"
          value={sortBy}
          aria-label="Ordenar resultados"
          onChange={(e) => onSortChange(e.target.value as SortOption)}
        >
          {sortOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {properties.length > 0 ? (
        <div
          className={`grid gap-3 ${
            isWideMode
              ? "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              : "sm:grid-cols-2 lg:grid-cols-1"
          }`}
        >
          {properties.map((property) => (
            <PropertyCard
              key={property.id}
              property={property}
              isSelected={property.id === selectedPropertyId}
              onSelect={onSelectProperty}
            />
          ))}
        </div>
      ) : dataSource === "error" ? (
        <div className="rounded-lg border border-dashed border-red-300 bg-red-50/60 px-5 py-10 text-center">
          <p className="text-base font-semibold text-ink-950">
            Estamos teniendo problemas para cargar las propiedades.
          </p>
          <p className="mx-auto mt-2 max-w-xs text-sm leading-6 text-ink-950/58">
            Intentá nuevamente en unos minutos.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-ink-950/14 bg-ink-950/[0.02] px-5 py-10 text-center">
          <p className="text-base font-semibold text-ink-950">{emptyMessage}</p>
          <p className="mx-auto mt-2 max-w-xs text-sm leading-6 text-ink-950/58">
            Probá ajustar operación, tipo de propiedad, zona o rango de precio para ver más
            resultados.
          </p>
          {onClearFilters && (
            <button
              type="button"
              className="mt-5 rounded-md bg-ink-950 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-ink-800 focus:outline-none focus:ring-4 focus:ring-ink-950/20"
              onClick={onClearFilters}
            >
              Limpiar filtros
            </button>
          )}
        </div>
      )}

      {hasMore && onLoadMore ? (
        <button
          type="button"
          className="mt-4 h-11 w-full rounded-md border border-ink-950/10 bg-white text-sm font-semibold text-ink-950 shadow-sm transition hover:border-ink-950/22 hover:bg-ink-950/[0.03]"
          onClick={onLoadMore}
        >
          Cargar más propiedades
        </button>
      ) : null}
    </section>
  );
}
