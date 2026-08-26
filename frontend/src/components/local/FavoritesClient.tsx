"use client";

import Link from "next/link";
import { PropertyCard } from "@/components/property/PropertyCard";
import { usePropertiesByIds } from "@/components/local/use-properties-by-ids";
import {
  clearHidden,
  clearRecentSearches,
  clearRecentViews,
  getCompare,
  getFavorites,
  getHidden,
  getRecentSearches,
  getRecentViews,
  removeRecentSearch,
} from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";

export function FavoritesClient({ view = "all", embedded = false }: { view?: "all" | "favorites" | "history" | "searches"; embedded?: boolean }) {
  const favorites = useLocalValue(getFavorites, []);
  const hidden = useLocalValue(getHidden, []);
  const compare = useLocalValue(getCompare, []);
  const recent = useLocalValue(getRecentViews, []);
  const searches = useLocalValue(getRecentSearches, []);
  const { properties, loading, error } = usePropertiesByIds(favorites);

  return (
    <div className={embedded ? "" : "container py-8"}>
      {!embedded ? <header className="mb-6">
        <h1 className="page-title">Mi actividad</h1>
        <p className="page-subtitle">
          Tus propiedades guardadas, comparaciones e historial quedan en este dispositivo.
        </p>
      </header> : null}

      {view === "all" || view === "favorites" ? <section aria-labelledby="fav-heading" className="mb-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="fav-heading" className="section-heading">
            Propiedades guardadas {favorites.length ? <span className="u-text-faint">({favorites.length})</span> : null}
          </h2>
          {compare.length ? (
            <Link href="/comparar" className="primary-button">Comparar ({compare.length})</Link>
          ) : null}
        </div>
        {favorites.length === 0 ? (
          <div className="state-panel mt-4">
            <span aria-hidden="true">★</span>
            <h2>Todavía no guardaste propiedades</h2>
            <p>Usá Guardar en cualquier propiedad para encontrarla acá más tarde. No hace falta crear una cuenta.</p>
            <Link className="primary-button" href="/propiedades">Explorar propiedades</Link>
          </div>
        ) : loading ? (
          <div className="local-list-skeleton mt-4" role="status" aria-label="Cargando propiedades guardadas">{Array.from({ length: 3 }, (_, index) => <span key={index} className="skeleton" />)}</div>
        ) : error ? (
          <p role="alert" className="mt-4 text-sm u-text-muted">No pudimos cargar tus favoritos. Reintentá en unos minutos.</p>
        ) : (
          <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((p) => (
              <PropertyCard key={p.id} property={p} variant="grid" returnTo="/favoritos" />
            ))}
            {properties.length < favorites.length ? (
              <p className="col-span-full text-xs u-text-faint">
                Algunos favoritos ya no están disponibles y no se muestran.
              </p>
            ) : null}
          </div>
        )}
      </section> : null}

      {(view === "all" || view === "history") && recent.length ? (
        <section aria-labelledby="recent-heading" className="mb-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="recent-heading" className="section-heading">Vistas recientemente</h2>
            <button type="button" className="secondary-button" onClick={clearRecentViews}>Limpiar</button>
          </div>
          <ul className="mt-4 divide-y divide-slate-100 rounded-xl border u-border">
            {recent.map((r) => (
              <li key={r.id}>
                <Link href={`/propiedad/${r.id}?volver=/favoritos`} className="flex items-center justify-between gap-3 p-3 hover:u-surface-sunken">
                  <span className="truncate text-sm font-semibold u-text">{r.title}</span>
                  <span className="shrink-0 text-sm u-text-muted">{r.price ?? "Consultar precio"}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : view === "history" ? <div className="state-panel"><span aria-hidden="true">◷</span><h2>Todavía no hay historial</h2><p>Las propiedades que abras van a aparecer acá, en orden reciente.</p><Link className="primary-button" href="/propiedades">Explorar propiedades</Link></div> : null}

      {(view === "all" || view === "searches") && searches.length ? (
        <section aria-labelledby="searches-heading" className="mb-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="searches-heading" className="section-heading">Búsquedas recientes</h2>
            <button type="button" className="secondary-button" onClick={clearRecentSearches}>Limpiar</button>
          </div>
          <ul className="mt-4 flex flex-wrap gap-2">
            {searches.map((s) => (
              <li key={s.url} className="inline-flex items-center gap-1 rounded-full border u-border u-surface pl-3">
                <Link href={s.url} className="py-1.5 text-sm font-semibold text-[color:var(--accent-soft)]">{s.label}</Link>
                <button
                  type="button"
                  aria-label={`Quitar la búsqueda ${s.label}`}
                  className="px-2 py-1 u-text-faint hover:u-text"
                  onClick={() => removeRecentSearch(s.url)}
                >
                  <span aria-hidden="true">✕</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : view === "searches" ? <div className="state-panel"><span aria-hidden="true">⌕</span><h2>Todavía no hay búsquedas</h2><p>Las búsquedas que realices se guardan en este dispositivo para retomarlas más tarde.</p><Link className="primary-button" href="/propiedades">Empezar una búsqueda</Link></div> : null}

      {(view === "all" || view === "history") && hidden.length ? (
        <section aria-labelledby="hidden-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="hidden-heading" className="section-heading">
              Propiedades ocultas <span className="u-text-faint">({hidden.length})</span>
            </h2>
            <button type="button" className="secondary-button" onClick={clearHidden}>Mostrar todas</button>
          </div>
          <p className="mt-3 text-sm u-text-muted">
            No aparecen en los resultados hasta que las restaures.
          </p>
        </section>
      ) : null}
    </div>
  );
}
