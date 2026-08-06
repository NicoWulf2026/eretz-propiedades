"use client";

import Link from "next/link";
import { PropertyImage } from "@/components/property/PropertyImage";
import {
  availabilityLabel,
  formatDate,
  operationLabels,
  propertyLocation,
  propertyPrice,
  propertySpecs,
  typeLabels,
} from "@/lib/property-presenter";
import type { PropertySummary } from "@/types/property";

export type PropertyCardVariant = "compact" | "full";

async function shareProperty(id: string, title: string) {
  if (typeof window === "undefined") return;
  const url = `${window.location.origin}/propiedad/${id}`;
  try {
    if (navigator.share) { await navigator.share({ title, url }); return; }
    await navigator.clipboard?.writeText(url);
  } catch { /* el usuario canceló o no hay permiso de compartir */ }
}

export function PropertyCard({
  property,
  variant = "compact",
  priority = false,
  returnTo = "/",
  selected = false,
  onSelect,
}: {
  property: PropertySummary;
  variant?: PropertyCardVariant;
  priority?: boolean;
  returnTo?: string;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const specs = propertySpecs(property);
  const date = formatDate(property.publishedAt ?? property.updatedAt);
  const full = variant === "full";
  const detailHref = `/propiedad/${property.id}?volver=${encodeURIComponent(returnTo)}`;
  const amenities = full ? (property.amenities ?? []).filter(Boolean).slice(0, 4) : [];
  const availability = availabilityLabel(property.status);
  return (
    <article className={`property-card ${full ? "is-full" : "is-compact"} ${selected ? "is-selected" : ""}`} data-property-id={property.id} onMouseEnter={() => onSelect?.(property.id)} onFocus={() => onSelect?.(property.id)}>
      <Link
        href={detailHref}
        className="focus-ring block"
        onClick={() => {
          try { sessionStorage.setItem(`eretz:return:${returnTo}`, JSON.stringify({ scrollY: window.scrollY, selectedId: property.id })); } catch { /* opcional */ }
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
          {availability ? (
            <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600" title="La disponibilidad de esta publicación no está confirmada en el último relevamiento.">
              <span aria-hidden="true">•</span>{availability}
            </p>
          ) : null}
          {property.publisher ? <p className="mt-2 truncate text-xs font-semibold text-slate-500">{property.publisher.name}{property.publisher.verified ? " · Verificada" : ""}</p> : null}
          <div className="mt-4 flex min-h-6 flex-wrap gap-x-3 gap-y-1 border-t border-slate-100 pt-3 text-xs font-semibold text-slate-600">
            {specs.length ? (full ? specs : specs.slice(0, 4)).map((spec) => <span key={spec}>{spec}</span>) : <span>Características no informadas</span>}
          </div>
          {full && property.description ? <p className="mt-3 line-clamp-2 text-sm text-slate-600">{property.description}</p> : null}
          {full && amenities.length ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {amenities.map((amenity) => <li key={amenity} className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{amenity}</li>)}
            </ul>
          ) : null}
          {date ? <time className="mt-3 block text-[11px] text-slate-500" dateTime={property.publishedAt ?? property.updatedAt ?? undefined}>Publicado/actualizado {date}</time> : null}
        </div>
      </Link>
      {full ? (
        <div className="card-actions">
          <Link href={detailHref} className="secondary-button">Ver propiedad</Link>
          <button type="button" className="secondary-button" onClick={() => shareProperty(property.id, property.title)}>Compartir</button>
          <Link href={`${detailHref}#contacto`} className="primary-button">Contactar</Link>
        </div>
      ) : null}
    </article>
  );
}
