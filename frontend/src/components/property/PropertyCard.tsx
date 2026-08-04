"use client";

import Link from "next/link";
import { PropertyImage } from "@/components/property/PropertyImage";
import {
  operationLabels,
  propertyLocation,
  propertyPrice,
  propertySpecs,
  typeLabels,
} from "@/lib/property-presenter";
import type { PropertySummary } from "@/types/property";
import { formatDate } from "@/lib/property-presenter";

export function PropertyCard({ property, priority = false, returnTo = "/", selected = false, onSelect }: { property: PropertySummary; priority?: boolean; returnTo?: string; selected?: boolean; onSelect?: (id: string) => void }) {
  const specs = propertySpecs(property);
  const date = formatDate(property.publishedAt ?? property.updatedAt);
  return (
    <article className={`property-card ${selected ? "is-selected" : ""}`} data-property-id={property.id} onMouseEnter={() => onSelect?.(property.id)} onFocus={() => onSelect?.(property.id)}>
      <Link
        href={`/propiedad/${property.id}?volver=${encodeURIComponent(returnTo)}`}
        className="focus-ring block"
        onClick={() => {
          try { sessionStorage.setItem(`eretz:return:${returnTo}`, JSON.stringify({ scrollY: window.scrollY, selectedId: property.id })); } catch { /* optional */ }
        }}
      >
        <div className="relative aspect-[4/3] overflow-hidden bg-slate-100">
          <PropertyImage src={property.images[0] ?? null} alt={property.title} priority={priority} />
          <span className="absolute left-3 top-3 rounded-full bg-[#0b2748] px-3 py-1.5 text-xs font-bold text-white shadow">
            {operationLabels[property.operation]}
          </span>
          {property.mortgageEligible && (
            <span className="absolute bottom-3 right-3 rounded-full bg-[#f4e8cc] px-3 py-1.5 text-xs font-bold text-[#0b2748]">Apto crédito</span>
          )}
        </div>
        <div className="p-4">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#2166a5]">{typeLabels[property.propertyType]}</p>
          <p className="mt-2 text-xl font-black tracking-tight text-[#0b2748]">{propertyPrice(property)}</p>
          <h2 className="mt-2 line-clamp-2 min-h-12 text-base font-bold leading-6 text-slate-800">{property.title}</h2>
          <p className="mt-2 truncate text-sm text-slate-600">{propertyLocation(property)}</p>
          {property.publisher ? <p className="mt-2 truncate text-xs font-semibold text-slate-500">{property.publisher.name}{property.publisher.verified ? " · Verificada" : ""}</p> : null}
          <div className="mt-4 flex min-h-6 flex-wrap gap-x-3 gap-y-1 border-t border-slate-100 pt-3 text-xs font-semibold text-slate-600">
            {specs.length ? specs.slice(0, 4).map((spec) => <span key={spec}>{spec}</span>) : <span>Características no informadas</span>}
          </div>
          {date ? <time className="mt-3 block text-[11px] text-slate-500" dateTime={property.publishedAt ?? property.updatedAt ?? undefined}>Publicado/actualizado {date}</time> : null}
        </div>
      </Link>
    </article>
  );
}
