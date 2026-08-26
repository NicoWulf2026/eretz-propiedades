import type { Metadata } from "next";
import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";
import { getRealEstateDirectory } from "@/lib/property-service";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Inmobiliarias",
  description: "Directorio de inmobiliarias con publicaciones en ERETZ Propiedades.",
};

function one(value: string | string[] | undefined) {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const query = one(params.q).slice(0, 60);
  const { items: agencies, failed } = await getRealEstateDirectory(query);

  return (
    <SiteShell>
      <div className="container py-8">
        <header className="professional-directory-header">
          <div>
          <p className="eyebrow">Profesionales inmobiliarios</p>
          <h1 className="page-title">Inmobiliarias</h1>
          <p className="page-subtitle">
            Encontrá quién publica, dónde trabaja y cuántas propiedades ofrece.
          </p>
          </div>
          <Link href="/agentes" className="secondary-button">Ver agentes</Link>
        </header>

        <form action="/inmobiliarias" className="mb-6 flex max-w-xl gap-2" role="search">
          <label className="sr-only" htmlFor="dir-q">Buscar inmobiliaria por nombre o ubicación</label>
          <input id="dir-q" name="q" type="search" defaultValue={query} placeholder="Nombre, ciudad o provincia" maxLength={60} className="field-input flex-1 rounded-lg border u-border-strong px-3 py-2" />
          <button type="submit" className="primary-button">Buscar</button>
        </form>

        {failed ? (
          <p role="alert" className="rounded-xl border border-amber-200 u-warn-surface p-6 text-sm u-warn-text">
            No pudimos cargar el listado de inmobiliarias en este momento. Volvé a intentar en unos minutos.
          </p>
        ) : agencies.length === 0 ? (
          <p className="rounded-xl border u-border u-surface-sunken p-6 text-sm u-text-muted">
            {query ? `No encontramos inmobiliarias que coincidan con “${query}”.` : "No hay inmobiliarias para mostrar por ahora."}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agencies.map((agency) => (
              <li key={agency.id}>
                <Link href={`/inmobiliaria/${agency.slug}`} className="focus-ring entity-card">
                  <span aria-hidden="true" className="entity-monogram">{agency.name.trim().charAt(0).toUpperCase()}</span>
                  <span className="entity-body">
                    <span className="entity-name">
                      {agency.name}
                      {agency.verified ? <span className="entity-verified" title="Identidad verificada por ERETZ">✓ Verificada</span> : null}
                    </span>
                    {agency.city || agency.province ? (
                      <span className="entity-meta">{[agency.city, agency.province].filter(Boolean).join(", ")}</span>
                    ) : <span className="entity-meta entity-meta-empty">Ubicación no informada</span>}
                    <span className="entity-count">
                      {agency.listingsCount.toLocaleString("es-AR")} {agency.listingsCount === 1 ? "publicación" : "publicaciones"}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </SiteShell>
  );
}
