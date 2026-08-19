"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { SearchAutocomplete, rememberSearch } from "@/components/search/SearchAutocomplete";
import { activeChips } from "@/components/explorer/ActiveChips";
import { FILTER_GROUPS, filterGroupCounts } from "@/lib/filter-groups";
import { interpretNaturalQuery } from "@/lib/nl-search";
import { filtersToSearchParams } from "@/lib/property-query";
import type { PropertyFilters, SearchSuggestion } from "@/types/property";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function FilterGroup({ id, prefix, label, hint, count, level, children }: {
  id: string; prefix: string; label: string; hint: string; count: number; level: string; children: React.ReactNode;
}) {
  return (
    <fieldset className="filter-group" id={`${prefix}-${id}`} data-group={id}>
      <legend className="filter-group-legend">
        <span className="filter-level">{level}</span>
        <span className="filter-group-heading">
          <span className="filter-group-name">{label}</span>
          {count > 0 ? <span className="filter-group-count">{count}</span> : null}
        </span>
        <span className="filter-group-hint">{hint}</span>
      </legend>
      <div className="filter-grid">{children}</div>
    </fieldset>
  );
}

const INTERNAL_FIELDS = new Set(["__nl_skip", "__suggestion_category", "__suggestion_value"]);
const SUGGESTION_PARAM: Partial<Record<SearchSuggestion["category"], string>> = {
  provincia: "provincia",
  ciudad: "ciudad",
  barrio: "barrio",
  inmobiliaria: "publicador",
  tipo: "tipo",
};

// Contrato único UI -> URL. El parser determinista sólo reemplaza q cuando
// encontró filtros explícitos y visibles; las selecciones manuales prevalecen.
export function buildFilterSearchParams(form: FormData): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, raw] of form.entries()) {
    if (INTERNAL_FIELDS.has(key)) continue;
    const value = String(raw).trim();
    if (!value || (key === "modo" && value === "balanced") || (key === "orden" && value === "recent")) continue;
    params.set(key, value);
  }

  const query = String(form.get("q") ?? "").trim();
  const suggestionCategory = String(form.get("__suggestion_category") ?? "") as SearchSuggestion["category"];
  const suggestionValue = String(form.get("__suggestion_value") ?? "").trim();
  const suggestionParam = SUGGESTION_PARAM[suggestionCategory];
  if (suggestionParam && suggestionValue) {
    params.delete("q");
    if (!params.has(suggestionParam)) params.set(suggestionParam, suggestionValue);
    return params;
  }

  if (!query) return params;
  const interpreted = interpretNaturalQuery(query);
  const skipped = new Set(form.getAll("__nl_skip").map(String));
  const applicable = interpreted.interpreted.filter((chip) => !skipped.has(chip.field));
  if (!applicable.length) return params;

  params.delete("q");
  for (const chip of applicable) {
    const value = interpreted.params[chip.field];
    if (typeof value === "string" && value && !params.has(chip.field)) params.set(chip.field, value);
  }
  params.set("nl", query);
  return params;
}

function submitFilters(event: React.FormEvent<HTMLFormElement>, action: string) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  rememberSearch(String(form.get("q") ?? ""));
  const params = buildFilterSearchParams(form);
  window.location.assign(`${action}${params.size ? `?${params.toString()}` : ""}`);
}

function quickLabel(prefix: string, values: Array<number | null>, fallback: string) {
  const chosen = values.filter((value): value is number => value !== null);
  return chosen.length ? `${prefix}: ${chosen.join(" / ")}+` : fallback;
}

function QuickSelectors({ filters, onOpenGroup }: { filters: PropertyFilters; onOpenGroup: (group: string) => void }) {
  const price = filters.minPrice !== null || filters.maxPrice !== null
    ? [filters.currency || null, filters.minPrice !== null ? `desde ${filters.minPrice.toLocaleString("es-AR")}` : null, filters.maxPrice !== null ? `hasta ${filters.maxPrice.toLocaleString("es-AR")}` : null].filter(Boolean).join(" ")
    : "Precio";
  return (
    <>
      <SearchAutocomplete defaultValue={filters.q} />
      <select aria-label="Operación" name="operacion" defaultValue={filters.operation}>
        <option value="">Operación</option>
        <option value="venta">Comprar</option>
        <option value="alquiler">Alquilar</option>
        <option value="temporario">Temporario</option>
        <option value="venta_y_alquiler">Venta y alquiler</option>
        <option value="consultar">Consultar</option>
      </select>
      <select aria-label="Tipo de propiedad" name="tipo" defaultValue={filters.propertyType}>
        <option value="">Tipo</option>
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
      <button className="quick-filter-button" type="button" onClick={() => onOpenGroup("precio")}>{price}</button>
      <button className="quick-filter-button" type="button" onClick={() => onOpenGroup("caracteristicas")}>
        {quickLabel("Amb. / dorm.", [filters.minRooms, filters.minBedrooms], "Ambientes")}
      </button>
    </>
  );
}

export function AdvancedFilterFields({ filters, idPrefix = "filter-group" }: { filters: PropertyFilters; idPrefix?: string }) {
  const counts = filterGroupCounts(filters);
  return (
    <>
      <FilterGroup id="ubicacion" prefix={idPrefix} label={FILTER_GROUPS[0].label} hint="Una ubicación o varias, siempre con jerarquía explícita" count={counts.ubicacion} level="Jerarquía geográfica">
        <Field label="Provincia"><input name="provincia" defaultValue={filters.province} placeholder="Buenos Aires" /></Field>
        <Field label="Ciudad"><input name="ciudad" defaultValue={filters.city} placeholder="Córdoba" /></Field>
        <Field label="Barrio o localidad"><input name="barrio" defaultValue={filters.neighborhood} placeholder="Palermo" /></Field>
        <Field label="Varias ubicaciones (separadas por comas)"><input name="ubicaciones" defaultValue={filters.locations.join(", ")} placeholder="Palermo, Belgrano, Núñez" /></Field>
      </FilterGroup>
      <FilterGroup id="precio" prefix={idPrefix} label={FILTER_GROUPS[1].label} hint="La falta de precio nunca se interpreta como cero" count={counts.precio} level="Acceso rápido">
        <Field label="Moneda"><select name="moneda" defaultValue={filters.currency}><option value="">Cualquiera</option><option>USD</option><option>ARS</option><option>EUR</option><option>UYU</option></select></Field>
        <Field label="Desde"><input name="precio_min" inputMode="numeric" type="number" min="0" defaultValue={filters.minPrice ?? ""} /></Field>
        <Field label="Hasta"><input name="precio_max" inputMode="numeric" type="number" min="0" defaultValue={filters.maxPrice ?? ""} /></Field>
        <Field label="Estado del precio"><select name="precio" defaultValue={filters.priceMode}><option value="">Todos, incluso a consultar</option><option value="with">Con precio publicado</option><option value="consult">Sólo a consultar</option></select></Field>
      </FilterGroup>
      <FilterGroup id="caracteristicas" prefix={idPrefix} label={FILTER_GROUPS[2].label} hint="Los criterios más usados, sin atributos vacíos del catálogo" count={counts.caracteristicas} level="Acceso rápido">
        <Field label="Ambientes mín."><input name="ambientes" type="number" min="1" max="30" defaultValue={filters.minRooms ?? ""} /></Field>
        <Field label="Dormitorios mín."><input name="dormitorios" type="number" min="1" max="30" defaultValue={filters.minBedrooms ?? ""} /></Field>
        <Field label="Baños mín."><input name="banos" type="number" min="1" max="20" defaultValue={filters.minBathrooms ?? ""} /></Field>
        <Field label="Cocheras mín."><input name="cocheras" type="number" min="1" max="20" defaultValue={filters.minGarages ?? ""} /></Field>
        <Field label="Superficie total mín."><input name="superficie" type="number" min="1" defaultValue={filters.minArea ?? ""} /></Field>
        <Field label="Superficie total máx."><input name="superficie_max" type="number" min="1" defaultValue={filters.maxArea ?? ""} /></Field>
        <Field label="Apto crédito"><select name="credito" defaultValue={filters.mortgageState}><option value="">Sin filtrar</option><option value="si">Sí</option><option value="no">No</option><option value="sininfo">Sin información</option></select></Field>
        <div className="filter-checks">
          <label className="check"><input name="imagenes" value="1" type="checkbox" defaultChecked={filters.hasImages} /> Con imágenes</label>
          <label className="check"><input name="ubicacion" value="1" type="checkbox" defaultChecked={filters.hasLocation} /> Con ubicación en mapa</label>
        </div>
      </FilterGroup>
      <FilterGroup id="publicacion" prefix={idPrefix} label={FILTER_GROUPS[3].label} hint="Publicador, vigencia y orden del listado" count={counts.publicacion} level="Más filtros">
        <Field label="Inmobiliaria o publicador"><input name="publicador" defaultValue={filters.publisher} placeholder="Nombre" /></Field>
        <Field label="Publicado"><select name="reciente" defaultValue={filters.recentDays ?? ""}><option value="">Cualquier fecha</option><option value="1">Últimas 24 horas</option><option value="7">Últimos 7 días</option><option value="30">Últimos 30 días</option><option value="90">Últimos 90 días</option></select></Field>
        <Field label="Orden"><select name="orden" defaultValue={filters.sort}><option value="recent">Incorporadas recientemente</option><option value="price_asc" disabled={!filters.currency}>Menor precio</option><option value="price_desc" disabled={!filters.currency}>Mayor precio</option><option value="area_desc">Mayor superficie</option><option value="rooms_desc">Más ambientes</option><option value="price_m2_asc" disabled={!filters.currency}>Menor precio por m²</option>{filters.near ? <option value="nearest">Más cercanas</option> : null}</select></Field>
      </FilterGroup>
      {!filters.currency && (filters.sort === "price_asc" || filters.sort === "price_desc" || filters.sort === "price_m2_asc") ? <p className="filter-warning">Elegí una moneda para comparar precios sin mezclar unidades.</p> : null}
      <p className="filter-data-note">ERETZ sólo muestra filtros respaldados por el catálogo actual. Los datos desconocidos no se convierten en “No”.</p>
    </>
  );
}

const QUICK_NAMES = new Set(["q", "operacion", "tipo"]);
const RESET_NAMES = new Set(["pagina", "cursor", "direccion"]);
const ADVANCED_NAMES = new Set([
  "provincia", "ciudad", "barrio", "ubicaciones", "precio_min", "precio_max", "moneda", "ambientes", "dormitorios", "banos",
  "cocheras", "superficie", "superficie_max", "credito", "publicador", "reciente", "imagenes", "precio", "ubicacion", "orden",
]);

function HiddenFilterState({ filters, includeAdvanced }: { filters: PropertyFilters; includeAdvanced: boolean }) {
  const params = filtersToSearchParams(filters);
  return <>{[...params.entries()].filter(([name]) => {
    if (QUICK_NAMES.has(name) || RESET_NAMES.has(name)) return false;
    if (ADVANCED_NAMES.has(name)) return includeAdvanced;
    return true;
  }).map(([name, value]) => <input key={`${name}:${value}`} type="hidden" name={name} value={value} />)}</>;
}

type CountState = { status: "idle" | "loading" | "ready" | "error"; count: number | null };

export function FilterForm({
  filters,
  action = "/",
  pinned = false,
  onPin,
  onUnpin,
  onOpenChange,
}: {
  filters: PropertyFilters;
  action?: string;
  pinned?: boolean;
  onPin?: () => void;
  onUnpin?: () => void;
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftVersion, setDraftVersion] = useState(0);
  const [countState, setCountState] = useState<CountState>({ status: "idle", count: null });
  const [panelTop, setPanelTop] = useState(0);
  const activeCount = activeChips(filters).length;
  const formRef = useRef<HTMLFormElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const pendingGroupRef = useRef("ubicacion");
  const instanceId = useId().replace(/:/g, "");
  const panelId = "advanced-filters";

  const closePanel = useCallback(() => {
    setOpen(false);
    onOpenChange?.(false);
    requestAnimationFrame(() => toggleRef.current?.focus());
  }, [onOpenChange]);

  function focusGroup(group: string) {
    const target = formRef.current?.querySelector<HTMLElement>(`[data-group="${group}"]`);
    target?.scrollIntoView({ block: "start", behavior: "smooth" });
    target?.querySelector<HTMLElement>("input, select, button")?.focus({ preventScroll: true });
  }

  function openGroup(group: string) {
    pendingGroupRef.current = group;
    if (pinned) { requestAnimationFrame(() => focusGroup(group)); return; }
    setOpen(true);
    onOpenChange?.(true);
    setDraftVersion((current) => current + 1);
  }

  useEffect(() => {
    if (pinned || !open) return;
    const position = () => {
      const toolbar = document.querySelector(".explorer-toolbar")?.getBoundingClientRect();
      setPanelTop(Math.max(0, Math.round(toolbar?.bottom ?? 0)));
    };
    position();
    window.addEventListener("resize", position);
    const frame = requestAnimationFrame(() => focusGroup(pendingGroupRef.current));
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") closePanel(); };
    window.addEventListener("keydown", onKey);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", position); window.removeEventListener("keydown", onKey); };
  }, [closePanel, open, pinned]);

  useEffect(() => {
    if ((!open && !pinned) || !formRef.current) return;
    const controller = new AbortController();
    setCountState({ status: "loading", count: null });
    const timer = window.setTimeout(async () => {
      try {
        if (!formRef.current) return;
        const params = buildFilterSearchParams(new FormData(formRef.current));
        const response = await fetch(`/api/properties/counts?${params.toString()}`, { signal: controller.signal });
        if (!response.ok) throw new Error("count unavailable");
        const payload = await response.json() as { count: number | null };
        setCountState(payload.count === null ? { status: "error", count: null } : { status: "ready", count: payload.count });
      } catch (error) {
        if ((error as Error).name !== "AbortError") setCountState({ status: "error", count: null });
      }
    }, draftVersion === 0 ? 0 : 380);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [draftVersion, open, pinned]);

  const cta = countState.status === "loading"
    ? "Calculando resultados…"
    : countState.status === "ready" && countState.count !== null
      ? `Ver ${countState.count.toLocaleString("es-AR")} propiedades`
      : "Aplicar filtros";

  if (pinned) {
    return (
      <form ref={formRef} action={action} className="explorer-filter-form is-pinned" onSubmit={(event) => submitFilters(event, action)} onChange={() => setDraftVersion((current) => current + 1)} aria-label="Panel de filtros fijado">
        <HiddenFilterState filters={filters} includeAdvanced={false} />
        <div className="filter-panel-header">
          <div><p className="eyebrow">Análisis</p><h2>Filtros fijados</h2></div>
          {onUnpin ? <button type="button" className="secondary-button" onClick={onUnpin}>Desfijar</button> : null}
        </div>
        <div className="explorer-primary-search is-stacked"><QuickSelectors filters={filters} onOpenGroup={openGroup} /></div>
        <AdvancedFilterFields filters={filters} idPrefix={`${instanceId}-group`} />
        <div className="filter-panel-actions">
          <a href={action} className="secondary-button">Limpiar</a>
          <button className="primary-button" type="submit">{cta}</button>
        </div>
      </form>
    );
  }

  return (
    <form ref={formRef} action={action} className="explorer-filter-form" onSubmit={(event) => submitFilters(event, action)} onChange={() => { if (open) setDraftVersion((current) => current + 1); }}>
      <HiddenFilterState filters={filters} includeAdvanced={!open} />
      <div className="explorer-primary-search">
        <QuickSelectors filters={filters} onOpenGroup={openGroup} />
        <button ref={toggleRef} className="filter-toggle" type="button" aria-expanded={open} aria-controls={panelId} onClick={() => openGroup("ubicacion")}>
          <span>{activeCount ? `Más filtros (${activeCount})` : "Más filtros"}</span>
          <span aria-hidden="true" className="filter-toggle-icon">+</span>
        </button>
        <button className="primary-button explorer-search-button" type="submit">Buscar</button>
      </div>
      {open ? (
        <div id={panelId} ref={panelRef} className="filter-panel is-open" role="dialog" aria-modal="false" aria-label="Más filtros de propiedades" style={{ top: panelTop }}>
          <div className="filter-panel-header">
            <div>
              <p className="eyebrow">Refiná sin perder el mapa</p>
              <h2>Más filtros{activeCount ? <span className="filter-panel-count">{activeCount} activos</span> : null}</h2>
            </div>
            <div className="filter-panel-header-actions">
              {onPin ? <button type="button" className="secondary-button" onClick={() => { onPin(); closePanel(); }}>Fijar panel</button> : null}
              <button className="icon-button" type="button" aria-label="Cerrar filtros" onClick={closePanel}>×</button>
            </div>
          </div>
          <div className="filter-panel-content">
            <AdvancedFilterFields filters={filters} idPrefix={`${instanceId}-group`} />
          </div>
          <div className="filter-panel-actions">
            <a href={action} className="secondary-button">Limpiar todo</a>
            <button className="primary-button" type="submit">{cta}</button>
            <span className="sr-only" aria-live="polite">{countState.status === "loading" ? "Actualizando cantidad de resultados" : cta}</span>
          </div>
        </div>
      ) : null}
    </form>
  );
}
