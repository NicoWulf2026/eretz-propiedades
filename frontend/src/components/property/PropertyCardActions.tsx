"use client";

import { useState } from "react";
import { inCompare, isFavorite, toggleCompare, toggleFavorite } from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";

// Acciones locales por tarjeta (sin cuenta): favorito, comparar y ocultar.
// Botones reales con aria-pressed/aria-label; se ubican fuera del <Link> de la
// tarjeta para no anidar controles dentro de un enlace.
export function PropertyCardActions({
  id,
  onHide,
}: {
  id: string;
  onHide: () => void;
}) {
  const fav = useLocalValue(() => isFavorite(id), false);
  const cmp = useLocalValue(() => inCompare(id), false);
  const [notice, setNotice] = useState("");

  const onCompare = () => {
    const result = toggleCompare(id);
    setNotice(result.full ? "Podés comparar hasta 4 propiedades." : "");
  };

  return (
    <div className="property-card-actions" role="group" aria-label="Acciones de la propiedad">
      <button
        type="button"
        className="card-action-button"
        aria-pressed={fav}
        aria-label={fav ? "Quitar de favoritos" : "Agregar a favoritos"}
        title={fav ? "Quitar de favoritos" : "Agregar a favoritos"}
        onClick={() => toggleFavorite(id)}
      >
        <span aria-hidden="true">{fav ? "★" : "☆"}</span>
      </button>
      <button
        type="button"
        className="card-action-button"
        aria-pressed={cmp}
        aria-label={cmp ? "Quitar de comparar" : "Agregar a comparar"}
        title={cmp ? "Quitar de comparar" : "Agregar a comparar"}
        onClick={onCompare}
      >
        <span aria-hidden="true">⇄</span>
      </button>
      <button
        type="button"
        className="card-action-button"
        aria-label="Ocultar esta propiedad"
        title="Ocultar esta propiedad"
        onClick={onHide}
      >
        <span aria-hidden="true">✕</span>
      </button>
      {notice ? (
        <span role="status" className="card-action-notice">{notice}</span>
      ) : null}
    </div>
  );
}
