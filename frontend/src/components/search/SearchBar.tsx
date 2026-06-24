"use client";

import type { FormEvent } from "react";

type SearchBarProps = {
  query: string;
  onQueryChange: (query: string) => void;
};

export function SearchBar({ query, onQueryChange }: SearchBarProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = document.getElementById("properties");
    if (el) {
      const top = el.getBoundingClientRect().top + window.scrollY - 72;
      window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
  }

  return (
    <form className="flex gap-2" aria-label="Buscar propiedades" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="main-search">
        Buscar por barrio, ciudad o dirección
      </label>
      <input
        id="main-search"
        className="h-12 flex-1 rounded-md border border-ink-950/10 bg-white px-4 text-sm outline-none transition placeholder:text-ink-950/42 focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15"
        placeholder="Barrio, ciudad, dirección o inmobiliaria"
        type="search"
        autoComplete="off"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
      />
      <button
        className="h-12 shrink-0 rounded-md bg-ink-950 px-6 text-sm font-semibold text-white transition hover:bg-ink-800 focus:outline-none focus:ring-4 focus:ring-ink-950/20"
        type="submit"
      >
        Buscar
      </button>
    </form>
  );
}
