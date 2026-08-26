"use client";

import { useEffect, useRef, useState } from "react";
import { PropertyImage } from "@/components/property/PropertyImage";

export function PropertyGallery({ images, title }: { images: string[]; title: string }) {
  const [selected, setSelected] = useState(0);
  const [modal, setModal] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      "button, [href], [tabindex]:not([tabindex='-1'])",
    );
    focusable?.[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setModal(false);
        return;
      }
      if (event.key === "ArrowLeft" && images.length > 1) {
        event.preventDefault();
        setSelected((current) => (current - 1 + images.length) % images.length);
        return;
      }
      if (event.key === "ArrowRight" && images.length > 1) {
        event.preventDefault();
        setSelected((current) => (current + 1) % images.length);
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previous?.focus();
    };
  }, [images.length, modal]);
  const image = images[selected] ?? null;
  return (
    <>
      {/* Mosaico 1+4: la imagen principal ocupa la mitad izquierda y hasta cuatro
          secundarias forman una grilla 2x2 a la derecha. Con menos de cinco fotos
          el mosaico degrada solo: la principal se expande al ancho disponible. */}
      <div className="ficha-gallery-mosaic">
        {image ? (
          <button type="button" className="ficha-gallery-main" onClick={() => setModal(true)} aria-label="Ampliar imagen">
            <PropertyImage src={image} alt={`${title}, imagen ${selected + 1}`} priority />
          </button>
        ) : (
          /* Sin fotos: placeholder sobrio en lugar de una superficie vacía. */
          <div className="gallery-empty" role="img" aria-label="Esta publicación no incluye fotos">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <circle cx="8.5" cy="9.5" r="1.5" />
              <path d="m21 16-5-5L9 18" />
            </svg>
            <span className="gallery-empty-text">Esta publicación no incluye fotos</span>
          </div>
        )}
        {images.length > 1 && (
          <div className="ficha-gallery-side" aria-hidden="true">
            {images.slice(1, 5).map((src, index) => (
              <button key={src} type="button" className="ficha-gallery-tile"
                      onClick={() => { setSelected(index + 1); setModal(true); }} tabIndex={-1}>
                <PropertyImage src={src} alt="" />
              </button>
            ))}
          </div>
        )}
        {images.length > 1 ? (
          <button
            type="button"
            className="ficha-gallery-open"
            onClick={() => { setSelected(0); setModal(true); }}
          >
            Ver todas las fotos <span aria-hidden="true">·</span> {images.length}
          </button>
        ) : null}
      </div>
      {modal && image && (
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Galería de fotos" className="gallery-dialog" onClick={() => setModal(false)}>
          <button type="button" className="gallery-close absolute right-4 top-4 grid size-12 place-items-center rounded-full text-2xl" onClick={() => setModal(false)} aria-label="Cerrar galería">×</button>
          <p className="gallery-counter" aria-live="polite">Foto {selected + 1} de {images.length}</p>
          <div className="gallery-stage" onClick={(event) => event.stopPropagation()}>
            <PropertyImage src={image} alt={`${title}, imagen ampliada`} />
          </div>
          {images.length > 1 && (
            <div className="gallery-navigation" onClick={(event) => event.stopPropagation()}>
              <button className="secondary-button" type="button" onClick={() => setSelected((selected - 1 + images.length) % images.length)} aria-label="Ver foto anterior">← Anterior</button>
              <div className="gallery-modal-thumbs" aria-label="Elegir foto">
                {images.map((src, index) => (
                  <button key={`${src}-${index}`} type="button" className={index === selected ? "is-current" : ""} onClick={() => setSelected(index)} aria-label={`Ver foto ${index + 1}`} aria-current={index === selected ? "true" : undefined}>
                    <PropertyImage src={src} alt="" />
                  </button>
                ))}
              </div>
              <button className="secondary-button" type="button" onClick={() => setSelected((selected + 1) % images.length)} aria-label="Ver foto siguiente">Siguiente →</button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
