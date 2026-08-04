"use client";

import { useEffect, useMemo, useState } from "react";
import { FilterForm } from "@/components/search/FilterForm";
import { Pagination } from "@/components/search/Pagination";
import { PropertyMap } from "@/components/map/PropertyMap";
import { PropertyCard } from "@/components/property/PropertyCard";
import { filtersToSearchParams } from "@/lib/property-query";
import type { ExplorerMode, PropertyFilters, PropertySearchResult } from "@/types/property";

const modeLabels: Array<[ExplorerMode, string]> = [
  ["map", "Mapa protagonista"],
  ["balanced", "Equilibrado"],
  ["results", "Resultados amplios"],
  ["map_only", "Solo mapa"],
  ["results_only", "Solo resultados"],
];

export function ExplorerClient({ filters, result, basePath }: { filters: PropertyFilters; result: PropertySearchResult; basePath: string }) {
  const initialReturnTo = `${basePath}${filtersToSearchParams(filters).toString() ? `?${filtersToSearchParams(filters)}` : ""}`;
  const [mode, setMode] = useState<ExplorerMode>(filters.mode);
  const [selectedId, setSelectedId] = useState(filters.selectedId);
  const [returnTo, setReturnTo] = useState(initialReturnTo);
  const currentFilters = useMemo(() => ({ ...filters, mode, selectedId }), [filters, mode, selectedId]);

  useEffect(() => {
    if (filters.mode === "balanced") {
      const saved = localStorage.getItem("eretz:explorer-mode") as ExplorerMode | null;
      if (saved && modeLabels.some(([value]) => value === saved)) requestAnimationFrame(() => setMode(saved));
    }
    try {
      const state = JSON.parse(sessionStorage.getItem(`eretz:return:${initialReturnTo}`) ?? "null") as { scrollY?: number; selectedId?: string } | null;
      if (state?.selectedId) requestAnimationFrame(() => setSelectedId(state.selectedId ?? ""));
      if (typeof state?.scrollY === "number") requestAnimationFrame(() => window.scrollTo({ top: state.scrollY, behavior: "instant" }));
    } catch {
      // Navigation restoration is progressive enhancement.
    }
    const onUrl = (event: Event) => setReturnTo((event as CustomEvent<string>).detail);
    window.addEventListener("eretz:explorer-url-change", onUrl);
    return () => window.removeEventListener("eretz:explorer-url-change", onUrl);
  }, [filters.mode, initialReturnTo]);

  function chooseMode(next: ExplorerMode) {
    setMode(next);
    localStorage.setItem("eretz:explorer-mode", next);
    const url = new URL(window.location.href);
    if (next === "balanced") url.searchParams.delete("modo"); else url.searchParams.set("modo", next);
    const nextUrl = `${url.pathname}${url.search ? url.search : ""}`;
    window.history.replaceState(window.history.state, "", nextUrl);
    setReturnTo(nextUrl);
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

  return (
    <div className="explorer-page">
      <header className="explorer-toolbar">
        <div className="container">
          <div className="explorer-heading-row">
            <div><p className="eyebrow">Explorador nacional</p><h1>Encontrá propiedades en el mapa</h1></div>
            <div className="view-mode-tabs" role="group" aria-label="Modo de visualización">
              {modeLabels.map(([value, label]) => <button key={value} type="button" className={mode === value ? "is-active" : ""} aria-pressed={mode === value} title={label} onClick={() => chooseMode(value)}><span className="desktop-mode-label">{label}</span><span className="mobile-mode-label">{value.includes("map") ? "Mapa" : "Resultados"}</span></button>)}
            </div>
          </div>
          <FilterForm filters={currentFilters} action={basePath} />
        </div>
      </header>

      {result.invalidCursor ? <div className="container py-4"><div className="alert alert-warning" role="alert"><strong>Este enlace de paginación venció o no es válido.</strong><span> Podés volver al inicio de estos resultados sin perder tus filtros.</span><a href={`${basePath}?${resetCursor}`}>Volver a la primera página</a></div></div> : null}

      <main className={`explorer-workspace mode-${mode}`}>
        <section className="explorer-map-pane" aria-label="Explorar en el mapa">
          <PropertyMap properties={result.properties} filters={currentFilters} selectedId={selectedId} onSelect={selectProperty} returnTo={returnTo} />
        </section>
        <section className="explorer-results-pane" aria-label="Resultados de propiedades">
          <div className="results-summary">
            <p>{result.count !== null ? <><strong>{result.count.toLocaleString("es-AR")}</strong> propiedades permitidas</> : <><strong>Resultados filtrados</strong> · página {result.page.toLocaleString("es-AR")}</>}</p>
            <span>24 por página · orden neutral</span>
          </div>
          {result.error ? (
            <div className="state-panel" role="alert"><span aria-hidden="true">↻</span><h2>No pudimos cargar las propiedades</h2><p>El servicio puede estar temporalmente ocupado. Tus filtros siguen guardados en la URL.</p><a className="primary-button" href={returnTo}>Reintentar</a></div>
          ) : result.properties.length === 0 ? (
            <div className="state-panel"><span aria-hidden="true">⌕</span><h2>No encontramos propiedades</h2><p>Probá ampliar la ubicación, quitar un rango o restablecer los filtros.</p><a className="primary-button" href={basePath}>Restablecer filtros</a></div>
          ) : (
            <div className="explorer-card-list" id="property-results">
              {result.properties.map((property, index) => <PropertyCard key={property.id} property={property} priority={index < 2} returnTo={returnTo} selected={selectedId === property.id} onSelect={selectProperty} />)}
            </div>
          )}
          <Pagination filters={currentFilters} hasNext={result.hasNext} hasPrevious={result.hasPrevious} nextCursor={result.nextCursor} previousCursor={result.previousCursor} basePath={basePath} />
        </section>
      </main>
    </div>
  );
}
