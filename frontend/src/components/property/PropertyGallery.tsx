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
      <div className="surface overflow-hidden">
        {image ? (
          <button type="button" className="block aspect-[16/10] w-full" onClick={() => setModal(true)} aria-label="Ampliar imagen">
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
          <div className="ficha-gallery-thumbs flex gap-2 overflow-x-auto p-3" aria-label="Miniaturas de la galería">
            {images.map((src, index) => (
              <button key={src} type="button" className={`h-16 w-24 shrink-0 overflow-hidden rounded-lg border-2 ${index === selected ? "border-[#2166a5]" : "border-transparent"}`} onClick={() => setSelected(index)} aria-label={`Ver imagen ${index + 1}`}>
                <PropertyImage src={src} alt="" />
              </button>
            ))}
          </div>
        )}
      </div>
      {modal && image && (
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Galería ampliada" className="fixed inset-0 z-[2000] grid place-items-center bg-black/90 p-4" onClick={() => setModal(false)}>
          <button type="button" className="absolute right-4 top-4 grid size-12 place-items-center rounded-full bg-white text-2xl text-black" onClick={() => setModal(false)} aria-label="Cerrar galería">×</button>
          <div className="h-[82vh] w-full max-w-6xl" onClick={(event) => event.stopPropagation()}>
            <PropertyImage src={image} alt={`${title}, imagen ampliada`} />
          </div>
          {images.length > 1 && (
            <div className="absolute inset-x-4 bottom-4 flex justify-center gap-3">
              <button className="secondary-button" type="button" onClick={() => setSelected((selected - 1 + images.length) % images.length)} aria-label="Ver imagen anterior">← Anterior</button>
              <button className="secondary-button" type="button" onClick={() => setSelected((selected + 1) % images.length)} aria-label="Ver imagen siguiente">Siguiente →</button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
