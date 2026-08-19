"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FilterForm } from "@/components/search/FilterForm";
import { ContextBar } from "@/components/explorer/ContextBar";
import { ActiveChips } from "@/components/explorer/ActiveChips";
import { NoResults } from "@/components/explorer/NoResults";
import { ViewModeSelector } from "@/components/explorer/ViewModeSelector";
import { Pagination } from "@/components/search/Pagination";
import { PropertyMap } from "@/components/map/PropertyMap";
import { PropertyCard } from "@/components/property/PropertyCard";
import { filtersToSearchParams } from "@/lib/property-query";
import { addRecentSearch, getVisited } from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";
import { describeSearch } from "@/lib/search-label";
import type { ExplorerMode, PropertyFilters, PropertySearchResult } from "@/types/property";

function unavailableResult(filters: PropertyFilters): PropertySearchResult {
  return {
    properties: [], count: null, totalCount: null, mapCount: null,
    page: filters.page, pageSize: 24,
    hasNext: false, hasPrevious: filters.page > 1, nextCursor: null, previousCursor: null,
    source: "error", error: true, invalidCursor: false,
  };
}

export function ExplorerClient({ filters, basePath }: { filters: PropertyFilters; basePath: string }) {
  const initialSearch = filtersToSearchParams(filters);
  const initialReturnTo = `${basePath}${initialSearch.toString() ? `?${initialSearch}` : ""}`;
  const [mode, setMode] = useState<ExplorerMode>(filters.mode);
  const [density, setDensity] = useState<"compact" | "full">("compact");
  const [hideVisited, setHideVisited] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const visited = useLocalValue(getVisited, [] as string[]);
  const [selectedId, setSelectedId] = useState(filters.selectedId);
  const [returnTo, setReturnTo] = useState(initialReturnTo);
  const requestKey = filtersToSearchParams(filters).toString();
  const [resultState, setResultState] = useState<{ key: string; result: PropertySearchResult } | null>(null);
  const result = resultState?.key === requestKey ? resultState.result : null;
  const [mapOnlyCounts, setMapOnlyCounts] = useState<{ key: string; count: number | null; mapCount: number | null } | null>(null);
  const resultAbortRef = useRef<AbortController | null>(null);
  // Scroll pendiente de restaurar al volver de una ficha (ver efectos abajo).
  const pendingScrollRef = useRef<number | null>(null);
  const pendingScrollTargetRef = useRef<"window" | "results">("window");
  const pendingUntilRef = useRef<number>(0);
  const resultsPaneRef = useRef<HTMLElement | null>(null);
  const currentFilters = useMemo(() => ({ ...filters, mode, selectedId }), [filters, mode, selectedId]);

  // Registra la búsqueda actual (sin paginación ni selección) en "búsquedas
  // recientes" cuando hay al menos un filtro significativo.
  useEffect(() => {
    const label = describeSearch(filters);
    if (!label) return;
    const params = filtersToSearchParams({ ...filters, cursor: "", page: 1, direction: "next", selectedId: "" });
    const query = params.toString();
    addRecentSearch({ url: `${basePath}${query ? `?${query}` : ""}`, label });
  }, [requestKey, basePath, filters]);

  useEffect(() => {
    if (filters.mode === "balanced") {
      const saved = localStorage.getItem("eretz:explorer-mode") as ExplorerMode | null;
      if (saved === "balanced" || saved === "results_only" || saved === "map_only") requestAnimationFrame(() => setMode(saved));
    }
    const savedDensity = localStorage.getItem("eretz:card-density");
    if (savedDensity === "full" || savedDensity === "compact") requestAnimationFrame(() => setDensity(savedDensity));
    if (localStorage.getItem("eretz:hide-visited") === "1") requestAnimationFrame(() => setHideVisited(true));
    try {
      // La clave se busca por la URL REAL y por la normalizada: `selectProperty`
      // la escribe desde window.location.href (cruda), mientras que
      // `initialReturnTo` usa filtersToSearchParams, que puede diferir cuando un
      // parámetro se normaliza (p. ej. `orden=price_desc` sin moneda cae a
      // `recent`) o no se serializa (`nl=`). Sin esto, el estado no se recuperaba.
      const rawReturnTo = `${window.location.pathname}${window.location.search}`;
      const stored = sessionStorage.getItem(`eretz:return:${rawReturnTo}`)
        ?? sessionStorage.getItem(`eretz:return:${initialReturnTo}`);
      const state = JSON.parse(stored ?? "null") as { scrollY?: number; scrollTarget?: "window" | "results"; selectedId?: string } | null;
      if (state?.selectedId) requestAnimationFrame(() => setSelectedId(state.selectedId ?? ""));
      // El scroll NO se restaura acá: el listado carga async y el destino todavía
      // no tiene altura suficiente. Se difiere al efecto de abajo.
      if (typeof state?.scrollY === "number") {
        pendingScrollRef.current = state.scrollY;
        pendingScrollTargetRef.current = state.scrollTarget ?? "window";
        pendingUntilRef.current = Date.now() + 10_000; // ventana para que cargue el listado
      }
    } catch {
      // Navigation restoration is progressive enhancement.
    }
    const onUrl = (event: Event) => setReturnTo((event as CustomEvent<string>).detail);
    window.addEventListener("eretz:explorer-url-change", onUrl);
    return () => window.removeEventListener("eretz:explorer-url-change", onUrl);
  }, [filters.mode, initialReturnTo]);

  // Restauración diferida: espera a que el documento o el rail tengan altura
  // suficiente (el listado llega por fetch).
  useEffect(() => {
    if (pendingScrollRef.current === null) return;
    let frame = 0;
    let appliedAt = 0;
    const attempt = () => {
      const target = pendingScrollRef.current;
      if (target === null) return;
      // Se desiste por deadline (el listado llega por fetch, 1-3 s). Tras aplicar
      // se re-verifica un momento: el router puede resetear el scroll a 0 al
      // completar la navegación, después de nuestra restauración.
      if (Date.now() > pendingUntilRef.current) { pendingScrollRef.current = null; return; }
      const resultsPane = pendingScrollTargetRef.current === "results" ? resultsPaneRef.current : null;
      const maxScroll = resultsPane
        ? resultsPane.scrollHeight - resultsPane.clientHeight
        : document.documentElement.scrollHeight - window.innerHeight;
      if (maxScroll >= target - 4) {
        const currentScroll = resultsPane?.scrollTop ?? window.scrollY;
        if (Math.abs(currentScroll - target) > 8) {
          if (resultsPane) resultsPane.scrollTo({ top: target, behavior: "instant" });
          else window.scrollTo({ top: target, behavior: "instant" });
          if (!appliedAt) appliedAt = Date.now();
        }
        if (appliedAt && Date.now() - appliedAt > 1200) { pendingScrollRef.current = null; return; }
      }
      frame = requestAnimationFrame(attempt);
    };
    frame = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(frame);
  }, [result, density, mode]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 768px)").matches;
    const resultsVisible = desktop ? mode !== "map_only" : mode === "results_only";
    if (!resultsVisible || result) return;
    const controller = new AbortController();
    resultAbortRef.current?.abort();
    resultAbortRef.current = controller;
    void fetch(`/api/properties/search?${filtersToSearchParams(filters)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("property request failed");
        return response.json() as Promise<PropertySearchResult>;
      })
      .then((nextResult) => setResultState({ key: requestKey, result: nextResult }))
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") {
          setResultState({ key: requestKey, result: unavailableResult(filters) });
        }
      });
    return () => controller.abort();
  }, [filters, mode, requestKey, result]);

  useEffect(() => {
    if (mode !== "map_only" || result || mapOnlyCounts?.key === requestKey) return;
    const controller = new AbortController();
    void fetch(`/api/properties/counts?${filtersToSearchParams(filters)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("count request failed");
        return response.json() as Promise<{ count: number | null; mapCount: number | null }>;
      })
      .then((counts) => setMapOnlyCounts({ key: requestKey, count: counts.count, mapCount: counts.mapCount }))
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setMapOnlyCounts({ key: requestKey, count: null, mapCount: null });
      });
    return () => controller.abort();
  }, [filters, mapOnlyCounts?.key, mode, requestKey, result]);

  function chooseMode(next: ExplorerMode) {
    setMode(next);
    localStorage.setItem("eretz:explorer-mode", next);
    const url = new URL(window.location.href);
    if (next === "balanced") url.searchParams.delete("modo"); else url.searchParams.set("modo", next);
    const nextUrl = `${url.pathname}${url.search ? url.search : ""}`;
    window.history.replaceState(window.history.state, "", nextUrl);
    setReturnTo(nextUrl);
  }

function removeViewport() {
  // Clear viewport filter and update URL
  // Quitar filtro del mapa: elimina sólo el viewport, reinicia el cursor y
  // navega para re-consultar listado, conteos y mapa. Conserva el resto.
  const newFilters = { ...filters, viewport: null, cursor: "", page: 1, direction: "next" as const };
  const search = filtersToSearchParams(newFilters);
  window.location.assign(`${basePath}${search.toString() ? `?${search}` : ""}`);
}


  function chooseDensity(next: "compact" | "full") {
    setDensity(next);
    try { localStorage.setItem("eretz:card-density", next); } catch { /* opcional */ }
  }

  function toggleHideVisited() {
    setHideVisited((current) => {
      const next = !current;
      try { localStorage.setItem("eretz:hide-visited", next ? "1" : "0"); } catch { /* opcional */ }
      return next;
    });
  }

  function selectProperty(id: string) {
    setSelectedId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("seleccion", id);
    const nextUrl = `${url.pathname}?${url.searchParams.toString()}`;
    window.history.replaceState(window.history.state, "", nextUrl);
    setReturnTo(nextUrl);
  }

  const resetCursor = filtersToSearchParams({ ...filters, cursor: "", page: 1, direction: "next" });

  // "Ocultar visitadas": filtro de VISTA local (no altera counts server ni DB).
  const visitedSet = useMemo(() => new Set(visited.map(String)), [visited]);
  const pageProperties = result?.properties ?? [];
  const visitedInPage = pageProperties.reduce((n, p) => (visitedSet.has(String(p.id)) ? n + 1 : n), 0);
  const shownProperties = hideVisited ? pageProperties.filter((p) => !visitedSet.has(String(p.id))) : pageProperties;
  const mapViewCount = result?.count ?? (mapOnlyCounts?.key === requestKey ? mapOnlyCounts.count : null);
  const mapViewLocatedCount = result?.mapCount ?? (mapOnlyCounts?.key === requestKey ? mapOnlyCounts.mapCount : null);

  return (
    <div className="explorer-page">
      <header className="explorer-toolbar">
        <div className="container">
          <div className="explorer-heading-row">
            <div><p className="eyebrow">Explorador nacional</p><h1>Encontrá propiedades en el mapa</h1></div>
            <ViewModeSelector mode={mode} onChange={chooseMode} />
          </div>
          <div className="explorer-search-card">
            <FilterForm filters={currentFilters} action={basePath} onOpenChange={setFiltersOpen} />
          </div>
          <ActiveChips filters={currentFilters} basePath={basePath} onRemoveViewport={removeViewport} />
        </div>
      </header>

      {result?.invalidCursor ? <div className="container py-4"><div className="alert alert-warning" role="alert"><strong>Este enlace de paginación venció o no es válido.</strong><span> Podés volver al inicio de estos resultados sin perder tus filtros.</span><a href={`${basePath}?${resetCursor}`}>Volver a la primera página</a></div></div> : null}

      <main className={`explorer-workspace mode-${mode}${filtersOpen ? " filters-open" : ""}`}>
        <section className="explorer-map-pane" aria-label="Explorar en el mapa">
          <PropertyMap properties={result?.properties ?? []} filters={currentFilters} selectedId={selectedId} onSelect={selectProperty} returnTo={returnTo} />
          {mode === "map_only" ? (
            <div className="map-view-summary" aria-live="polite">
              <strong>{mapViewCount === null ? "Calculando propiedades…" : `${mapViewCount.toLocaleString("es-AR")} propiedades`}</strong>
              {mapViewLocatedCount !== null ? <span>{mapViewLocatedCount.toLocaleString("es-AR")} con ubicación orientativa en el mapa</span> : null}
            </div>
          ) : null}
        </section>
        <section ref={resultsPaneRef} className="explorer-results-pane" aria-label="Resultados de propiedades">
          <ContextBar
            totalCount={result?.totalCount ?? null}
            count={result?.count ?? null}
            mapCount={result?.mapCount ?? null}
            sort={filters.sort}
            mode={mode}
            viewportApplied={!!filters.viewport}
            onRemoveViewport={removeViewport}
          />
          <div className="density-toggle" role="group" aria-label="Densidad de tarjetas">
            <span className="density-label">Tarjetas</span>
            <button type="button" className={density === "compact" ? "is-active" : ""} aria-pressed={density === "compact"} onClick={() => chooseDensity("compact")}>Compactas</button>
            <button type="button" className={density === "full" ? "is-active" : ""} aria-pressed={density === "full"} onClick={() => chooseDensity("full")}>Completas</button>
            <button type="button" className={`hide-visited-toggle ${hideVisited ? "is-active" : ""}`} aria-pressed={hideVisited} onClick={toggleHideVisited} disabled={!hideVisited && visitedInPage === 0}>
              {hideVisited ? `Mostrar visitadas (${visitedInPage})` : `Ocultar visitadas (${visitedInPage})`}
            </button>
          </div>
          {!result ? (
            <div className="state-panel" role="status"><span aria-hidden="true">⌛</span><h2>Preparando resultados</h2><p>El mapa ya está disponible. Las propiedades se cargan sólo cuando este listado es visible.</p></div>
          ) : result.error ? (
            <div className="state-panel" role="alert"><span aria-hidden="true">↻</span><h2>No pudimos cargar las propiedades</h2><p>El servicio puede estar temporalmente ocupado. Tus filtros siguen guardados en la URL.</p><a className="primary-button" href={returnTo}>Reintentar</a></div>
          ) : result.properties.length === 0 ? (
            <NoResults filters={currentFilters} basePath={basePath} />
          ) : shownProperties.length === 0 ? (
            <div className="state-panel" role="status"><span aria-hidden="true">✓</span><h2>Ya viste todas las de esta página</h2><p>Ocultaste las propiedades visitadas. Podés mostrarlas de nuevo o pasar a la siguiente página.</p><button type="button" className="secondary-button" onClick={toggleHideVisited}>Mostrar visitadas</button></div>
          ) : (
            <div className={`explorer-card-list density-${density}`} id="property-results" data-view={mode}>
              {shownProperties.map((property) => <PropertyCard key={property.id} property={property} variant={density} returnTo={returnTo} selected={selectedId === property.id} onSelect={selectProperty} />)}
            </div>
          )}
          {result ? <Pagination filters={currentFilters} hasNext={result.hasNext} hasPrevious={result.hasPrevious} nextCursor={result.nextCursor} previousCursor={result.previousCursor} basePath={basePath} /> : null}
        </section>
      </main>
    </div>
  );
}
