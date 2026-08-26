"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { CollectionsClient } from "@/components/local/CollectionsClient";
import { CompareClient } from "@/components/local/CompareClient";
import { FavoritesClient } from "@/components/local/FavoritesClient";

const sections = [
  ["guardadas", "Guardadas"],
  ["colecciones", "Colecciones"],
  ["comparar", "Comparar"],
  ["historial", "Historial"],
  ["busquedas", "Búsquedas"],
] as const;
type Section = (typeof sections)[number][0];

export function MiEretzClient() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const fromUrl = searchParams.get("seccion") as Section | null;
  const active: Section = fromUrl && sections.some(([id]) => id === fromUrl) ? fromUrl : "guardadas";

  const select = (section: Section) => {
    router.replace(`/mi-eretz?seccion=${section}`, { scroll: false });
  };
  const moveTab = (event: React.KeyboardEvent<HTMLButtonElement>, current: number) => {
    const key = event.key;
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(key)) return;
    event.preventDefault();
    const next = key === "Home" ? 0 : key === "End" ? sections.length - 1
      : (current + (key === "ArrowRight" ? 1 : -1) + sections.length) % sections.length;
    const section = sections[next][0];
    select(section);
    requestAnimationFrame(() => document.getElementById(`mi-eretz-tab-${section}`)?.focus());
  };

  return (
    <div className="container mi-eretz-shell">
      <header className="mi-eretz-header">
        <div>
          <p className="eyebrow">Tu espacio personal</p>
          <h1 className="page-title">Mi ERETZ</h1>
          <p className="page-subtitle">Guardá, organizá y compará propiedades sin perder el hilo.</p>
        </div>
        <p className="mi-eretz-local-note"><span aria-hidden="true">⌁</span> Todo está guardado en este dispositivo.</p>
      </header>
      <div className="mi-eretz-tabs" role="tablist" aria-label="Secciones de Mi ERETZ">
        {sections.map(([id, label], index) => (
          <button key={id} id={`mi-eretz-tab-${id}`} type="button" role="tab" aria-controls="mi-eretz-panel" aria-selected={active === id} tabIndex={active === id ? 0 : -1} className={active === id ? "is-active" : undefined} onClick={() => select(id)} onKeyDown={(event) => moveTab(event, index)}>{label}</button>
        ))}
      </div>
      <section id="mi-eretz-panel" className="mi-eretz-content" role="tabpanel" aria-labelledby={`mi-eretz-tab-${active}`} tabIndex={0}>
        {active === "guardadas" ? <FavoritesClient embedded view="favorites" /> : null}
        {active === "colecciones" ? <CollectionsClient embedded /> : null}
        {active === "comparar" ? <CompareClient embedded /> : null}
        {active === "historial" ? <FavoritesClient embedded view="history" /> : null}
        {active === "busquedas" ? <FavoritesClient embedded view="searches" /> : null}
      </section>
    </div>
  );
}
