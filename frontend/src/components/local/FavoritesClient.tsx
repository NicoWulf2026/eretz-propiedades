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

export function FavoritesClient() {
  const favorites = useLocalValue(getFavorites, []);
  const hidden = useLocalValue(getHidden, []);
  const compare = useLocalValue(getCompare, []);
  const recent = useLocalValue(getRecentViews, []);
  const searches = useLocalValue(getRecentSearches, []);
  const { properties, loading, error } = usePropertiesByIds(favorites);

  return (
    <div className="container py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-black tracking-[-0.03em] text-[#0b2748]">Mi actividad</h1>
        <p className="mt-2 text-sm text-slate-600">
          Tus favoritos, comparación, propiedades vistas y ocultas se guardan en este dispositivo.
        </p>
      </header>

      <section aria-labelledby="fav-heading" className="mb-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="fav-heading" className="text-xl font-black text-[#0b2748]">
            Favoritos {favorites.length ? <span className="text-slate-500">({favorites.length})</span> : null}
          </h2>
          {compare.length ? (
            <Link href="/comparar" className="primary-button">Comparar ({compare.length})</Link>
          ) : null}
        </div>
        {favorites.length === 0 ? (
          <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            Todavía no guardaste favoritos. Tocá la estrella ☆ en cualquier propiedad para guardarla acá.
          </p>
        ) : loading ? (
          <p className="mt-4 text-sm text-slate-600">Cargando favoritos…</p>
        ) : error ? (
          <p className="mt-4 text-sm text-slate-600">No pudimos cargar tus favoritos. Reintentá en unos minutos.</p>
        ) : (
          <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((p) => (
              <PropertyCard key={p.id} property={p} variant="full" returnTo="/favoritos" />
            ))}
            {properties.length < favorites.length ? (
              <p className="col-span-full text-xs text-slate-500">
                Algunos favoritos ya no están disponibles y no se muestran.
              </p>
            ) : null}
          </div>
        )}
      </section>

      {recent.length ? (
        <section aria-labelledby="recent-heading" className="mb-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="recent-heading" className="text-xl font-black text-[#0b2748]">Vistas recientemente</h2>
            <button type="button" className="secondary-button" onClick={clearRecentViews}>Limpiar</button>
          </div>
          <ul className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200">
            {recent.map((r) => (
              <li key={r.id}>
                <Link href={`/propiedad/${r.id}?volver=/favoritos`} className="flex items-center justify-between gap-3 p-3 hover:bg-slate-50">
                  <span className="truncate text-sm font-semibold text-slate-800">{r.title}</span>
                  <span className="shrink-0 text-sm text-slate-600">{r.price ?? "Consultar precio"}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {searches.length ? (
        <section aria-labelledby="searches-heading" className="mb-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="searches-heading" className="text-xl font-black text-[#0b2748]">Búsquedas recientes</h2>
            <button type="button" className="secondary-button" onClick={clearRecentSearches}>Limpiar</button>
          </div>
          <ul className="mt-4 flex flex-wrap gap-2">
            {searches.map((s) => (
              <li key={s.url} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white pl-3">
                <Link href={s.url} className="py-1.5 text-sm font-semibold text-[#2166a5]">{s.label}</Link>
                <button
                  type="button"
                  aria-label={`Quitar la búsqueda ${s.label}`}
                  className="px-2 py-1 text-slate-500 hover:text-slate-800"
                  onClick={() => removeRecentSearch(s.url)}
                >
                  <span aria-hidden="true">✕</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {hidden.length ? (
        <section aria-labelledby="hidden-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="hidden-heading" className="text-xl font-black text-[#0b2748]">
              Propiedades ocultas <span className="text-slate-500">({hidden.length})</span>
            </h2>
            <button type="button" className="secondary-button" onClick={clearHidden}>Mostrar todas</button>
          </div>
          <p className="mt-3 text-sm text-slate-600">
            No aparecen en los resultados hasta que las restaures.
          </p>
        </section>
      ) : null}
    </div>
  );
}
