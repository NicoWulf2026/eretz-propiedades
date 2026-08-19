"use client";

import Link from "next/link";
import { PriceTag } from "@/components/property/PriceTag";
import { PropertyImage } from "@/components/property/PropertyImage";
import { PropertyCardActions } from "@/components/property/PropertyCardActions";
import { hideProperty, isHidden, isVisited, unhideProperty } from "@/lib/local-store";
import { useLocalValue } from "@/lib/use-local-store";
import { locationConfidenceLabel } from "@/lib/geo-confidence";
import {
  availabilityLabel,
  formatDate,
  operationLabels,
  propertyLocation,
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
  onPreview,
  onCommit,
}: {
  property: PropertySummary;
  variant?: PropertyCardVariant;
  priority?: boolean;
  returnTo?: string;
  selected?: boolean;
  onPreview?: (id: string | null) => void;
  onCommit?: (id: string) => void;
}) {
  const specs = propertySpecs(property);
  const date = formatDate(property.publishedAt ?? property.updatedAt);
  const full = variant === "full";
  const detailHref = `/propiedad/${property.id}?volver=${encodeURIComponent(returnTo)}`;
  const amenities = full ? (property.amenities ?? []).filter(Boolean).slice(0, 4) : [];
  const availability = availabilityLabel(property.status);
  const hidden = useLocalValue(() => isHidden(property.id), false);
  const visited = useLocalValue(() => isVisited(property.id), false);
  if (hidden) {
    return (
      <article className="property-card is-hidden" data-property-id={property.id}>
        <div className="property-card-hidden-body">
          <p className="text-sm font-semibold u-text-muted">Ocultaste esta propiedad.</p>
          <p className="mt-1 truncate text-xs u-text-muted">{property.title}</p>
          <button type="button" className="secondary-button mt-3" onClick={() => unhideProperty(property.id)}>
            Mostrar de nuevo
          </button>
        </div>
      </article>
    );
  }
  return (
    <article
      className={`property-card ${full ? "is-full" : "is-compact"} ${selected ? "is-selected" : ""}`}
      data-property-id={property.id}
      onPointerEnter={() => onPreview?.(property.id)}
      onPointerLeave={() => onPreview?.(null)}
      onFocusCapture={() => onPreview?.(property.id)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) onPreview?.(null);
      }}
    >
      <PropertyCardActions id={property.id} onHide={() => hideProperty(property.id)} />
      <Link
        href={detailHref}
        className="focus-ring block"
        onClick={() => {
          onCommit?.(property.id);
          try {
            const resultsPane = document.querySelector<HTMLElement>(".explorer-results-pane");
            const usesResultsScroll = !!resultsPane
              && resultsPane.scrollHeight > resultsPane.clientHeight
              && window.getComputedStyle(resultsPane).overflowY !== "visible";
            const state = JSON.stringify({
              scrollY: usesResultsScroll ? resultsPane.scrollTop : window.scrollY,
              scrollTarget: usesResultsScroll ? "results" : "window",
              selectedId: property.id,
            });
            const visibleReturnTo = `${window.location.pathname}${window.location.search}`;
            sessionStorage.setItem(`eretz:return:${returnTo}`, state);
            if (visibleReturnTo !== returnTo) sessionStorage.setItem(`eretz:return:${visibleReturnTo}`, state);
          } catch { /* opcional */ }
        }}
      >
        <div className="property-card-media relative aspect-[4/3]">
          <PropertyImage src={property.images[0] ?? null} alt={property.title} priority={priority} />
          <span className="pill absolute left-3 top-3">{operationLabels[property.operation]}</span>
          {visited && <span className="card-visited-badge absolute bottom-3 left-3">Vista</span>}
          {property.mortgageEligible && (
            <span className="pill pill-pick absolute bottom-3 right-3">Apto crédito</span>
          )}
        </div>
        <div className="property-card-body">
          {/* Orden de la referencia: primero la direccion, despues el precio. */}
          <h2 className="card-title">{property.title}</h2>
          <PriceTag property={property} className="card-price" />
          <p className="card-location">{propertyLocation(property)}</p>
          {property.locationConfidence !== "high" ? (
            <p className={`card-location-confidence is-${property.locationConfidence}`}>
              {locationConfidenceLabel(property.locationConfidence)}
            </p>
          ) : null}
          <p className="card-type">{typeLabels[property.propertyType]}</p>
          {availability ? (
            <p className="card-availability" title="La disponibilidad de esta publicación no está confirmada en el último relevamiento.">
              {availability}
            </p>
          ) : null}
          <div className="card-specs">
            {specs.length ? (full ? specs : specs.slice(0, 4)).map((spec) => <span key={spec}>{spec}</span>) : <span>Características no informadas</span>}
          </div>
          {property.publisher ? <p className="card-publisher">{property.publisher.name}{property.publisher.verified ? " · Verificada" : ""}</p> : null}
          {full && property.description ? <p className="mt-3 line-clamp-2 text-sm u-text-muted">{property.description}</p> : null}
          {full && amenities.length ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {amenities.map((amenity) => <li key={amenity} className="rounded-full u-surface-sunken px-2.5 py-1 text-[11px] font-semibold u-text-muted">{amenity}</li>)}
            </ul>
          ) : null}
          {date ? <time className="mt-3 block text-[11px] u-text-faint" dateTime={property.publishedAt ?? property.updatedAt ?? undefined}>Publicado/actualizado {date}</time> : null}
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
