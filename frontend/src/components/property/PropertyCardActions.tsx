"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { inCompare, isFavorite, toggleCompare, toggleFavorite } from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";

export function PropertyCardActions({
  id,
  title,
  reportHref,
  onHide,
}: {
  id: string;
  title: string;
  reportHref: string;
  onHide: () => void;
}) {
  const fav = useLocalValue(() => isFavorite(id), false);
  const cmp = useLocalValue(() => inCompare(id), false);
  const [notice, setNotice] = useState("");
  const menuRef = useRef<HTMLDetailsElement>(null);

  const closeMenu = () => {
    if (menuRef.current) menuRef.current.open = false;
  };

  const onCompare = () => {
    const result = toggleCompare(id);
    setNotice(result.full ? "Podés comparar hasta 4 propiedades." : result.active ? "Agregada a comparar." : "Quitada de comparar.");
    closeMenu();
  };

  const onShare = async () => {
    const url = `${window.location.origin}/propiedad/${id}`;
    try {
      if (navigator.share) await navigator.share({ title, url });
      else {
        await navigator.clipboard?.writeText(url);
        setNotice("Enlace copiado.");
      }
    } catch { /* El usuario canceló o el navegador no dio permiso. */ }
    closeMenu();
  };

  const onHideProperty = () => {
    closeMenu();
    onHide();
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
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 20.5 4.9 13.8A4.8 4.8 0 0 1 12 7.3a4.8 4.8 0 0 1 7.1 6.5L12 20.5Z" />
        </svg>
      </button>
      <details
        ref={menuRef}
        className="card-more-menu"
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          event.preventDefault();
          closeMenu();
          menuRef.current?.querySelector<HTMLElement>("summary")?.focus();
        }}
      >
        <summary className="card-action-button" aria-label="Más acciones" title="Más acciones">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></svg>
        </summary>
        <div className="card-more-popover" role="group" aria-label="Más acciones de la propiedad">
          <button type="button" aria-pressed={cmp} onClick={onCompare}>
            {cmp ? "Quitar de comparar" : "Agregar a comparar"}
          </button>
          <button type="button" onClick={onShare}>Compartir</button>
          <button type="button" onClick={onHideProperty}>Ocultar propiedad</button>
          <Link href={reportHref} onClick={closeMenu}>Reportar publicación</Link>
        </div>
      </details>
      {notice ? (
        <span role="status" className="card-action-notice">{notice}</span>
      ) : null}
    </div>
  );
}
