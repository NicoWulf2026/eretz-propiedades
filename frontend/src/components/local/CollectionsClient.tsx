"use client";

import { useState } from "react";
import Link from "next/link";
import { PropertyCard } from "@/components/property/PropertyCard";
import { usePropertiesByIds } from "@/components/local/use-properties-by-ids";
import {
  createCollection,
  deleteCollection,
  getCollections,
  getFavorites,
  removeFromCollection,
  renameCollection,
} from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";

// Vista de las propiedades de una colección (fetch fresco gate-filtrado por ids).
function CollectionProperties({ ids, onRemove }: { ids: string[]; onRemove: (id: string) => void }) {
  const { properties, loading, error } = usePropertiesByIds(ids);
  if (ids.length === 0) return <p className="mt-3 text-sm u-text-muted">Esta colección está vacía. Agregá propiedades desde su ficha.</p>;
  if (loading) return <p className="mt-3 text-sm u-text-muted">Cargando…</p>;
  if (error) return <p className="mt-3 text-sm u-text-muted">No pudimos cargar estas propiedades.</p>;
  return (
    <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {properties.map((p) => (
        <div key={p.id}>
          <PropertyCard property={p} variant="grid" returnTo="/colecciones" />
          <button type="button" className="secondary-button mt-2 w-full" onClick={() => onRemove(p.id)}>Quitar de la colección</button>
        </div>
      ))}
      {properties.length < ids.length ? <p className="col-span-full text-xs u-text-faint">Algunas propiedades ya no están disponibles.</p> : null}
    </div>
  );
}

export function CollectionsClient() {
  const collections = useLocalValue(getCollections, []);
  const favorites = useLocalValue(getFavorites, []);
  const [selected, setSelected] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const openCollection = collections.find((c) => c.id === selected) ?? null;

  return (
    <div className="container py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Colecciones</h1>
          <p className="page-subtitle">Organizá propiedades en listas con nombre. Se guardan en este dispositivo, sin cuenta.</p>
        </div>
        <Link href="/favoritos" className="secondary-button">Mi actividad</Link>
      </header>

      <form
        className="mb-6 flex max-w-xl gap-2"
        onSubmit={(e) => { e.preventDefault(); const n = newName.trim(); if (!n) return; const c = createCollection(n); setNewName(""); setSelected(c.id); }}
      >
        <label className="sr-only" htmlFor="new-collection">Nombre de la nueva colección</label>
        <input id="new-collection" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={60} placeholder="Nueva colección (ej. Para visitar, Finalistas)" className="flex-1 rounded-lg border u-border-strong px-3 py-2" />
        <button type="submit" className="primary-button">Crear</button>
      </form>

      {/* Favoritos como colección compatible (no se pierde) */}
      <section className="mb-6 rounded-xl border u-border u-surface-sunken p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="font-bold text-[color:var(--ink)]">Favoritos <span className="u-text-faint">({favorites.length})</span></p>
          <Link href="/favoritos" className="text-sm font-bold text-[color:var(--accent-soft)]">Ver favoritos →</Link>
        </div>
      </section>

      {collections.length === 0 ? (
        <div className="state-panel">
          <span aria-hidden="true">▤</span>
          <h2>Todavía no tenés colecciones</h2>
          <p>Agrupá propiedades en listas con nombre —por ejemplo “Para visitar” o “Finalistas”— y volvé a encontrarlas cuando quieras. Se guardan en este dispositivo, sin cuenta.</p>
        </div>
      ) : (
        <ul className="grid gap-3">
          {collections.map((c) => (
            <li key={c.id} className="rounded-xl border u-border u-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                {renaming === c.id ? (
                  <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); renameCollection(c.id, renameValue); setRenaming(null); }}>
                    <input autoFocus value={renameValue} onChange={(e) => setRenameValue(e.target.value)} maxLength={60} className="flex-1 rounded-lg border u-border-strong px-2 py-1" />
                    <button type="submit" className="secondary-button">Guardar</button>
                    <button type="button" className="secondary-button" onClick={() => setRenaming(null)}>Cancelar</button>
                  </form>
                ) : (
                  <>
                    <button type="button" className="text-left text-base font-bold text-[color:var(--ink)]" onClick={() => setSelected(selected === c.id ? null : c.id)} aria-expanded={selected === c.id}>
                      {c.name} <span className="u-text-faint">({c.ids.length})</span>
                    </button>
                    <div className="flex gap-2">
                      <button type="button" className="text-sm font-semibold text-[color:var(--accent-soft)]" onClick={() => setSelected(selected === c.id ? null : c.id)}>{selected === c.id ? "Ocultar" : "Ver"}</button>
                      <button type="button" className="text-sm font-semibold u-text-muted" onClick={() => { setRenaming(c.id); setRenameValue(c.name); }}>Renombrar</button>
                      <button type="button" className="text-sm font-semibold u-bad-text" onClick={() => { if (selected === c.id) setSelected(null); deleteCollection(c.id); }}>Eliminar</button>
                    </div>
                  </>
                )}
              </div>
              {selected === c.id ? <CollectionProperties ids={c.ids} onRemove={(pid) => removeFromCollection(c.id, pid)} /> : null}
            </li>
          ))}
        </ul>
      )}

      {openCollection ? <p className="sr-only" role="status">Mostrando la colección {openCollection.name}</p> : null}
    </div>
  );
}
