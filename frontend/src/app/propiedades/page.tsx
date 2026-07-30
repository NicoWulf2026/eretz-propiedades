import type { Metadata } from "next";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyMap } from "@/components/map/PropertyMap";
import { PropertyCard } from "@/components/property/PropertyCard";
import { FilterForm } from "@/components/search/FilterForm";
import { Pagination } from "@/components/search/Pagination";
import { parsePropertyFilters, type SearchParams } from "@/lib/property-query";
import { searchProperties } from "@/lib/property-service";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Buscar propiedades en Argentina",
  description: "Buscá propiedades en venta y alquiler con filtros y contacto directo.",
  robots: { index: false, follow: true },
};

export default async function PropertiesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parsePropertyFilters(await searchParams);
  const result = await searchProperties(filters);
  return (
    <SiteShell>
      <section className="border-b border-slate-200 bg-[#eef5fb]">
        <div className="container py-10">
          <p className="eyebrow">Inventario público</p>
          <h1 className="section-title">Propiedades en Argentina</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">Buscá por palabras del título y filtrá ubicación, operación y características sobre el inventario público. Cada URL puede compartirse.</p>
          <div className="mt-7"><FilterForm filters={filters} /></div>
        </div>
      </section>
      <section className="container py-10">
        {result.error ? (
          <div className="empty-panel" role="alert"><h2 className="text-xl font-black text-[#0b2748]">No pudimos cargar los resultados</h2><p className="mt-2 text-sm">La consulta tardó demasiado o el servicio no está disponible. Probá nuevamente.</p><a className="primary-button mt-5" href={`/propiedades`}>Reintentar</a></div>
        ) : result.properties.length === 0 ? (
          <div className="empty-panel"><h2 className="text-xl font-black text-[#0b2748]">No encontramos propiedades</h2><p className="mt-2 text-sm">Probá ampliar la ubicación, el rango de precio o restablecer los filtros.</p><a className="primary-button mt-5" href="/propiedades">Restablecer filtros</a></div>
        ) : (
          <>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-600">{result.count !== null ? <><strong className="text-[#0b2748]">{result.count.toLocaleString("es-AR")}</strong> resultados</> : <>Página <strong className="text-[#0b2748]">{result.page.toLocaleString("es-AR")}</strong></>}</p>
              <p className="text-xs text-slate-500">24 avisos por página</p>
            </div>
            <PropertyMap properties={result.properties} />
            <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {result.properties.map((property, index) => <PropertyCard key={property.id} property={property} priority={index < 4} />)}
            </div>
            <Pagination filters={filters} hasNext={result.hasNext} hasPrevious={result.hasPrevious} nextCursor={result.nextCursor} previousCursor={result.previousCursor} />
          </>
        )}
      </section>
    </SiteShell>
  );
}
