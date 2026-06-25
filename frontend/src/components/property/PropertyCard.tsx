"use client";

import { memo } from "react";
import { getOriginalPublishedPriceLabel } from "@/lib/analysis-currency";
import type { Property, PropertyOperation, PropertyStatus, PropertyType } from "@/types/property";

const OPERATION_LABEL: Record<PropertyOperation, string> = {
  venta: "Venta",
  alquiler: "Alquiler",
  inversion: "En pozo",
  temporario: "Temporario",
  consultar: "Consultar",
  venta_y_alquiler: "Venta y alquiler",
};

const OPERATION_CLS: Record<PropertyOperation, string> = {
  venta: "bg-ink-950 text-white",
  alquiler: "bg-sky-700 text-white",
  inversion: "bg-gold-500 text-ink-950",
  temporario: "bg-emerald-700 text-white",
  consultar: "bg-ink-950/55 text-white",
  venta_y_alquiler: "bg-violet-700 text-white",
};

// Estados que requieren badge visible en la tarjeta
const STATUS_LABEL: Partial<Record<PropertyStatus, string>> = {
  reservada: "Reservada",
  vendida: "Vendida",
  alquilada: "Alquilada",
  no_detectada_en_ultimo_scraping: "Sin datos recientes",
  desconocida: "Estado desconocido",
};

const STATUS_CLS: Partial<Record<PropertyStatus, string>> = {
  reservada: "bg-amber-500 text-white",
  vendida: "bg-red-600 text-white",
  alquilada: "bg-emerald-700 text-white",
  no_detectada_en_ultimo_scraping: "bg-ink-950/65 text-white",
  desconocida: "bg-ink-950/40 text-white",
};

const TYPE_LABEL: Record<PropertyType, string> = {
  departamento: "Departamento",
  casa: "Casa",
  ph: "PH",
  terreno: "Terreno",
  oficina: "Oficina",
  local: "Local",
  otro: "Propiedad",
};

// Nombres de la plataforma (legacy "InmoCapital" + actual "ERETZ Propiedades"): nunca
// se muestran como nombre de inmobiliaria; se reemplazan por "Inmobiliaria no especificada".
const PLATFORM_FALLBACKS = new Set([
  "InmoCapital",
  "inmocapital",
  "INMOCAPITAL",
  "ERETZ Propiedades",
  "ERETZ",
  "Eretz",
  "eretz",
]);
const numFmt = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

function fmtNum(currency: Property["currency"], value: number): string | null {
  if (!Number.isFinite(value) || value <= 0) return null;
  return `${currency} ${numFmt.format(value)}`;
}

function getLocation(p: Property): string {
  const city = p.city || null;
  const prov = p.province && p.province !== city ? p.province : null;
  const parts = [p.neighborhood, city, prov].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "Argentina";
}

function getSpecs(p: Property): string[] {
  const out: string[] = [];

  if (p.rooms > 0) out.push(`${p.rooms} amb.`);
  if (p.bedrooms > 0) out.push(p.bedrooms === 1 ? "1 dorm." : `${p.bedrooms} dorm.`);
  if (p.bathrooms > 0) out.push(p.bathrooms === 1 ? "1 baño" : `${p.bathrooms} baños`);
  if (p.garages > 0) out.push(p.garages === 1 ? "1 coch." : `${p.garages} coch.`);

  if (p.totalArea > 0 && p.coveredArea > 0 && p.totalArea !== p.coveredArea) {
    out.push(`${p.totalArea} m² tot.`);
    out.push(`${p.coveredArea} m² cub.`);
  } else if (p.totalArea > 0) {
    out.push(`${p.totalArea} m²`);
  } else if (p.coveredArea > 0) {
    out.push(`${p.coveredArea} m² cub.`);
  }

  return out;
}

function toWaUrl(phone: string): string | null {
  const digits = phone.replace(/\D/g, "");
  return digits.length >= 8 ? `https://wa.me/${digits}` : null;
}

function PinIcon() {
  return (
    <svg className="size-3 shrink-0" viewBox="0 0 12 14" fill="currentColor" aria-hidden="true">
      <path d="M6 0C3.24 0 1 2.24 1 5c0 3.5 5 9 5 9s5-5.5 5-9c0-2.76-2.24-5-5-5zm0 7a2 2 0 110-4 2 2 0 010 4z" />
    </svg>
  );
}

function ExtIcon() {
  return (
    <svg
      className="size-3 shrink-0"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7 1h4v4M11 1L5.5 6.5M5 3H2a1 1 0 00-1 1v6a1 1 0 001 1h6a1 1 0 001-1V8" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg
      className="size-3 shrink-0"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.5 8.5c-.4-.4-2-.7-2.5-.3L7 9.2C5.8 8.7 4.3 7.2 3.8 6l1-1c.4-.5.1-2.1-.3-2.5L3.2.9C2.9.5 2.4.5 2 .8L1 1.7c-.7.7-.5 1.8 0 3 .9 2.1 3.3 5 5.3 6.3 1.2.7 2.5 1.1 3.4.5l.8-1c.3-.4.3-.9 0-1z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg
      className="size-3 shrink-0"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="1" y="2.5" width="10" height="7" rx="1" />
      <path d="M1 3l5 4 5-4" />
    </svg>
  );
}

const AVATAR_COLORS = [
  "bg-blue-100 text-blue-700",
  "bg-emerald-100 text-emerald-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
  "bg-violet-100 text-violet-700",
  "bg-cyan-100 text-cyan-700",
];

function agencyAvatarColor(name: string): string {
  const idx = [...name].reduce((s, c) => s + c.charCodeAt(0), 0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

function AgencyAvatar({ name }: { name: string }) {
  const initials =
    name
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? "")
      .join("") || "EP";

  return (
    <span
      className={`flex size-7 shrink-0 items-center justify-center rounded-md text-[10px] font-bold ${agencyAvatarColor(name)}`}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

function AgencyFooter({ property }: { property: Property }) {
  const rawName = property.agencyName?.trim() || "";
  const name = rawName && !PLATFORM_FALLBACKS.has(rawName) ? rawName : null;
  const displayName = name ?? "Inmobiliaria no especificada";
  const web = name !== null ? property.agencyWeb?.trim() || null : null;
  const phone = property.agencyPhone?.trim() || property.agentPhone?.trim() || null;
  const email = property.agencyEmail?.trim() || null;
  const agent = property.agentName?.trim() || null;
  const src = property.sourceUrl?.trim() || null;

  const waUrl = phone ? toWaUrl(phone) : null;
  const telUrl = phone ? `tel:${phone.replace(/\s/g, "")}` : null;
  const contactHref = waUrl ?? telUrl;
  const mailUrl = email ? `mailto:${email}` : null;
  const hasActions = Boolean(src || contactHref || mailUrl);

  return (
    <div className="mt-3 rounded-md border border-ink-950/8 bg-ink-950/[0.025] p-2.5">
      <div className="flex min-w-0 items-center gap-2">
        <AgencyAvatar name={displayName} />
        <div className="min-w-0 flex-1">
          <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-950/40">
            Publicado por
          </span>
          {web !== null ? (
            <a
              href={web}
              target="_blank"
              rel="noopener noreferrer"
              className="block truncate text-xs font-semibold text-ink-950 underline-offset-2 hover:underline"
              onClick={(event) => event.stopPropagation()}
            >
              {displayName}
            </a>
          ) : (
            <span className="block truncate text-xs font-semibold text-ink-950">
              {displayName}
            </span>
          )}
        </div>
      </div>

      {agent !== null && (
        <p className="mt-1.5 truncate text-[11px] text-ink-950/52">
          Agente: <span className="text-ink-950/68">{agent}</span>
        </p>
      )}

      {hasActions && (
        <div className="mt-2 flex flex-col gap-1.5 sm:flex-row sm:flex-wrap">
          {src !== null && (
            <a
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-ink-950 px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-ink-800 sm:justify-start"
              onClick={(event) => event.stopPropagation()}
            >
              <ExtIcon />
              Ver publicación
            </a>
          )}
          {contactHref !== null && (
            <a
              href={contactHref}
              target={waUrl !== null ? "_blank" : undefined}
              rel={waUrl !== null ? "noopener noreferrer" : undefined}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-ink-950/10 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-ink-950/72 transition hover:bg-ink-950/[0.04] sm:justify-start"
              onClick={(event) => event.stopPropagation()}
            >
              <PhoneIcon />
              Contactar
            </a>
          )}
          {mailUrl !== null && (
            <a
              href={mailUrl}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-ink-950/10 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-ink-950/72 transition hover:bg-ink-950/[0.04] sm:justify-start"
              onClick={(event) => event.stopPropagation()}
            >
              <MailIcon />
              Email
            </a>
          )}
        </div>
      )}
    </div>
  );
}

type PropertyCardProps = {
  property: Property;
  isSelected?: boolean;
  onSelect?: (id: string) => void;
};

export const PropertyCard = memo(function PropertyCard({
  property,
  isSelected = false,
  onSelect,
}: PropertyCardProps) {
  const imageUrl = property.images.find(Boolean);
  const shouldShowImage = property.hasRealImage && Boolean(imageUrl);

  const pricePerM2 =
    property.totalArea > 0 && property.price > 0
      ? Math.round(property.price / property.totalArea)
      : null;

  const expensesLabel =
    property.expenses && property.expenses > 0
      ? `Exp. ${fmtNum(property.expensesCurrency ?? property.currency, property.expenses) ?? ""}`
      : null;

  const specs = getSpecs(property);
  const location = getLocation(property);
  const rawTitle = property.title?.trim() || "";
  const title = rawTitle && rawTitle !== "Propiedad sin título" ? rawTitle : null;

  const isInactive = property.status !== "activa";
  const noMapCoords = property.latitude === null || property.longitude === null;

  return (
    <article
      id={`property-card-${property.id}`}
      className={`cursor-pointer overflow-hidden rounded-lg border bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lift ${
        isSelected ? "border-gold-500 ring-2 ring-gold-500/30" : "border-ink-950/8"
      } ${isInactive ? "opacity-60" : ""}`}
      onClick={() => onSelect?.(property.id)}
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-ink-950/8">
        {shouldShowImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt={title ?? TYPE_LABEL[property.propertyType]}
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="flex h-full w-full select-none items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgba(200,164,93,0.16),transparent_34%),linear-gradient(135deg,#061528,#102b4d)]">
            <div className="text-center">
              <p className="text-sm font-semibold tracking-[0.16em] text-white">ERETZ Propiedades</p>
              <div className="mx-auto mt-3 h-px w-16 bg-gold-400/60" />
              <p className="mt-3 text-[11px] font-medium uppercase tracking-[0.18em] text-white/46">
                {TYPE_LABEL[property.propertyType]}
              </p>
            </div>
          </div>
        )}

        {/* Badge de estado — solo visible para estados no-activos */}
        {STATUS_LABEL[property.status] && (
          <div className="absolute inset-x-0 top-0 flex items-start p-2.5">
            <span
              className={`rounded-md px-2.5 py-1 text-[11px] font-bold shadow-sm ${STATUS_CLS[property.status] ?? "bg-ink-950/50 text-white"}`}
            >
              {STATUS_LABEL[property.status]}
            </span>
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-ink-950/35 to-transparent p-2.5">
          <span
            className={`rounded-md px-2.5 py-1 text-[11px] font-bold shadow-sm ${OPERATION_CLS[property.operation]}`}
          >
            {OPERATION_LABEL[property.operation]}
          </span>
          {property.mortgageEligible && (
            <span className="rounded-md bg-gold-500 px-2.5 py-1 text-[11px] font-bold text-ink-950 shadow-sm">
              Apto crédito
            </span>
          )}
        </div>
      </div>

      <div className="p-3.5">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-950/40">
          {TYPE_LABEL[property.propertyType]}
        </p>

        <p className="mt-1 text-xl font-bold leading-tight tracking-tight text-ink-950">
          {getOriginalPublishedPriceLabel(property)}
        </p>

        {(expensesLabel !== null || pricePerM2 !== null) && (
          <div className="mt-1 flex items-center justify-between gap-2">
            <p className="truncate text-xs text-ink-950/48">{expensesLabel ?? ""}</p>
            {pricePerM2 !== null && (
              <p className="shrink-0 text-xs text-ink-950/48">
                {fmtNum(property.currency, pricePerM2)} / m²
              </p>
            )}
          </div>
        )}

        <div className="mt-2.5 flex items-center gap-1.5 text-ink-950/58">
          <PinIcon />
          <p className="truncate text-sm font-medium">{location}</p>
        </div>

        {title !== null && <p className="mt-0.5 truncate text-xs text-ink-950/48">{title}</p>}

        {(specs.length > 0 || noMapCoords) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {specs.map((s) => (
              <span
                key={s}
                className="rounded bg-ink-950/[0.04] px-2 py-0.5 text-xs font-medium text-ink-950/66"
              >
                {s}
              </span>
            ))}
            {noMapCoords && (
              <span className="rounded bg-ink-950/[0.06] px-2 py-0.5 text-xs font-medium text-ink-950/50">
                No aparece en mapa
              </span>
            )}
          </div>
        )}

        <AgencyFooter property={property} />
      </div>
    </article>
  );
});
