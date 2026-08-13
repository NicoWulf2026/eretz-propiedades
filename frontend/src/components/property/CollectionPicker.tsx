"use client";

import { useState } from "react";
import {
  addToCollection,
  collectionsWith,
  createCollection,
  getCollections,
  removeFromCollection,
} from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";

// Agrega/quita la propiedad actual a colecciones locales (sin cuenta). Permite
// crear una colección nueva en el momento.
export function CollectionPicker({ propertyId }: { propertyId: string }) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const collections = useLocalValue(getCollections, []);
  const membership = useLocalValue(() => collectionsWith(propertyId), []);

  return (
    <div className="collection-picker">
      <button type="button" className="secondary-button w-full" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Guardar en colección{membership.length ? ` (${membership.length})` : ""}
      </button>
      {open ? (
        <div className="collection-picker-panel" role="group" aria-label="Colecciones">
          {collections.length === 0 ? (
            <p className="text-sm u-text-muted">Todavía no tenés colecciones. Creá una:</p>
          ) : (
            <ul className="grid gap-1">
              {collections.map((c) => {
                const inIt = membership.includes(c.id);
                return (
                  <li key={c.id}>
                    <label className="flex items-center gap-2 text-sm u-text-muted">
                      <input
                        type="checkbox"
                        checked={inIt}
                        onChange={() => (inIt ? removeFromCollection(c.id, propertyId) : addToCollection(c.id, propertyId))}
                      />
                      {c.name} <span className="u-text-faint">({c.ids.length})</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => { e.preventDefault(); const n = newName.trim(); if (!n) return; const c = createCollection(n); addToCollection(c.id, propertyId); setNewName(""); }}
          >
            <label className="sr-only" htmlFor={`newcol-${propertyId}`}>Nueva colección</label>
            <input id={`newcol-${propertyId}`} value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={60} placeholder="Nueva colección" className="flex-1 rounded-lg border u-border-strong px-2 py-1 text-sm" />
            <button type="submit" className="secondary-button">Crear y agregar</button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
