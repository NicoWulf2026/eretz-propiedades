"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { PropertyCurrency, PropertyOperation, PropertyType } from "@/types/property";

export type QuickFilters = {
  operation: "all" | PropertyOperation;
  propertyType: "all" | PropertyType;
  province: string | null;
  city: string | null;
  neighborhood: string | null;
  currency: "all" | PropertyCurrency;
  minPrice: number | null;
  maxPrice: number | null;
  minRooms: number | null;
  minBedrooms: number | null;
  minBathrooms: number | null;
  hasGarage: boolean;
  minTotalArea: number | null;
  maxTotalArea: number | null;
  minCoveredArea: number | null;
  maxCoveredArea: number | null;
  hasRealImage: boolean;
  hasCoordinates: boolean;
  recentlyPublished: boolean;
  mortgageEligible: boolean;
  onlyAvailable: boolean;
};

export const initialFilters: QuickFilters = {
  operation: "all",
  propertyType: "all",
  province: null,
  city: null,
  neighborhood: null,
  currency: "all",
  minPrice: null,
  maxPrice: null,
  minRooms: null,
  minBedrooms: null,
  minBathrooms: null,
  hasGarage: false,
  minTotalArea: null,
  maxTotalArea: null,
  minCoveredArea: null,
  maxCoveredArea: null,
  hasRealImage: false,
  hasCoordinates: false,
  recentlyPublished: false,
  mortgageEligible: false,
  onlyAvailable: false,
};

type FilterBarProps = {
  filters: QuickFilters;
  availableProvinces: string[];
  availableCities: string[];
  availableNeighborhoods: string[];
  onChange: (filters: QuickFilters) => void;
};

type PanelId = "operation" | "type" | "location" | "price" | "features" | "area" | "extras";

function cntOperation(f: QuickFilters) {
  return f.operation !== "all" ? 1 : 0;
}

function cntType(f: QuickFilters) {
  return f.propertyType !== "all" ? 1 : 0;
}

function cntLocation(f: QuickFilters) {
  return [f.province, f.city, f.neighborhood].filter(Boolean).length;
}

function cntPrice(f: QuickFilters) {
  return (
    (f.currency !== "all" ? 1 : 0) +
    (f.minPrice !== null ? 1 : 0) +
    (f.maxPrice !== null ? 1 : 0)
  );
}

function cntFeatures(f: QuickFilters) {
  return (
    (f.minRooms !== null ? 1 : 0) +
    (f.minBedrooms !== null ? 1 : 0) +
    (f.minBathrooms !== null ? 1 : 0) +
    (f.hasGarage ? 1 : 0)
  );
}

function cntArea(f: QuickFilters) {
  return [f.minTotalArea, f.maxTotalArea, f.minCoveredArea, f.maxCoveredArea].filter(
    (v) => v !== null,
  ).length;
}

function cntExtras(f: QuickFilters) {
  return (
    (f.hasRealImage ? 1 : 0) +
    (f.hasCoordinates ? 1 : 0) +
    (f.recentlyPublished ? 1 : 0) +
    (f.mortgageEligible ? 1 : 0) +
    (f.onlyAvailable ? 1 : 0)
  );
}

export function countAllFilters(f: QuickFilters) {
  return (
    cntOperation(f) +
    cntType(f) +
    cntLocation(f) +
    cntPrice(f) +
    cntFeatures(f) +
    cntArea(f) +
    cntExtras(f)
  );
}

function parseNumberInput(value: string): number | null {
  const digits = value.replace(/\D/g, "");
  if (!digits) return null;
  const n = parseInt(digits, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function secBtn(hasActive: boolean, isOpen: boolean) {
  if (hasActive) {
    return "flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-ink-950 px-3 text-sm font-semibold text-white shadow-sm transition hover:bg-ink-800 focus:outline-none focus:ring-2 focus:ring-ink-950/20";
  }

  if (isOpen) {
    return "flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-ink-950/16 bg-ink-950/6 px-3 text-sm font-medium text-ink-950 transition focus:outline-none";
  }

  return "flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-ink-950/10 bg-white px-3 text-sm font-medium text-ink-950/60 transition hover:border-ink-950/18 hover:bg-ink-950/[0.03] hover:text-ink-950/85 focus:outline-none";
}

function chipBtn(active: boolean) {
  return active
    ? "h-8 whitespace-nowrap rounded-md bg-ink-950 px-3 text-xs font-semibold text-white transition"
    : "h-8 whitespace-nowrap rounded-md border border-ink-950/10 bg-ink-950/[0.03] px-3 text-xs font-medium text-ink-950/60 transition hover:border-ink-950/16 hover:bg-ink-950/[0.06] hover:text-ink-950";
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`size-3 shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
      viewBox="0 0 10 6"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M1 1l4 4 4-4" />
    </svg>
  );
}

function CountBadge({ count, dark }: { count: number; dark: boolean }) {
  if (count === 0) return null;

  return (
    <span
      className={`flex size-[18px] items-center justify-center rounded-full text-[10px] font-bold tabular-nums ${
        dark ? "bg-white/22 text-white" : "bg-ink-950/10 text-ink-950/70"
      }`}
    >
      {count}
    </span>
  );
}

function SecLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-ink-950/38">
      {children}
    </p>
  );
}

const panelBase =
  "absolute top-full z-[80] mt-2 max-w-[min(92vw,24rem)] rounded-lg border border-ink-950/10 bg-white shadow-[0_16px_44px_rgba(6,21,40,0.16)]";

const selectCls =
  "h-9 w-full rounded-md border border-ink-950/10 bg-white px-2.5 text-sm font-medium text-ink-950 outline-none transition focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15";

const inputCls =
  "h-9 w-full rounded-md border border-ink-950/10 bg-white px-2.5 text-sm outline-none transition placeholder:text-ink-950/36 focus:border-gold-500 focus:ring-4 focus:ring-gold-500/15";

const OPERATION_OPTIONS: Array<{ value: PropertyOperation; label: string }> = [
  { value: "venta", label: "Venta" },
  { value: "alquiler", label: "Alquiler" },
  { value: "venta_y_alquiler", label: "Venta y alquiler" },
  { value: "temporario", label: "Temporario" },
  { value: "inversion", label: "En pozo" },
  { value: "consultar", label: "Consultar" },
];

const TYPE_OPTIONS: Array<{ value: PropertyType; label: string }> = [
  { value: "departamento", label: "Departamento" },
  { value: "casa", label: "Casa" },
  { value: "ph", label: "PH" },
  { value: "local", label: "Local" },
  { value: "oficina", label: "Oficina" },
  { value: "terreno", label: "Terreno" },
  { value: "otro", label: "Otro" },
];

const ROOMS_OPTIONS = [1, 2, 3, 4];
const BEDS_OPTIONS = [1, 2, 3, 4];
const BATHS_OPTIONS = [1, 2, 3];

export function FilterBar({
  filters,
  availableProvinces,
  availableCities,
  availableNeighborhoods,
  onChange,
}: FilterBarProps) {
  const [openPanel, setOpenPanel] = useState<PanelId | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (openPanel === null) return;

    function handlePointerDown(event: PointerEvent) {
      const root = rootRef.current;
      if (root && !root.contains(event.target as Node)) {
        setOpenPanel(null);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenPanel(null);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openPanel]);

  function toggle(id: PanelId) {
    setOpenPanel((prev) => (prev === id ? null : id));
  }

  const aOp = cntOperation(filters);
  const aType = cntType(filters);
  const aLoc = cntLocation(filters);
  const aPrice = cntPrice(filters);
  const aFeat = cntFeatures(filters);
  const aArea = cntArea(filters);
  const aExtra = cntExtras(filters);
  const aAll = aOp + aType + aLoc + aPrice + aFeat + aArea + aExtra;

  function setOperation(op: PropertyOperation) {
    onChange({ ...filters, operation: filters.operation === op ? "all" : op });
    setOpenPanel(null);
  }

  function setPropertyType(pt: PropertyType) {
    onChange({ ...filters, propertyType: filters.propertyType === pt ? "all" : pt });
    setOpenPanel(null);
  }

  function setProvince(value: string) {
    onChange({
      ...filters,
      province: value || null,
      city: null,
      neighborhood: null,
    });
  }

  function setCity(value: string) {
    onChange({ ...filters, city: value || null, neighborhood: null });
  }

  function setNeighborhood(value: string) {
    onChange({ ...filters, neighborhood: value || null });
    if (value) {
      setOpenPanel(null);
    }
  }

  return (
    <div ref={rootRef} className="relative z-30 flex flex-wrap items-center gap-1.5 overflow-visible">
      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "operation"}
          className={secBtn(aOp > 0, openPanel === "operation")}
          onClick={() => toggle("operation")}
        >
          Operación
          <CountBadge count={aOp} dark={aOp > 0} />
          <Chevron open={openPanel === "operation"} />
        </button>

        {openPanel === "operation" && (
          <div className={`${panelBase} left-0 p-3`} style={{ width: "min(92vw, 18rem)" }}>
            <SecLabel>Tipo de operación</SecLabel>
            <div className="flex flex-wrap gap-2">
              {OPERATION_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={chipBtn(filters.operation === value)}
                  onClick={() => setOperation(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "type"}
          className={secBtn(aType > 0, openPanel === "type")}
          onClick={() => toggle("type")}
        >
          Tipo
          <CountBadge count={aType} dark={aType > 0} />
          <Chevron open={openPanel === "type"} />
        </button>

        {openPanel === "type" && (
          <div className={`${panelBase} left-0 p-3`} style={{ width: "min(92vw, 18rem)" }}>
            <SecLabel>Tipo de propiedad</SecLabel>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {TYPE_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={chipBtn(filters.propertyType === value)}
                  onClick={() => setPropertyType(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "location"}
          className={secBtn(aLoc > 0, openPanel === "location")}
          onClick={() => toggle("location")}
        >
          Ubicación
          <CountBadge count={aLoc} dark={aLoc > 0} />
          <Chevron open={openPanel === "location"} />
        </button>

        {openPanel === "location" && (
          <div className={`${panelBase} left-0 space-y-2.5 p-4`} style={{ width: "min(92vw, 19rem)" }}>
            <div>
              <SecLabel>Provincia</SecLabel>
              <select
                className={selectCls}
                value={filters.province ?? ""}
                onChange={(e) => setProvince(e.target.value)}
              >
                <option value="">Todas las provincias</option>
                {availableProvinces.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <SecLabel>Ciudad</SecLabel>
              <select
                className={selectCls}
                value={filters.city ?? ""}
                onChange={(e) => setCity(e.target.value)}
              >
                <option value="">Todas las ciudades</option>
                {availableCities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>

            {availableNeighborhoods.length > 0 && (
              <div>
                <SecLabel>Barrio</SecLabel>
                <select
                  className={selectCls}
                  value={filters.neighborhood ?? ""}
                  onChange={(e) => setNeighborhood(e.target.value)}
                >
                  <option value="">Todos los barrios</option>
                  {availableNeighborhoods.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "price"}
          className={secBtn(aPrice > 0, openPanel === "price")}
          onClick={() => toggle("price")}
        >
          Precio
          <CountBadge count={aPrice} dark={aPrice > 0} />
          <Chevron open={openPanel === "price"} />
        </button>

        {openPanel === "price" && (
          <div className={`${panelBase} left-0 space-y-3 p-4`} style={{ width: "min(92vw, 18rem)" }}>
            <div>
              <SecLabel>Moneda</SecLabel>
              <div className="flex gap-2">
                {(["USD", "ARS"] as PropertyCurrency[]).map((cur) => (
                  <button
                    key={cur}
                    type="button"
                    className={chipBtn(filters.currency === cur)}
                    onClick={() =>
                      onChange({ ...filters, currency: filters.currency === cur ? "all" : cur })
                    }
                  >
                    {cur}
                  </button>
                ))}
                {filters.currency !== "all" && (
                  <button
                    type="button"
                    className={chipBtn(false)}
                    onClick={() => onChange({ ...filters, currency: "all" })}
                  >
                    Todas
                  </button>
                )}
              </div>
            </div>

            <div>
              <SecLabel>
                Desde{filters.currency !== "all" ? ` (${filters.currency})` : ""}
              </SecLabel>
              <input
                type="text"
                inputMode="numeric"
                className={inputCls}
                placeholder="Precio mínimo"
                value={filters.minPrice !== null ? String(filters.minPrice) : ""}
                onChange={(e) =>
                  onChange({ ...filters, minPrice: parseNumberInput(e.target.value) })
                }
              />
            </div>

            <div>
              <SecLabel>
                Hasta{filters.currency !== "all" ? ` (${filters.currency})` : ""}
              </SecLabel>
              <input
                type="text"
                inputMode="numeric"
                className={inputCls}
                placeholder="Precio máximo"
                value={filters.maxPrice !== null ? String(filters.maxPrice) : ""}
                onChange={(e) =>
                  onChange({ ...filters, maxPrice: parseNumberInput(e.target.value) })
                }
              />
            </div>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "features"}
          className={secBtn(aFeat > 0, openPanel === "features")}
          onClick={() => toggle("features")}
        >
          Características
          <CountBadge count={aFeat} dark={aFeat > 0} />
          <Chevron open={openPanel === "features"} />
        </button>

        {openPanel === "features" && (
          <div
            className={`${panelBase} left-0 space-y-3 p-4 sm:left-auto sm:right-0`}
            style={{ width: "min(92vw, 19rem)" }}
          >
            <div>
              <SecLabel>Ambientes</SecLabel>
              <div className="flex gap-1.5">
                {ROOMS_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={chipBtn(filters.minRooms === n)}
                    onClick={() =>
                      onChange({ ...filters, minRooms: filters.minRooms === n ? null : n })
                    }
                  >
                    {n}+
                  </button>
                ))}
              </div>
            </div>

            <div>
              <SecLabel>Dormitorios</SecLabel>
              <div className="flex gap-1.5">
                {BEDS_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={chipBtn(filters.minBedrooms === n)}
                    onClick={() =>
                      onChange({
                        ...filters,
                        minBedrooms: filters.minBedrooms === n ? null : n,
                      })
                    }
                  >
                    {n}+
                  </button>
                ))}
              </div>
            </div>

            <div>
              <SecLabel>Baños</SecLabel>
              <div className="flex gap-1.5">
                {BATHS_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={chipBtn(filters.minBathrooms === n)}
                    onClick={() =>
                      onChange({
                        ...filters,
                        minBathrooms: filters.minBathrooms === n ? null : n,
                      })
                    }
                  >
                    {n}+
                  </button>
                ))}
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-0.5 py-1 hover:bg-ink-950/[0.03]">
              <input
                type="checkbox"
                className="size-[15px] cursor-pointer accent-ink-950"
                checked={filters.hasGarage}
                onChange={(e) => onChange({ ...filters, hasGarage: e.target.checked })}
              />
              <span className="text-sm text-ink-950/70">Con cochera</span>
            </label>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "area"}
          className={secBtn(aArea > 0, openPanel === "area")}
          onClick={() => toggle("area")}
        >
          Superficie
          <CountBadge count={aArea} dark={aArea > 0} />
          <Chevron open={openPanel === "area"} />
        </button>

        {openPanel === "area" && (
          <div
            className={`${panelBase} left-0 space-y-3 p-4 sm:left-auto sm:right-0`}
            style={{ width: "min(92vw, 19rem)" }}
          >
            <div>
              <SecLabel>Total (m²)</SecLabel>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  className={inputCls}
                  placeholder="Mín."
                  value={filters.minTotalArea !== null ? String(filters.minTotalArea) : ""}
                  onChange={(e) =>
                    onChange({ ...filters, minTotalArea: parseNumberInput(e.target.value) })
                  }
                />
                <span className="shrink-0 text-xs text-ink-950/36">-</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className={inputCls}
                  placeholder="Máx."
                  value={filters.maxTotalArea !== null ? String(filters.maxTotalArea) : ""}
                  onChange={(e) =>
                    onChange({ ...filters, maxTotalArea: parseNumberInput(e.target.value) })
                  }
                />
              </div>
            </div>

            <div>
              <SecLabel>Cubierta (m²)</SecLabel>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  className={inputCls}
                  placeholder="Mín."
                  value={filters.minCoveredArea !== null ? String(filters.minCoveredArea) : ""}
                  onChange={(e) =>
                    onChange({ ...filters, minCoveredArea: parseNumberInput(e.target.value) })
                  }
                />
                <span className="shrink-0 text-xs text-ink-950/36">-</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className={inputCls}
                  placeholder="Máx."
                  value={filters.maxCoveredArea !== null ? String(filters.maxCoveredArea) : ""}
                  onChange={(e) =>
                    onChange({ ...filters, maxCoveredArea: parseNumberInput(e.target.value) })
                  }
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          aria-expanded={openPanel === "extras"}
          className={secBtn(aExtra > 0, openPanel === "extras")}
          onClick={() => toggle("extras")}
        >
          Extras
          <CountBadge count={aExtra} dark={aExtra > 0} />
          <Chevron open={openPanel === "extras"} />
        </button>

        {openPanel === "extras" && (
          <div
            className={`${panelBase} left-0 p-3 sm:left-auto sm:right-0`}
            style={{ width: "min(92vw, 17rem)" }}
          >
            <SecLabel>Opciones adicionales</SecLabel>
            <div className="space-y-0.5">
              {[
                {
                  key: "hasRealImage",
                  label: "Solo con fotos reales",
                  checked: filters.hasRealImage,
                  set: (v: boolean) => onChange({ ...filters, hasRealImage: v }),
                },
                {
                  key: "hasCoordinates",
                  label: "Con ubicación en mapa",
                  checked: filters.hasCoordinates,
                  set: (v: boolean) => onChange({ ...filters, hasCoordinates: v }),
                },
                {
                  key: "recentlyPublished",
                  label: "Publicado recientemente",
                  checked: filters.recentlyPublished,
                  set: (v: boolean) => onChange({ ...filters, recentlyPublished: v }),
                },
                {
                  key: "mortgageEligible",
                  label: "Apto crédito",
                  checked: filters.mortgageEligible,
                  set: (v: boolean) => onChange({ ...filters, mortgageEligible: v }),
                },
                {
                  key: "onlyAvailable",
                  label: "Solo disponibles",
                  checked: filters.onlyAvailable,
                  set: (v: boolean) => onChange({ ...filters, onlyAvailable: v }),
                },
              ].map(({ key, label, checked, set }) => (
                <label
                  key={key}
                  className="flex cursor-pointer items-center gap-2.5 rounded-md px-1 py-2 hover:bg-ink-950/[0.03]"
                >
                  <input
                    type="checkbox"
                    className="size-[15px] cursor-pointer accent-ink-950"
                    checked={checked}
                    onChange={(e) => set(e.target.checked)}
                  />
                  <span className="text-sm text-ink-950/70">{label}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {aAll > 0 && (
        <>
          <div className="mx-2 h-5 w-px bg-ink-950/10" aria-hidden="true" />
          <span className="text-xs text-ink-950/44">
            {aAll} {aAll === 1 ? "filtro activo" : "filtros activos"}
          </span>
          <button
            type="button"
            className="flex h-9 shrink-0 items-center gap-1 rounded-lg border border-red-200/70 bg-red-50 px-3 text-xs font-semibold text-red-600 transition hover:bg-red-100 focus:outline-none"
            onClick={() => {
              onChange(initialFilters);
              setOpenPanel(null);
            }}
          >
            <svg
              className="size-3"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M1 1l8 8M9 1L1 9" />
            </svg>
            Limpiar
          </button>
        </>
      )}
    </div>
  );
}
