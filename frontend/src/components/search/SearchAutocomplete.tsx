"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { SearchSuggestion } from "@/types/property";

const recentKey = "eretz:recent-searches:v1";

const CATEGORY_LABELS: Record<SearchSuggestion["category"], string> = {
  id: "Propiedad", provincia: "Provincia", ciudad: "Ciudad", barrio: "Barrio",
  dirección: "Dirección", inmobiliaria: "Inmobiliaria", agente: "Agente", tipo: "Tipo",
};

function readRecent(): SearchSuggestion[] {
  try {
    const values = JSON.parse(localStorage.getItem(recentKey) ?? "[]") as string[];
    return values.slice(0, 5).map((label) => ({ id: `recent:${label}`, label, category: "ciudad", query: label }));
  } catch {
    return [];
  }
}

export function rememberSearch(value: string) {
  const clean = value.trim().slice(0, 60);
  if (!clean) return;
  try {
    const current = JSON.parse(localStorage.getItem(recentKey) ?? "[]") as string[];
    localStorage.setItem(recentKey, JSON.stringify([clean, ...current.filter((item) => item !== clean)].slice(0, 5)));
  } catch {
    // Storage is an enhancement; search remains fully functional without it.
  }
}

export function SearchAutocomplete({ defaultValue }: { defaultValue: string }) {
  const listId = useId();
  const [value, setValue] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!open) return;
    if (value.trim().length < 2) {
      const frame = requestAnimationFrame(() => {
        setSuggestions(readRecent());
        setActive(-1);
      });
      return () => cancelAnimationFrame(frame);
    }
    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const response = await fetch(`/api/properties/suggestions?q=${encodeURIComponent(value.trim())}`, { signal: controller.signal });
        if (!response.ok) return;
        const payload = await response.json() as { suggestions: SearchSuggestion[] };
        setSuggestions(payload.suggestions);
        setActive(-1);
      } catch {
        // Abort and temporary suggestion failures never block regular form submission.
      }
    }, 260);
    return () => window.clearTimeout(timer);
  }, [open, value]);

  function choose(suggestion: SearchSuggestion) {
    rememberSearch(suggestion.query);
    setOpen(false);
    if (suggestion.href) { window.location.assign(suggestion.href); return; }
    setValue(suggestion.query);
  }

  return (
    <div className="search-combobox">
      <label className="sr-only" htmlFor={`${listId}-input`}>Buscar por ubicación, dirección, tipo, inmobiliaria, agente o ID</label>
      <span aria-hidden="true" className="search-icon">⌕</span>
      <input
        id={`${listId}-input`}
        name="q"
        type="search"
        autoComplete="off"
        value={value}
        placeholder="Ciudad, barrio, dirección, tipo, inmobiliaria, agente o ID"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open && suggestions.length > 0}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onChange={(event) => { setValue(event.target.value); setOpen(true); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((current) => Math.min(suggestions.length - 1, current + 1)); }
          if (event.key === "ArrowUp") { event.preventDefault(); setActive((current) => Math.max(0, current - 1)); }
          if (event.key === "Escape") { event.preventDefault(); setOpen(false); setActive(-1); }
          if (event.key === "Enter" && active >= 0 && suggestions[active]) { event.preventDefault(); choose(suggestions[active]); }
        }}
      />
      {open && suggestions.length > 0 ? (
        <ul id={listId} role="listbox" className="search-suggestions">
          {suggestions.map((suggestion, index) => (
            <li
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              key={suggestion.id}
              className={index === active ? "is-active" : ""}
              onMouseDown={(event) => { event.preventDefault(); choose(suggestion); }}
            >
              <span>{suggestion.label}</span>
              <small>{suggestion.id.startsWith("recent:") ? "Reciente" : CATEGORY_LABELS[suggestion.category]}</small>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
