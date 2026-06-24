"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { FilterBar, countAllFilters, initialFilters, type QuickFilters } from "@/components/filters/FilterBar";
import { PropertyMap } from "@/components/map/PropertyMap";
import type { FlyToTarget } from "@/components/map/PropertyLeafletMap";
import {
  PropertyListPlaceholder,
  type SortOption,
} from "@/components/property/PropertyListPlaceholder";
import { HeroSection } from "@/components/search/HeroSection";
import { SearchBar } from "@/components/search/SearchBar";
import type { PropertyDataSource } from "@/lib/property-service";
import type { Property } from "@/types/property";

type PropertyExplorerProps = {
  properties: Property[];
  dataSource: PropertyDataSource;
};

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

type LayoutMode = "map-only" | "map-large" | "balanced" | "list-large" | "list-only";

const LAYOUT_GRID: Record<LayoutMode, string> = {
  "map-only":   "lg:grid-cols-1",
  "map-large":  "lg:grid-cols-[minmax(0,1fr)_420px]",
  "balanced":   "lg:grid-cols-2",
  "list-large": "lg:grid-cols-[380px_minmax(0,1fr)]",
  "list-only":  "lg:grid-cols-1",
};

type LayoutOption = {
  mode: LayoutMode;
  label: string;
  icon: React.ReactNode;
  title: string;
};

function LayoutIcon({ mode }: { mode: LayoutMode }) {
  const dark = "currentColor";
  switch (mode) {
    case "map-only":
      return (
        <svg viewBox="0 0 22 12" className="size-[18px]" aria-hidden="true">
          <rect x="0" y="0" width="22" height="12" rx="2" fill={dark} />
        </svg>
      );
    case "map-large":
      return (
        <svg viewBox="0 0 22 12" className="size-[18px]" aria-hidden="true">
          <rect x="0" y="0" width="14" height="12" rx="2" fill={dark} />
          <rect x="16" y="0" width="6" height="12" rx="2" fill={dark} fillOpacity={0.32} />
        </svg>
      );
    case "balanced":
      return (
        <svg viewBox="0 0 22 12" className="size-[18px]" aria-hidden="true">
          <rect x="0" y="0" width="10" height="12" rx="2" fill={dark} />
          <rect x="12" y="0" width="10" height="12" rx="2" fill={dark} fillOpacity={0.32} />
        </svg>
      );
    case "list-large":
      return (
        <svg viewBox="0 0 22 12" className="size-[18px]" aria-hidden="true">
          <rect x="0" y="0" width="6" height="12" rx="2" fill={dark} />
          <rect x="8" y="0" width="14" height="12" rx="2" fill={dark} fillOpacity={0.32} />
        </svg>
      );
    case "list-only":
      return (
        <svg viewBox="0 0 22 12" className="size-[18px]" aria-hidden="true">
          <rect x="0" y="0" width="22" height="12" rx="2" fill={dark} fillOpacity={0.32} />
          <rect x="2" y="2" width="18" height="2" rx="1" fill={dark} />
          <rect x="2" y="6" width="14" height="2" rx="1" fill={dark} />
          <rect x="2" y="10" width="10" height="2" rx="1" fill={dark} />
        </svg>
      );
  }
}

const LAYOUT_OPTIONS: LayoutOption[] = [
  { mode: "map-only",   label: "Solo mapa",      icon: <LayoutIcon mode="map-only" />,   title: "Solo mapa" },
  { mode: "map-large",  label: "Mapa grande",     icon: <LayoutIcon mode="map-large" />,  title: "Mapa grande (60/40)" },
  { mode: "balanced",   label: "50/50",           icon: <LayoutIcon mode="balanced" />,   title: "Vista equilibrada" },
  { mode: "list-large", label: "Resultados",      icon: <LayoutIcon mode="list-large" />, title: "Resultados grandes" },
  { mode: "list-only",  label: "Solo resultados", icon: <LayoutIcon mode="list-only" />,  title: "Solo resultados" },
];

// ---------------------------------------------------------------------------
// Filter helpers
// ---------------------------------------------------------------------------

const visiblePageSize = 24;

function normalizeSearchText(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}

function matchesSearch(property: Property, query: string) {
  if (!query) return true;
  const tokens = query.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;

  const haystack = [
    property.title,
    property.description,
    property.address,
    property.neighborhood,
    property.city,
    property.province,
    property.agencyName,
    property.propertyType,
    property.operation,
  ]
    .map(normalizeSearchText)
    .join(" ");

  return tokens.every((token) => haystack.includes(token));
}

function hasCoordinates(property: Property) {
  return (
    typeof property.latitude === "number" &&
    Number.isFinite(property.latitude) &&
    typeof property.longitude === "number" &&
    Number.isFinite(property.longitude)
  );
}

function isRecentlyPublished(property: Property): boolean {
  const ref = property.publishedAt || property.createdAt;
  if (!ref) return false;
  const t = new Date(ref).getTime();
  if (!Number.isFinite(t)) return false;
  return Date.now() - t < 30 * 24 * 60 * 60 * 1000;
}

function getBestMatchScore(property: Property) {
  let score = 0;
  if (hasCoordinates(property)) score += 4;
  if (property.hasRealImage) score += 3;
  if (property.price > 0) score += 2;
  if (property.updatedAt) {
    const t = new Date(property.updatedAt).getTime();
    if (Number.isFinite(t)) {
      const ageMs = Date.now() - t;
      score += Math.max(0, 1 - ageMs / (30 * 24 * 60 * 60 * 1000));
    }
  }
  return score;
}

function filterProperties(
  properties: Property[],
  filters: QuickFilters,
  query: string,
): Property[] {
  return properties.filter((p) => {
    // Operación
    if (filters.operation !== "all" && p.operation !== filters.operation) return false;
    // Tipo
    if (filters.propertyType !== "all" && p.propertyType !== filters.propertyType) return false;
    // Moneda
    if (filters.currency !== "all" && p.currency !== filters.currency) return false;
    // Ubicación
    if (filters.province !== null && p.province !== filters.province) return false;
    if (filters.city !== null && p.city !== filters.city) return false;
    if (filters.neighborhood !== null && p.neighborhood !== filters.neighborhood) return false;
    // Precio
    if (filters.minPrice !== null && p.price < filters.minPrice) return false;
    if (filters.maxPrice !== null && p.price > filters.maxPrice) return false;
    // Características
    if (filters.minRooms !== null && p.rooms < filters.minRooms) return false;
    if (filters.minBedrooms !== null && p.bedrooms < filters.minBedrooms) return false;
    if (filters.minBathrooms !== null && p.bathrooms < filters.minBathrooms) return false;
    if (filters.hasGarage && p.garages <= 0) return false;
    // Superficie — solo filtra si el área es conocida (> 0)
    if (filters.minTotalArea !== null && p.totalArea > 0 && p.totalArea < filters.minTotalArea) return false;
    if (filters.maxTotalArea !== null && p.totalArea > 0 && p.totalArea > filters.maxTotalArea) return false;
    if (filters.minCoveredArea !== null && p.coveredArea > 0 && p.coveredArea < filters.minCoveredArea) return false;
    if (filters.maxCoveredArea !== null && p.coveredArea > 0 && p.coveredArea > filters.maxCoveredArea) return false;
    // Extras
    if (filters.hasRealImage && !p.hasRealImage) return false;
    if (filters.hasCoordinates && !hasCoordinates(p)) return false;
    if (filters.recentlyPublished && !isRecentlyPublished(p)) return false;
    if (filters.mortgageEligible && !p.mortgageEligible) return false;
    if (filters.onlyAvailable && (p.status === "vendida" || p.status === "alquilada" || p.status === "no_detectada_en_ultimo_scraping")) return false;
    // Búsqueda libre
    return matchesSearch(p, query);
  });
}

function applySort(properties: Property[], sortBy: SortOption): Property[] {
  const arr = [...properties];
  switch (sortBy) {
    case "newest":
      return arr.sort((a, b) => {
        const ta = new Date(a.updatedAt || a.createdAt || 0).getTime() || 0;
        const tb = new Date(b.updatedAt || b.createdAt || 0).getTime() || 0;
        return tb - ta;
      });
    case "price-asc":
      return arr.sort((a, b) => {
        if (a.price <= 0 && b.price <= 0) return 0;
        if (a.price <= 0) return 1;
        if (b.price <= 0) return -1;
        return a.price - b.price;
      });
    case "price-desc":
      return arr.sort((a, b) => {
        if (a.price <= 0 && b.price <= 0) return 0;
        if (a.price <= 0) return 1;
        if (b.price <= 0) return -1;
        return b.price - a.price;
      });
    case "area-desc":
      return arr.sort((a, b) => {
        if (a.totalArea <= 0 && b.totalArea <= 0) return 0;
        if (a.totalArea <= 0) return 1;
        if (b.totalArea <= 0) return -1;
        return b.totalArea - a.totalArea;
      });
    case "rooms-desc":
      return arr.sort((a, b) => b.rooms - a.rooms || b.bedrooms - a.bedrooms);
    case "best-match":
    default:
      return arr.sort((a, b) => getBestMatchScore(b) - getBestMatchScore(a));
  }
}

function getZoneCount(properties: Property[]) {
  const zones = new Set(
    properties
      .map((p) => p.neighborhood || p.city)
      .filter(Boolean)
      .map(normalizeSearchText),
  );
  return zones.size;
}

function getUniqueValues(
  properties: Property[],
  getter: (p: Property) => string,
): string[] {
  const seen = new Set<string>();
  properties.forEach((p) => {
    const val = getter(p);
    if (val) seen.add(val);
  });
  return Array.from(seen).sort((a, b) => a.localeCompare(b, "es"));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PropertyExplorer({ properties, dataSource }: PropertyExplorerProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [filters, setFilters] = useState<QuickFilters>(initialFilters);
  const [sortBy, setSortBy] = useState<SortOption>("best-match");
  const [visibleCount, setVisibleCount] = useState(visiblePageSize);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("map-large");

  // R5: selection + map interaction
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);
  const [flyToTarget, setFlyToTarget] = useState<FlyToTarget>(null);

  // R6: mobile view toggle ("map" default — mapa es protagonista)
  const [mobileView, setMobileView] = useState<"map" | "list">("map");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const normalizedQuery = useMemo(
    () => normalizeSearchText(deferredQuery),
    [deferredQuery],
  );

  const availableProvinces = useMemo(
    () => getUniqueValues(properties, (p) => p.province),
    [properties],
  );

  const availableCities = useMemo(() => {
    const source = filters.province
      ? properties.filter((p) => p.province === filters.province)
      : properties;
    return getUniqueValues(source, (p) => p.city);
  }, [properties, filters.province]);

  const availableNeighborhoods = useMemo(() => {
    const source = filters.city
      ? properties.filter((p) => p.city === filters.city)
      : filters.province
      ? properties.filter((p) => p.province === filters.province)
      : properties;
    return getUniqueValues(source, (p) => p.neighborhood);
  }, [properties, filters.city, filters.province]);

  const filteredProperties = useMemo(
    () => applySort(filterProperties(properties, filters, normalizedQuery), sortBy),
    [filters, normalizedQuery, properties, sortBy],
  );

  const visibleProperties = useMemo(
    () => filteredProperties.slice(0, visibleCount),
    [filteredProperties, visibleCount],
  );

  const totalZones = useMemo(() => getZoneCount(properties), [properties]);
  const hasMore = visibleCount < filteredProperties.length;

  const updateQuickFilters = useCallback((nextFilters: QuickFilters) => {
    setFilters(nextFilters);
    setVisibleCount(visiblePageSize);
  }, []);

  const updateQuery = useCallback((nextQuery: string) => {
    setQuery(nextQuery);
    setVisibleCount(visiblePageSize);
  }, []);

  const updateSortBy = useCallback((next: SortOption) => {
    setSortBy(next);
    setVisibleCount(visiblePageSize);
  }, []);

  const clearAllFilters = useCallback(() => {
    setFilters(initialFilters);
    setVisibleCount(visiblePageSize);
  }, []);

  const loadMore = useCallback(() => {
    setVisibleCount((n) => n + visiblePageSize);
  }, []);

  // R5 — card click: toggle selection + fly map to coordinates
  const handleSelectFromCard = useCallback((id: string) => {
    setSelectedPropertyId((prev) => {
      const next = prev === id ? null : id;
      if (next !== null) {
        const prop = properties.find((p) => p.id === id);
        if (
          prop &&
          typeof prop.latitude === "number" &&
          Number.isFinite(prop.latitude) &&
          typeof prop.longitude === "number" &&
          Number.isFinite(prop.longitude)
        ) {
          setFlyToTarget({ lat: prop.latitude, lng: prop.longitude, id });
        }
      }
      return next;
    });
  }, [properties]);

  // R5 — marker click: toggle selection (scroll handled by effect below)
  const handleSelectFromMap = useCallback((id: string) => {
    setSelectedPropertyId((prev) => (prev === id ? null : id));
  }, []);

  // R5 — scroll card into view when selected from the map
  useEffect(() => {
    if (!selectedPropertyId) return;
    const el = document.getElementById(`property-card-${selectedPropertyId}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedPropertyId]);

  const mapHidden  = layoutMode === "list-only";
  const listHidden = layoutMode === "map-only";

  return (
    <main>
      {/* ── Hero ── */}
      <HeroSection totalProperties={properties.length} totalZones={totalZones}>
        <SearchBar query={query} onQueryChange={updateQuery} />
      </HeroSection>

      {/* ── Filter strip ── */}
      <div className="relative z-30 overflow-visible border-b border-ink-950/8 bg-white">

        {/* Mobile: collapsible filter header */}
        <div className="flex items-center justify-between px-4 py-2.5 sm:px-5 lg:hidden">
          <button
            type="button"
            aria-expanded={filtersOpen}
            className="flex items-center gap-2 text-sm font-semibold text-ink-950"
            onClick={() => setFiltersOpen((v) => !v)}
          >
            <svg className="size-4 shrink-0 text-ink-950/60" viewBox="0 0 16 12" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true">
              <path d="M1 1h14M3 6h10M6 11h4" />
            </svg>
            Filtros
            {countAllFilters(filters) > 0 && (
              <span className="rounded-full bg-ink-950 px-2 py-0.5 text-[11px] font-bold text-white">
                {countAllFilters(filters)}
              </span>
            )}
            <svg
              className={`size-3 shrink-0 text-ink-950/50 transition-transform duration-150 ${filtersOpen ? "rotate-180" : ""}`}
              viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true"
            >
              <path d="M1 1l4 4 4-4" />
            </svg>
          </button>
          {countAllFilters(filters) > 0 && (
            <button
              type="button"
              className="text-xs font-semibold text-red-600"
              onClick={() => updateQuickFilters(initialFilters)}
            >
              Limpiar
            </button>
          )}
        </div>

        {/* Mobile: filter panel (opens below the header) */}
        {filtersOpen && (
          <div className="border-t border-ink-950/6 px-4 pb-3 pt-2 sm:px-5 lg:hidden">
            <FilterBar
              filters={filters}
              availableCities={availableCities}
              availableProvinces={availableProvinces}
              availableNeighborhoods={availableNeighborhoods}
              onChange={updateQuickFilters}
            />
          </div>
        )}

        {/* Desktop: always-visible filter bar */}
        <div className="hidden lg:block">
          <div className="mx-auto w-full max-w-[1480px] px-6 py-3">
            <FilterBar
              filters={filters}
              availableCities={availableCities}
              availableProvinces={availableProvinces}
              availableNeighborhoods={availableNeighborhoods}
              onChange={updateQuickFilters}
            />
          </div>
        </div>
      </div>

      {/* ── Layout controls (desktop only) ── */}
      <div className="hidden border-b border-ink-950/6 bg-white/80 lg:block">
        <div className="mx-auto flex w-full max-w-[1480px] items-center justify-end gap-1 px-6 py-1.5">
          <p className="mr-2 text-xs font-medium text-ink-950/40">Vista:</p>
          {LAYOUT_OPTIONS.map(({ mode, label, icon, title }) => {
            const isActive = layoutMode === mode;
            return (
              <button
                key={mode}
                type="button"
                title={title}
                aria-pressed={isActive}
                className={
                  isActive
                    ? "flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold text-white transition bg-ink-950"
                    : "flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium text-ink-950/54 transition hover:bg-ink-950/6 hover:text-ink-950/80"
                }
                onClick={() => setLayoutMode(mode)}
              >
                {icon}
                <span className="hidden xl:inline">{label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Mobile: tab bar Mapa / Resultados ── */}
      <div className="flex border-b border-ink-950/8 bg-white lg:hidden">
        {(["map", "list"] as const).map((view) => (
          <button
            key={view}
            type="button"
            className={`flex-1 -mb-px border-b-2 py-3 text-sm font-semibold transition ${
              mobileView === view
                ? "border-ink-950 text-ink-950"
                : "border-transparent text-ink-950/44 hover:text-ink-950/70"
            }`}
            onClick={() => setMobileView(view)}
          >
            {view === "map"
              ? "Mapa"
              : `Resultados${filteredProperties.length > 0 ? ` (${filteredProperties.length.toLocaleString("es-AR")})` : ""}`}
          </button>
        ))}
      </div>

      {/* ── Contenido: MAPA IZQUIERDA · LISTA DERECHA ── */}
      {/* Mobile: un panel a la vez. Desktop: grid según layoutMode. */}
      <section
        className={`mx-auto grid w-full max-w-[1480px] gap-4 px-4 pb-24 pt-3 sm:px-5 lg:px-6 lg:pt-4 ${LAYOUT_GRID[layoutMode]}`}
      >
        {/* Mapa — siempre presente en DOM (Leaflet persiste); CSS controla visibilidad */}
        <div
          className={
            mapHidden
              ? "hidden"
              : mobileView !== "map"
              ? "hidden lg:block"
              : "h-[calc(100dvh-15rem)] lg:h-auto"
          }
        >
          <PropertyMap
            properties={filteredProperties}
            selectedPropertyId={selectedPropertyId}
            onSelectProperty={handleSelectFromMap}
            flyToTarget={flyToTarget}
          />
        </div>

        {/* Listado — visible en mobile solo si mobileView === "list" */}
        <div
          className={
            listHidden
              ? "hidden"
              : mobileView !== "list"
              ? "hidden lg:block"
              : "overflow-y-auto overscroll-contain max-h-[calc(100dvh-15rem)] lg:max-h-none lg:overflow-visible"
          }
        >
          <PropertyListPlaceholder
            dataSource={dataSource}
            properties={visibleProperties}
            totalFiltered={filteredProperties.length}
            totalProperties={properties.length}
            sortBy={sortBy}
            onSortChange={updateSortBy}
            hasMore={hasMore}
            onLoadMore={loadMore}
            onClearFilters={clearAllFilters}
            selectedPropertyId={selectedPropertyId}
            onSelectProperty={handleSelectFromCard}
            isWideMode={layoutMode === "list-only"}
          />
        </div>
      </section>
    </main>
  );
}
