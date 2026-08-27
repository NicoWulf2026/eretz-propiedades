"use client";

import Link from "next/link";
import { memo } from "react";
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
  propertyPrice,
  propertySpecs,
  typeLabels,
} from "@/lib/property-presenter";
import type { PropertySummary } from "@/types/property";

export type PropertyCardVariant = "compact" | "grid";

export const PropertyCard = memo(function PropertyCard({
  property,
  variant = "grid",
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
  // La etiqueta sigue al campo, no al revés. Hoy `fecha_publicacion` tiene 0%
  // de cobertura, así que esto siempre cae en `updatedAt` y dice "Actualizada",
  // que es cierto. El día que se pueble, mostrar una fecha de publicación
  // rotulada "Actualizada" sería decir algo falso sin que nadie tocara nada.
  const dateSource = property.publishedAt ?? property.updatedAt;
  const dateLabel = property.publishedAt ? "Publicada" : "Actualizada";
  const date = formatDate(dateSource);
  const grid = variant === "grid";
  const detailHref = `/propiedad/${property.id}?volver=${encodeURIComponent(returnTo)}`;
  const availability = availabilityLabel(property.status);
  const location = propertyLocation(property);
  const type = typeLabels[property.propertyType];
  const operation = operationLabels[property.operation];
  const visibleSpecs = specs.slice(0, grid ? 4 : 3);
  const accessibleName = `Ver ${type.toLowerCase()} en ${location}, ${propertyPrice(property)}`;
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
      className={`property-card is-${variant} ${selected ? "is-selected" : ""}`}
      data-property-id={property.id}
      data-card-variant={variant}
      onPointerEnter={() => onPreview?.(property.id)}
      onPointerLeave={() => onPreview?.(null)}
      onFocusCapture={() => onPreview?.(property.id)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) onPreview?.(null);
      }}
    >
      <PropertyCardActions
        id={property.id}
        title={property.title}
        reportHref={`${detailHref}#aviso`}
        onHide={() => hideProperty(property.id)}
      />
      <Link
        href={detailHref}
        prefetch={false}
        className="focus-ring block"
        aria-label={accessibleName}
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
        <div className="property-card-media relative">
          <PropertyImage
            src={property.images[0] ?? null}
            alt={`Foto de ${type.toLowerCase()} en ${location}`}
            fallbackLabel={type}
            priority={priority}
          />
          <span className="pill card-operation absolute left-3 top-3">{operation}</span>
          {visited && <span className="card-visited-badge absolute bottom-3 left-3">Vista</span>}
          {property.mortgageEligible && (
            <span className="pill pill-pick absolute bottom-3 right-3">Apto crédito</span>
          )}
        </div>
        <div className="property-card-body">
          <div className="card-primary-row">
            <PriceTag property={property} className="card-price" consultLabel="Consultar" />
            <span className="card-type">{type}</span>
          </div>
          <div className="card-location-row">
            <p className="card-location" title={location}>{location}</p>
            {property.locationConfidence !== "high" ? (
              <span
                className={`card-location-confidence is-${property.locationConfidence}`}
                aria-label={locationConfidenceLabel(property.locationConfidence)}
                title={locationConfidenceLabel(property.locationConfidence)}
              >
                <span className="confidence-mark" aria-hidden="true" />
                <span className="confidence-copy">{locationConfidenceLabel(property.locationConfidence)}</span>
              </span>
            ) : null}
          </div>
          {visibleSpecs.length ? <div className="card-specs">{visibleSpecs.map((spec) => <span key={spec}>{spec}</span>)}</div> : null}
          {property.publisher ? <p className="card-publisher">{property.publisher.name}{property.publisher.verified ? " · Verificada" : ""}</p> : null}
          {availability ? <p className="card-availability" title="La disponibilidad de esta publicación no está confirmada en el último relevamiento.">{availability}</p> : null}
          {grid && date ? <time className="card-date" dateTime={dateSource ?? undefined}>{dateLabel} {date}</time> : null}
        </div>
      </Link>
    </article>
  );
});
