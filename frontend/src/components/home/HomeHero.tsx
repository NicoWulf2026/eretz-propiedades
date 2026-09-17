"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { interpretNaturalQuery } from "@/lib/nl-search";

// Hero del home: titular grande centrado y la tarjeta de búsqueda con el mismo
// intérprete de lenguaje natural que usa el explorador. El submit lleva a
// /propiedades con los parámetros ya resueltos, así que el deep-link resultante
// es idéntico al que produce el explorador.
export function HomeHero({ operations }: { operations: { value: string; label: string }[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [operation, setOperation] = useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams(interpretNaturalQuery(query).params as Record<string, string>);
    if (operation) params.set("operacion", operation);
    const qs = params.toString();
    router.push(qs ? `/propiedades?${qs}` : "/propiedades");
  }

  return (
    <section className="home-hero">
      <div className="container">
        <h1 className="home-hero-title">
          Encontrá propiedades<br />como te las imaginás
        </h1>
        <p className="home-hero-lede">
          Avisos de inmobiliarias de toda la Argentina, en un solo lugar y en el mapa.
        </p>

        <form className="home-search-card" onSubmit={submit} role="search" aria-label="Buscar propiedades">
          <label htmlFor="home-q" className="sr-only">Describí lo que buscás</label>
          <textarea
            id="home-q"
            className="home-search-input"
            rows={2}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Escribí como quieras: ej. depto 2 ambientes en Palermo hasta 200 mil dólares"
          />
          <div className="home-search-row">
            <div className="home-op-segment" role="group" aria-label="Tipo de operación">
              {operations.map((op) => (
                <button
                  key={op.value}
                  type="button"
                  className={operation === op.value ? "is-active" : ""}
                  aria-pressed={operation === op.value}
                  onClick={() => setOperation(operation === op.value ? "" : op.value)}
                >
                  {op.label}
                </button>
              ))}
            </div>
            <button type="submit" className="primary-button home-search-submit">Buscar</button>
          </div>
        </form>

        <p className="home-hero-links">
          <Link href="/propiedades?modo=map_only" prefetch={false}>Ver el mapa</Link>
          <Link href="/inmobiliarias" prefetch={false}>Inmobiliarias</Link>
          <Link href="/comparar" prefetch={false}>Comparar propiedades</Link>
        </p>
      </div>
    </section>
  );
}
