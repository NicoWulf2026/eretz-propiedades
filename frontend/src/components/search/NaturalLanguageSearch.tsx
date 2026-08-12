"use client";

import { useEffect, useState } from "react";
import { interpretNaturalQuery } from "@/lib/nl-search";
import { track } from "@/lib/analytics";

// Entrada opcional de lenguaje natural: texto → filtros ESTRUCTURADOS → navega al
// explorador con esos filtros (server-side). Conserva el texto original en `nl=`
// (restaurable/shareable) y muestra lo NO interpretado sin inventar filtros.
export function NaturalLanguageSearch({ basePath }: { basePath: string }) {
  const [text, setText] = useState("");
  const [notInterpreted, setNotInterpreted] = useState<string[]>([]);
  const [interpretedCount, setInterpretedCount] = useState<number | null>(null);

  // Restaura el texto original desde la URL (?nl=) sin romper la hidratación.
  useEffect(() => {
    const nl = new URLSearchParams(window.location.search).get("nl");
    if (!nl) return;
    const r = interpretNaturalQuery(nl);
    const raf = requestAnimationFrame(() => {
      setText(nl);
      setNotInterpreted(r.notInterpreted);
      setInterpretedCount(r.interpreted.length);
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = text.trim();
    if (!clean) return;
    const r = interpretNaturalQuery(clean);
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(r.params)) {
      if (typeof value === "string" && value) params.set(key, value);
    }
    params.set("nl", clean); // preserva el texto original (no es un filtro)
    // Sólo metadata no sensible (cantidades), nunca el texto completo.
    track("natural_language_search", { interpreted: r.interpreted.length, unrecognized: r.notInterpreted.length });
    window.location.assign(`${basePath}?${params.toString()}`);
  }

  return (
    <form onSubmit={submit} className="nl-search" role="search" aria-label="Búsqueda por lenguaje natural">
      <label className="sr-only" htmlFor="nl-input">Escribí lo que buscás con tus palabras</label>
      <input
        id="nl-input"
        name="nl"
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={200}
        placeholder="Escribí como quieras: ej. depto 2 ambientes en Palermo o Belgrano hasta 200 mil dólares"
        className="nl-search-input"
      />
      <button type="submit" className="primary-button">Interpretar y buscar</button>
      {interpretedCount === 0 ? (
        <p className="nl-note" role="note">No pudimos interpretar filtros de ese texto. Probá con tipo, ubicación, precio o ambientes.</p>
      ) : notInterpreted.length ? (
        <p className="nl-note" role="note">No interpretamos: {notInterpreted.join(", ")}. Si querés, agregalo como filtro manual.</p>
      ) : null}
    </form>
  );
}
