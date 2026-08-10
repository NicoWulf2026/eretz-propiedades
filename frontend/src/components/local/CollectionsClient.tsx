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
  if (ids.length === 0) return <p className="mt-3 text-sm text-slate-600">Esta colección está vacía. Agregá propiedades desde su ficha.</p>;
  if (loading) return <p className="mt-3 text-sm text-slate-600">Cargando…</p>;
  if (error) return <p className="mt-3 text-sm text-slate-600">No pudimos cargar estas propiedades.</p>;
  return (
    <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {properties.map((p) => (
        <div key={p.id}>
          <PropertyCard property={p} variant="full" returnTo="/colecciones" />
          <button type="button" className="secondary-button mt-2 w-full" onClick={() => onRemove(p.id)}>Quitar de la colección</button>
        </div>
      ))}
      {properties.length < ids.length ? <p className="col-span-full text-xs text-slate-500">Algunas propiedades ya no están disponibles.</p> : null}
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
          <h1 className="text-3xl font-black tracking-[-0.03em] text-[#0b2748]">Colecciones</h1>
          <p className="mt-2 text-sm text-slate-600">Organizá propiedades en listas con nombre. Se guardan en este dispositivo, sin cuenta.</p>
        </div>
        <Link href="/favoritos" className="secondary-button">Mi actividad</Link>
      </header>

      <form
        className="mb-6 flex max-w-xl gap-2"
        onSubmit={(e) => { e.preventDefault(); const n = newName.trim(); if (!n) return; const c = createCollection(n); setNewName(""); setSelected(c.id); }}
      >
        <label className="sr-only" htmlFor="new-collection">Nombre de la nueva colección</label>
        <input id="new-collection" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={60} placeholder="Nueva colección (ej. Para visitar, Finalistas)" className="flex-1 rounded-lg border border-slate-300 px-3 py-2" />
        <button type="submit" className="primary-button">Crear</button>
      </form>

      {/* Favoritos como colección compatible (no se pierde) */}
      <section className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="font-bold text-[#0b2748]">Favoritos <span className="text-slate-500">({favorites.length})</span></p>
          <Link href="/favoritos" className="text-sm font-bold text-[#2166a5]">Ver favoritos →</Link>
        </div>
      </section>

      {collections.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Todavía no creaste colecciones. Creá una arriba y luego agregá propiedades desde su ficha.</p>
      ) : (
        <ul className="grid gap-3">
          {collections.map((c) => (
            <li key={c.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                {renaming === c.id ? (
                  <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); renameCollection(c.id, renameValue); setRenaming(null); }}>
                    <input autoFocus value={renameValue} onChange={(e) => setRenameValue(e.target.value)} maxLength={60} className="flex-1 rounded-lg border border-slate-300 px-2 py-1" />
                    <button type="submit" className="secondary-button">Guardar</button>
                    <button type="button" className="secondary-button" onClick={() => setRenaming(null)}>Cancelar</button>
                  </form>
                ) : (
                  <>
                    <button type="button" className="text-left text-base font-bold text-[#0b2748]" onClick={() => setSelected(selected === c.id ? null : c.id)} aria-expanded={selected === c.id}>
                      {c.name} <span className="text-slate-500">({c.ids.length})</span>
                    </button>
                    <div className="flex gap-2">
                      <button type="button" className="text-sm font-semibold text-[#2166a5]" onClick={() => setSelected(selected === c.id ? null : c.id)}>{selected === c.id ? "Ocultar" : "Ver"}</button>
                      <button type="button" className="text-sm font-semibold text-slate-600" onClick={() => { setRenaming(c.id); setRenameValue(c.name); }}>Renombrar</button>
                      <button type="button" className="text-sm font-semibold text-red-700" onClick={() => { if (selected === c.id) setSelected(null); deleteCollection(c.id); }}>Eliminar</button>
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
