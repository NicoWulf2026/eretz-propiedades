"use client";

import Link from "next/link";
import { PropertyImage } from "@/components/property/PropertyImage";
import { track } from "@/lib/analytics";
import {
  operationLabels,
  propertyLocation,
  propertyPrice,
  propertySpecs,
  typeLabels,
} from "@/lib/property-presenter";
import type { Property } from "@/types/property";

export function PropertyCard({ property, priority = false }: { property: Property; priority?: boolean }) {
  const specs = propertySpecs(property);
  return (
    <article className="property-card">
      <Link
        href={`/propiedad/${property.id}`}
        className="focus-ring block"
        onClick={() => track("property_opened", { property_id: property.id })}
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
          <div className="mt-4 flex min-h-6 flex-wrap gap-x-3 gap-y-1 border-t border-slate-100 pt-3 text-xs font-semibold text-slate-600">
            {specs.length ? specs.slice(0, 4).map((spec) => <span key={spec}>{spec}</span>) : <span>Características no informadas</span>}
          </div>
        </div>
      </Link>
    </article>
  );
}

