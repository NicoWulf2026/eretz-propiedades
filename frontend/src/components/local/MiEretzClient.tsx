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
        {sections.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={active === id} className={active === id ? "is-active" : undefined} onClick={() => select(id)}>{label}</button>
        ))}
      </div>
      <section className="mi-eretz-content" role="tabpanel" aria-label={sections.find(([id]) => id === active)?.[1]}>
        {active === "guardadas" ? <FavoritesClient embedded view="favorites" /> : null}
        {active === "colecciones" ? <CollectionsClient embedded /> : null}
        {active === "comparar" ? <CompareClient embedded /> : null}
        {active === "historial" ? <FavoritesClient embedded view="history" /> : null}
        {active === "busquedas" ? <FavoritesClient embedded view="searches" /> : null}
      </section>
    </div>
  );
}
