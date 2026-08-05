"use client";

import { useEffect, useRef, useState } from "react";
import { SearchAutocomplete, rememberSearch } from "@/components/search/SearchAutocomplete";
import type { PropertyFilters } from "@/types/property";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function FilterForm({ filters, action = "/" }: { filters: PropertyFilters; action?: string }) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  function closePanel() {
    setOpen(false);
    requestAnimationFrame(() => toggleRef.current?.focus());
  }

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("input, select, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePanel();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((element) => element.offsetParent !== null);
      if (!focusable.length) return;
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
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <form action={action} className="explorer-filter-form" onSubmit={(event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      rememberSearch(String(form.get("q") ?? ""));
      const params = new URLSearchParams();
      for (const [key, raw] of form.entries()) {
        const value = String(raw).trim();
        if (!value || (key === "modo" && value === "balanced")) continue;
        if (key === "orden" && value === "recent") continue;
        params.append(key, value);
      }
      window.location.assign(`${action}${params.size ? `?${params.toString()}` : ""}`);
    }}>
      <input type="hidden" name="modo" value={filters.mode} />
      <div className="explorer-primary-search">
        <SearchAutocomplete defaultValue={filters.q} />
        <select aria-label="Operación" name="operacion" defaultValue={filters.operation}>
          <option value="">Comprar o alquilar</option>
          <option value="venta">Comprar</option>
          <option value="alquiler">Alquilar</option>
          <option value="temporario">Temporario</option>
          <option value="venta_y_alquiler">Venta y alquiler</option>
        </select>
        <select aria-label="Tipo de propiedad" name="tipo" defaultValue={filters.propertyType}>
          <option value="">Todos los tipos</option>
          <option value="departamento">Departamento</option>
          <option value="casa">Casa</option>
          <option value="ph">PH</option>
          <option value="terreno">Terreno</option>
          <option value="oficina">Oficina</option>
          <option value="local">Local</option>
          <option value="cochera">Cochera</option>
          <option value="galpon">Galpón</option>
          <option value="campo">Campo</option>
        </select>
        <button ref={toggleRef} className="filter-toggle" type="button" aria-expanded={open} aria-controls="advanced-filters" onClick={() => setOpen(true)}>
          Filtros <span aria-hidden="true">＋</span>
        </button>
        <button className="primary-button explorer-search-button" type="submit">Buscar</button>
      </div>
      {open ? <>
      <button className="filter-backdrop" type="button" aria-label="Cerrar filtros" onClick={closePanel} />
      <div id="advanced-filters" ref={panelRef} className="filter-panel is-open" role="dialog" aria-modal="true" aria-label="Filtros de propiedades">
        <div className="filter-panel-header">
          <div><p className="eyebrow">Afinar búsqueda</p><h2>Filtros</h2></div>
          <button className="icon-button" type="button" aria-label="Cerrar filtros" onClick={closePanel}>×</button>
        </div>
        <div className="filter-grid">
          <Field label="Provincia"><input name="provincia" defaultValue={filters.province} placeholder="Buenos Aires" /></Field>
          <Field label="Ciudad"><input name="ciudad" defaultValue={filters.city} placeholder="Córdoba" /></Field>
          <Field label="Barrio o localidad"><input name="barrio" defaultValue={filters.neighborhood} placeholder="Palermo" /></Field>
          <Field label="Inmobiliaria o publicador"><input name="publicador" defaultValue={filters.publisher} placeholder="Nombre" /></Field>
          <Field label="Moneda"><select name="moneda" defaultValue={filters.currency}><option value="">Cualquiera</option><option>USD</option><option>ARS</option><option>EUR</option><option>UYU</option></select></Field>
          <Field label="Precio mínimo"><input name="precio_min" inputMode="numeric" type="number" min="0" defaultValue={filters.minPrice ?? ""} /></Field>
          <Field label="Precio máximo"><input name="precio_max" inputMode="numeric" type="number" min="0" defaultValue={filters.maxPrice ?? ""} /></Field>
          <Field label="Ambientes mín."><input name="ambientes" type="number" min="1" max="30" defaultValue={filters.minRooms ?? ""} /></Field>
          <Field label="Dormitorios mín."><input name="dormitorios" type="number" min="1" max="30" defaultValue={filters.minBedrooms ?? ""} /></Field>
          <Field label="Baños mín."><input name="banos" type="number" min="1" max="20" defaultValue={filters.minBathrooms ?? ""} /></Field>
          <Field label="Cocheras mín."><input name="cocheras" type="number" min="1" max="50" defaultValue={filters.minGarages ?? ""} /></Field>
          <Field label="Superficie total mín."><input name="superficie" type="number" min="1" defaultValue={filters.minArea ?? ""} /></Field>
          <Field label="Superficie total máx."><input name="superficie_max" type="number" min="1" defaultValue={filters.maxArea ?? ""} /></Field>
          <Field label="Superficie cubierta mín."><input name="superficie_cubierta" type="number" min="1" defaultValue={filters.minCoveredArea ?? ""} /></Field>
          <Field label="Terreno mín."><input name="terreno" type="number" min="1" defaultValue={filters.minLandArea ?? ""} /></Field>
          <Field label="Expensas máximas"><input name="expensas_max" type="number" min="0" defaultValue={filters.maxExpenses ?? ""} /></Field>
          <Field label="Antigüedad máxima"><input name="antiguedad_max" type="number" min="0" max="300" defaultValue={filters.maxAge ?? ""} /></Field>
          <Field label="Publicado"><select name="reciente" defaultValue={filters.recentDays ?? ""}><option value="">Cualquier fecha</option><option value="1">Últimas 24 horas</option><option value="7">Últimos 7 días</option><option value="30">Últimos 30 días</option><option value="90">Últimos 90 días</option></select></Field>
          <Field label="Orden"><select name="orden" defaultValue={filters.sort}><option value="recent">Incorporadas recientemente</option><option value="price_asc" disabled={!filters.currency}>Menor precio</option><option value="price_desc" disabled={!filters.currency}>Mayor precio</option><option value="area_desc">Mayor superficie</option><option value="rooms_desc">Más ambientes</option><option value="price_m2_asc" disabled={!filters.currency}>Menor precio por m²</option></select></Field>
        </div>
        <div className="filter-checks">
          <label className="check"><input name="ubicacion" value="1" type="checkbox" defaultChecked={filters.hasLocation} /> Con ubicación en mapa</label>
          <label className="check"><input name="imagenes" value="1" type="checkbox" defaultChecked={filters.hasImages} /> Con imágenes</label>
          <label className="check"><input name="precio" value="1" type="checkbox" defaultChecked={filters.hasPrice} /> Con precio</label>
          <label className="check"><input name="video" value="1" type="checkbox" defaultChecked={filters.hasVideo} /> Con video</label>
          <label className="check"><input name="plano" value="1" type="checkbox" defaultChecked={filters.hasFloorPlan} /> Con plano</label>
          <label className="check"><input name="credito" value="1" type="checkbox" defaultChecked={filters.mortgageEligible} /> Apto crédito confirmado</label>
        </div>
        {!filters.currency && (filters.sort === "price_asc" || filters.sort === "price_desc" || filters.sort === "price_m2_asc") ? <p className="filter-warning">Elegí una moneda para comparar precios sin mezclar unidades.</p> : null}
        <div className="filter-panel-actions">
          <a href={action} className="secondary-button">Restablecer</a>
          <button className="primary-button" type="submit">Ver resultados</button>
        </div>
      </div>
      </> : null}
    </form>
  );
}
