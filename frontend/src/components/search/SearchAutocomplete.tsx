"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { interpretNaturalQuery } from "@/lib/nl-search";
import type { SearchSuggestion } from "@/types/property";

const recentKey = "eretz:recent-searches:v1";
const suggestionCache = new Map<string, SearchSuggestion[]>();

const CATEGORY_LABELS: Record<SearchSuggestion["category"], string> = {
  id: "Propiedad", provincia: "Provincia", ciudad: "Ciudad", barrio: "Barrio",
  dirección: "Dirección", inmobiliaria: "Inmobiliaria", agente: "Agente", tipo: "Tipo de propiedad",
};

function readRecent(): SearchSuggestion[] {
  try {
    const values = JSON.parse(localStorage.getItem(recentKey) ?? "[]") as string[];
    return values.slice(0, 5).map((label) => ({
      id: `recent:${label}`,
      label,
      category: "ciudad",
      query: label,
      context: "Búsqueda reciente",
    }));
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

function forgetSearch(value: string) {
  try {
    const current = JSON.parse(localStorage.getItem(recentKey) ?? "[]") as string[];
    localStorage.setItem(recentKey, JSON.stringify(current.filter((item) => item !== value)));
  } catch {
    // Storage is an enhancement; search remains fully functional without it.
  }
}

function SuggestionLabel({ label, query }: { label: string; query: string }) {
  const index = label.toLocaleLowerCase("es-AR").indexOf(query.toLocaleLowerCase("es-AR"));
  if (index < 0 || !query) return <>{label}</>;
  return <>{label.slice(0, index)}<mark>{label.slice(index, index + query.length)}</mark>{label.slice(index + query.length)}</>;
}

export function SearchAutocomplete({ defaultValue }: { defaultValue: string }) {
  const listId = useId();
  const [value, setValue] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [ignoredFields, setIgnoredFields] = useState<string[]>([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState<SearchSuggestion | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const interpretation = useMemo(() => interpretNaturalQuery(value), [value]);
  const visibleInterpretation = interpretation.interpreted.filter((chip) => !ignoredFields.includes(chip.field));

  useEffect(() => {
    const nl = new URLSearchParams(window.location.search).get("nl");
    if (nl) requestAnimationFrame(() => setValue(nl));
  }, []);

  useEffect(() => {
    if (!open) return;
    const clean = value.trim();
    if (clean.length < 2) {
      const frame = requestAnimationFrame(() => {
        setSuggestions(readRecent());
        setActive(-1);
      });
      return () => cancelAnimationFrame(frame);
    }
    const timer = window.setTimeout(async () => {
      const cached = suggestionCache.get(clean.toLocaleLowerCase("es-AR"));
      if (cached) {
        setSuggestions(cached);
        setActive(-1);
        return;
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const response = await fetch(`/api/properties/suggestions?q=${encodeURIComponent(clean)}`, { signal: controller.signal });
        if (!response.ok) return;
        const payload = await response.json() as { suggestions: SearchSuggestion[] };
        suggestionCache.set(clean.toLocaleLowerCase("es-AR"), payload.suggestions);
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
    setSelectedSuggestion(suggestion.id.startsWith("recent:") ? null : suggestion);
    setIgnoredFields([]);
  }

  function removeRecent(suggestion: SearchSuggestion) {
    forgetSearch(suggestion.query);
    setSuggestions(readRecent());
    setActive(-1);
  }

  return (
    <div className="search-combobox universal-search">
      <label className="sr-only" htmlFor={`${listId}-input`}>Buscá por barrio, ciudad, dirección, inmobiliaria, agente, tipo o ID ERETZ</label>
      <span aria-hidden="true" className="search-icon">⌕</span>
      <input
        id={`${listId}-input`}
        name="q"
        type="search"
        autoComplete="off"
        value={value}
        maxLength={200}
        placeholder="Buscá por barrio, ciudad, dirección, inmobiliaria o ID ERETZ"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open && suggestions.length > 0}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 140)}
        onChange={(event) => {
          setValue(event.target.value);
          setSelectedSuggestion(null);
          setIgnoredFields([]);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((current) => Math.min(suggestions.length - 1, current + 1)); }
          if (event.key === "ArrowUp") { event.preventDefault(); setActive((current) => Math.max(0, current - 1)); }
          if (event.key === "Escape") { event.preventDefault(); setOpen(false); setActive(-1); }
          if (event.key === "Enter" && active >= 0 && suggestions[active]) { event.preventDefault(); choose(suggestions[active]); }
        }}
      />
      {ignoredFields.map((field) => <input key={field} type="hidden" name="__nl_skip" value={field} />)}
      {selectedSuggestion ? <>
        <input type="hidden" name="__suggestion_category" value={selectedSuggestion.category} />
        <input type="hidden" name="__suggestion_value" value={selectedSuggestion.query} />
      </> : null}
      {open && suggestions.length > 0 ? (
        <ul id={listId} role="listbox" className="search-suggestions">
          {suggestions.map((suggestion, index) => {
            const recent = suggestion.id.startsWith("recent:");
            return (
              <li
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === active}
                key={suggestion.id}
                className={index === active ? "is-active" : ""}
                onMouseDown={(event) => { if (!(event.target as HTMLElement).closest("button")) { event.preventDefault(); choose(suggestion); } }}
              >
                <span className="suggestion-copy">
                  <strong><SuggestionLabel label={suggestion.label} query={value.trim()} /></strong>
                  <small>{recent ? "Búsqueda reciente" : [CATEGORY_LABELS[suggestion.category], suggestion.context].filter(Boolean).join(" · ")}</small>
                </span>
                {recent ? (
                  <button type="button" className="suggestion-remove" aria-label={`Borrar búsqueda reciente ${suggestion.label}`} onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); removeRecent(suggestion); }}>×</button>
                ) : <span className="suggestion-arrow" aria-hidden="true">→</span>}
              </li>
            );
          })}
        </ul>
      ) : null}
      {value.trim() && (visibleInterpretation.length > 0 || interpretation.notInterpreted.length > 0) ? (
        <div className="search-interpretation" aria-live="polite">
          {visibleInterpretation.length > 0 ? (
            <div className="interpretation-row">
              <span className="interpretation-label">Interpretamos</span>
              <div className="interpretation-chips">
                {visibleInterpretation.map((chip) => (
                  <button key={chip.field} type="button" className="interpretation-chip" aria-label={`No aplicar ${chip.label}`} onClick={() => setIgnoredFields((current) => [...current, chip.field])}>
                    {chip.label}<span aria-hidden="true"> ×</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {interpretation.notInterpreted.length > 0 ? (
            <div className="interpretation-row is-unrecognized">
              <span className="interpretation-label">No pudimos interpretar</span>
              <div className="interpretation-chips">
                {interpretation.notInterpreted.map((term) => <span key={term} className="interpretation-chip is-muted">{term}</span>)}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
