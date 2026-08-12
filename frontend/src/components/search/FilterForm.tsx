"use client";

import { useEffect, useRef, useState } from "react";
import { SearchAutocomplete, rememberSearch } from "@/components/search/SearchAutocomplete";
import { activeChips } from "@/components/explorer/ActiveChips";
import { FILTER_GROUPS, filterGroupCounts } from "@/lib/filter-groups";
import type { PropertyFilters } from "@/types/property";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

// Grupo de filtros con contador de activos. El contador se omite en 0 para no
// agregar ruido, y el nombre accesible incluye el texto visible.
// Un grupo es a la vez destino de la navegación lateral y panel de contenido.
// Todos quedan en el DOM (no se desmontan) para que el formulario envíe siempre
// el conjunto completo de filtros, aunque sólo uno esté visible.
function FilterGroup({ id, label, hint, count, children }: {
  id: string; label: string; hint: string; count: number; children: React.ReactNode;
}) {
  return (
    <fieldset className="filter-group" id={`filter-group-${id}`} data-group={id}>
      <legend className="filter-group-legend">
        <span className="filter-group-name">{label}</span>
        {count > 0 ? <span className="filter-group-count">{count}</span> : null}
        <span className="filter-group-hint">{hint}</span>
      </legend>
      <div className="filter-grid">{children}</div>
    </fieldset>
  );
}

// Navegación lateral de categorías: cada entrada lleva su contador propio y el
// subtítulo que describe qué contiene, como en la referencia.
function FilterNav({ counts, active, onSelect }: {
  counts: Record<string, number>; active: string; onSelect: (id: string) => void;
}) {
  return (
    <nav className="filter-nav" aria-label="Categorías de filtros">
      {FILTER_GROUPS.map((group) => {
        const count = counts[group.id] ?? 0;
        return (
          <button
            key={group.id}
            type="button"
            className={`filter-nav-item${active === group.id ? " is-active" : ""}`}
            aria-current={active === group.id ? "true" : undefined}
            onClick={() => onSelect(group.id)}
          >
            <span className="filter-nav-label">
              {group.label}
              {count > 0 ? <span className="filter-group-count">{count}</span> : null}
            </span>
            <span className="filter-nav-hint">{group.hint}</span>
          </button>
        );
      })}
    </nav>
  );
}

// Contrato único UI -> URL. Reutilizado por el modal y por el panel fijado.
function submitFilters(event: React.FormEvent<HTMLFormElement>, action: string) {
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
}

// Búsqueda + operación + tipo (filtros rápidos siempre visibles).
function QuickSelectors({ filters }: { filters: PropertyFilters }) {
  return (
    <>
      <SearchAutocomplete defaultValue={filters.q} />
      <select aria-label="Operación" name="operacion" defaultValue={filters.operation}>
        <option value="">Comprar o alquilar</option>
        <option value="venta">Comprar</option>
        <option value="alquiler">Alquilar</option>
        <option value="temporario">Temporario</option>
        <option value="venta_y_alquiler">Venta y alquiler</option>
        <option value="consultar">Consultar</option>
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
        <option value="otro">Otro</option>
      </select>
    </>
  );
}

// Campos avanzados (compartidos por modal y panel fijado). Solo filtros con
// respaldo de datos reales del catálogo público (ver DESKTOP_FILTER_MATRIX.md).
// `active` lo consume el contenedor via data-active: la visibilidad del grupo se
// resuelve en CSS para que todos los campos sigan en el DOM y el formulario
// envie siempre el conjunto completo de filtros.
export function AdvancedFilterFields({ filters }: { filters: PropertyFilters; active?: string }) {
  const counts = filterGroupCounts(filters);
  return (
    <>
      {filters.near ? (
        <>
          <input type="hidden" name="cerca_lat" value={filters.near.lat} />
          <input type="hidden" name="cerca_lng" value={filters.near.lng} />
        </>
      ) : null}
      <FilterGroup id="ubicacion" label={FILTER_GROUPS[0].label} hint={FILTER_GROUPS[0].hint} count={counts.ubicacion}>
        <Field label="Provincia"><input name="provincia" defaultValue={filters.province} placeholder="Buenos Aires" /></Field>
        <Field label="Ciudad"><input name="ciudad" defaultValue={filters.city} placeholder="Córdoba" /></Field>
        <Field label="Barrio o localidad"><input name="barrio" defaultValue={filters.neighborhood} placeholder="Palermo" /></Field>
        <Field label="Varias ubicaciones (separá con comas)"><input name="ubicaciones" defaultValue={filters.locations.join(", ")} placeholder="Palermo, Belgrano, Núñez" /></Field>
      </FilterGroup>
      <FilterGroup id="precio" label={FILTER_GROUPS[1].label} hint={FILTER_GROUPS[1].hint} count={counts.precio}>
        <Field label="Moneda"><select name="moneda" defaultValue={filters.currency}><option value="">Cualquiera</option><option>USD</option><option>ARS</option><option>EUR</option><option>UYU</option></select></Field>
        <Field label="Precio mínimo"><input name="precio_min" inputMode="numeric" type="number" min="0" defaultValue={filters.minPrice ?? ""} /></Field>
        <Field label="Precio máximo"><input name="precio_max" inputMode="numeric" type="number" min="0" defaultValue={filters.maxPrice ?? ""} /></Field>
        <Field label="Precio"><select name="precio" defaultValue={filters.priceMode}><option value="">Todas</option><option value="with">Con precio publicado</option><option value="consult">A consultar</option></select></Field>
      </FilterGroup>
      <FilterGroup id="caracteristicas" label={FILTER_GROUPS[2].label} hint={FILTER_GROUPS[2].hint} count={counts.caracteristicas}>
        <Field label="Ambientes mín."><input name="ambientes" type="number" min="1" max="30" defaultValue={filters.minRooms ?? ""} /></Field>
        <Field label="Dormitorios mín."><input name="dormitorios" type="number" min="1" max="30" defaultValue={filters.minBedrooms ?? ""} /></Field>
        <Field label="Baños mín."><input name="banos" type="number" min="1" max="20" defaultValue={filters.minBathrooms ?? ""} /></Field>
        <Field label="Superficie total mín."><input name="superficie" type="number" min="1" defaultValue={filters.minArea ?? ""} /></Field>
        <Field label="Superficie total máx."><input name="superficie_max" type="number" min="1" defaultValue={filters.maxArea ?? ""} /></Field>
        <div className="filter-checks">
          <label className="check"><input name="ubicacion" value="1" type="checkbox" defaultChecked={filters.hasLocation} /> Con ubicación en mapa</label>
          <label className="check"><input name="imagenes" value="1" type="checkbox" defaultChecked={filters.hasImages} /> Con imágenes</label>
        </div>
      </FilterGroup>
      <FilterGroup id="publicacion" label={FILTER_GROUPS[3].label} hint={FILTER_GROUPS[3].hint} count={counts.publicacion}>
        <Field label="Inmobiliaria o publicador"><input name="publicador" defaultValue={filters.publisher} placeholder="Nombre" /></Field>
        {/* Apto crédito: infraestructura tri-state lista (parse/query NULL-safe/chip),
            pero el control se oculta mientras apto_credito sea ~100% NULL en el
            catálogo, para no ofrecer un filtro sin respaldo de datos reales. */}
        <Field label="Publicado"><select name="reciente" defaultValue={filters.recentDays ?? ""}><option value="">Cualquier fecha</option><option value="1">Últimas 24 horas</option><option value="7">Últimos 7 días</option><option value="30">Últimos 30 días</option><option value="90">Últimos 90 días</option></select></Field>
        <Field label="Orden"><select name="orden" defaultValue={filters.sort}><option value="recent">Incorporadas recientemente</option><option value="price_asc" disabled={!filters.currency}>Menor precio</option><option value="price_desc" disabled={!filters.currency}>Mayor precio</option><option value="area_desc">Mayor superficie</option><option value="rooms_desc">Más ambientes</option><option value="price_m2_asc" disabled={!filters.currency}>Menor precio por m²</option>{filters.near ? <option value="nearest">Más cercanas</option> : null}</select></Field>
      </FilterGroup>
      {!filters.currency && (filters.sort === "price_asc" || filters.sort === "price_desc" || filters.sort === "price_m2_asc") ? <p className="filter-warning">Elegí una moneda para comparar precios sin mezclar unidades.</p> : null}
    </>
  );
}

export function FilterForm({
  filters,
  action = "/",
  pinned = false,
  onPin,
  onUnpin,
}: {
  filters: PropertyFilters;
  action?: string;
  pinned?: boolean;
  onPin?: () => void;
  onUnpin?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState<string>(FILTER_GROUPS[0].id);
  const activeCount = activeChips(filters).length;
  const panelRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  function closePanel() {
    setOpen(false);
    requestAnimationFrame(() => toggleRef.current?.focus());
  }

  useEffect(() => {
    if (pinned || !open) return;
    panelRef.current?.querySelector<HTMLElement>("input, select, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { closePanel(); return; }
      if (event.key !== "Tab") return;
      const focusable = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((element) => element.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, pinned]);

  if (pinned) {
    return (
      <form action={action} className="explorer-filter-form is-pinned" onSubmit={(event) => submitFilters(event, action)} aria-label="Panel de filtros fijado">
        <input type="hidden" name="modo" value={filters.mode} />
        <div className="filter-panel-header">
          <div><p className="eyebrow">Análisis</p><h2>Filtros fijados</h2></div>
          {onUnpin ? <button type="button" className="secondary-button" onClick={onUnpin}>Desfijar</button> : null}
        </div>
        <div className="explorer-primary-search is-stacked"><QuickSelectors filters={filters} /></div>
        <AdvancedFilterFields filters={filters} />
        <div className="filter-panel-actions">
          <a href={action} className="secondary-button">Limpiar</a>
          <button className="primary-button" type="submit">Aplicar</button>
        </div>
      </form>
    );
  }

  return (
    <form action={action} className="explorer-filter-form" onSubmit={(event) => submitFilters(event, action)}>
      <input type="hidden" name="modo" value={filters.mode} />
      <div className="explorer-primary-search">
        <QuickSelectors filters={filters} />
        {/* El nombre accesible contiene el texto visible (evita el
            label-content-name-mismatch de Lighthouse). */}
        <button ref={toggleRef} className="filter-toggle" type="button" aria-expanded={open} aria-controls="advanced-filters" onClick={() => setOpen(true)}>
          <span>{activeCount ? `Más filtros (${activeCount})` : "Más filtros"}</span>
          <span aria-hidden="true" className="filter-toggle-icon">+</span>
        </button>
        <button className="primary-button explorer-search-button" type="submit">Buscar</button>
      </div>
      {open ? <>
      <button className="filter-backdrop" type="button" aria-label="Cerrar filtros" onClick={closePanel} />
      <div id="advanced-filters" ref={panelRef} className="filter-panel is-open" role="dialog" aria-modal="true" aria-label="Filtros de propiedades">
        <div className="filter-panel-header">
          <h2>Filtros{activeCount ? <span className="filter-panel-count">{activeCount} activos</span> : null}</h2>
          <div className="filter-panel-header-actions">
            {onPin ? <button type="button" className="secondary-button" onClick={() => { onPin(); closePanel(); }}>Fijar panel</button> : null}
            <button className="icon-button" type="button" aria-label="Cerrar filtros" onClick={closePanel}>×</button>
          </div>
        </div>
        {/* Master-detail: la navegación de categorías queda a la izquierda con las
            acciones al pie, y el contenido del grupo elegido a la derecha. */}
        <div className="filter-panel-body">
          <div className="filter-panel-aside">
            <FilterNav counts={filterGroupCounts(filters)} active={activeGroup} onSelect={setActiveGroup} />
            <div className="filter-panel-actions">
              <a href={action} className="secondary-button">Limpiar</a>
              <button className="primary-button" type="submit">Aplicar</button>
            </div>
          </div>
          <div className="filter-panel-content" data-active={activeGroup}>
            <AdvancedFilterFields filters={filters} active={activeGroup} />
          </div>
        </div>
      </div>
      </> : null}
    </form>
  );
}
