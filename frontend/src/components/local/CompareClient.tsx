"use client";

import Link from "next/link";
import { usePropertiesByIds } from "@/components/local/use-properties-by-ids";
import { clearCompare, getCompare, toggleCompare } from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";
import { availabilityLabel, operationLabels, propertyLocation, propertyPrice, typeLabels } from "@/lib/property-presenter";
import type { PropertySummary } from "@/types/property";

// "Sin información" nunca equivale a 0 ni a "No": un dato ausente se muestra como
// desconocido, no como negativo.
const unknown = "Sin información";
const num = (v: number | null): string => (v == null ? unknown : String(v));
const area = (v: number | null): string => (v == null ? unknown : `${v} m²`);

const ROWS: { label: string; value: (p: PropertySummary) => string }[] = [
  { label: "Precio", value: propertyPrice },
  { label: "Operación", value: (p) => operationLabels[p.operation] },
  { label: "Tipo", value: (p) => typeLabels[p.propertyType] },
  { label: "Ubicación", value: propertyLocation },
  { label: "Ambientes", value: (p) => num(p.rooms) },
  { label: "Dormitorios", value: (p) => num(p.bedrooms) },
  { label: "Baños", value: (p) => num(p.bathrooms) },
  { label: "Cocheras", value: (p) => num(p.garages) },
  { label: "Sup. total", value: (p) => area(p.totalArea) },
  { label: "Sup. cubierta", value: (p) => area(p.coveredArea) },
  { label: "Apto crédito", value: (p) => (p.mortgageEligible ? "Sí" : "No") },
  { label: "Disponibilidad", value: (p) => availabilityLabel(p.status) ?? "Disponible" },
  { label: "Publicada por", value: (p) => p.publisher?.name ?? unknown },
];

export function CompareClient() {
  const compare = useLocalValue(getCompare, []);
  const { properties, loading, error } = usePropertiesByIds(compare);

  return (
    <div className="container py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Comparar propiedades</h1>
          <p className="page-subtitle">Compará hasta 4 propiedades guardadas en este dispositivo.</p>
        </div>
        {compare.length ? (
          <button type="button" className="secondary-button" onClick={clearCompare}>Vaciar comparación</button>
        ) : null}
      </header>

      {compare.length === 0 ? (
        <div className="state-panel">
          <span aria-hidden="true">⇄</span>
          <h2>Elegí propiedades para comparar</h2>
          <p>Sumá entre 2 y 4 propiedades con el botón de comparar y vas a ver sus precios, superficies y características una al lado de la otra.</p>
          <Link className="primary-button" href="/propiedades">Explorar propiedades</Link>
        </div>
      ) : loading ? (
        <p className="text-sm text-slate-600">Cargando comparación…</p>
      ) : error ? (
        <p className="text-sm text-slate-600">No pudimos cargar la comparación. Reintentá en unos minutos.</p>
      ) : properties.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
          Las propiedades seleccionadas ya no están disponibles.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="compare-table">
            <caption className="sr-only">Comparación de propiedades seleccionadas</caption>
            <thead>
              <tr>
                <th scope="col" className="compare-row-label">Propiedad</th>
                {properties.map((p) => (
                  <th key={p.id} scope="col" className="compare-col-head">
                    <span className="block truncate font-bold text-[#0b2748]">{p.title}</span>
                    <span className="mt-2 flex flex-wrap gap-2">
                      <Link href={`/propiedad/${p.id}?volver=/comparar`} className="text-xs font-bold text-[#2166a5]">Ver ficha</Link>
                      <button type="button" className="text-xs font-bold text-slate-500 hover:text-slate-800" onClick={() => toggleCompare(p.id)}>
                        Quitar
                      </button>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label}>
                  <th scope="row" className="compare-row-label">{row.label}</th>
                  {properties.map((p) => (
                    <td key={p.id} className="compare-cell">{row.value(p)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
