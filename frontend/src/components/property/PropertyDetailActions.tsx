"use client";

import { useState } from "react";
import { inCompare, isFavorite, toggleCompare, toggleFavorite } from "@/lib/local-store";
import { propertyShareMessage } from "@/lib/property-share";
import { useLocalValue } from "@/lib/use-local-store";
import type { Property } from "@/types/property";

export function PropertyDetailActions({ property, canonical }: { property: Property; canonical: string }) {
  const favorite = useLocalValue(() => isFavorite(property.id), false);
  const compared = useLocalValue(() => inCompare(property.id), false);
  const [notice, setNotice] = useState("");

  async function share() {
    const text = propertyShareMessage(property, canonical);
    if (navigator.share) {
      try {
        await navigator.share({ title: property.title, text, url: canonical });
        return;
      } catch {
        return;
      }
    }
    try {
      await navigator.clipboard.writeText(text);
      setNotice("Datos y enlace copiados");
    } catch {
      window.prompt("Copiá los datos y el enlace", text);
    }
  }

  return (
    <div className="detail-quick-actions" aria-label="Acciones de la propiedad">
      <button type="button" className="secondary-button" aria-pressed={favorite} onClick={() => toggleFavorite(property.id)}>
        {favorite ? "Guardada" : "Guardar"}
      </button>
      <button
        type="button"
        className="secondary-button"
        aria-pressed={compared}
        onClick={() => {
          const result = toggleCompare(property.id);
          setNotice(result.full ? "Podés comparar hasta 4 propiedades" : "");
        }}
      >
        {compared ? "En comparación" : "Comparar"}
      </button>
      <button type="button" className="secondary-button" onClick={share}>Compartir</button>
      <span className="sr-only" aria-live="polite">{notice}</span>
    </div>
  );
}
