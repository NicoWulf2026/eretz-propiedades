import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyCard } from "@/components/property/PropertyCard";
import { getPropertiesByAgency, getRealEstateById } from "@/lib/property-service";
import { idFromSlug } from "@/lib/slug";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const agency = await getRealEstateById(idFromSlug(slug));
  if (!agency) return { title: "Inmobiliaria no encontrada", robots: { index: false } };
  return {
    title: `${agency.name} — Inmobiliaria`,
    description: `Publicaciones de ${agency.name} en ERETZ Propiedades.`,
  };
}

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const id = idFromSlug(slug);
  const agency = await getRealEstateById(id);
  if (!agency) notFound();

  const properties = await getPropertiesByAgency(id);
  const returnTo = `/inmobiliaria/${agency.slug}`;

  return (
    <SiteShell>
      <div className="container py-8">
        <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-2 text-sm u-text-muted">
          <Link href="/inmobiliarias" className="font-bold text-[color:var(--accent-soft)]">← Inmobiliarias</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{agency.name}</span>
        </nav>

        <header className="professional-profile-hero">
          <div className="professional-cover" aria-hidden="true" />
          <div className="professional-profile-main">
            <span aria-hidden="true" className="professional-profile-mark">{agency.name.trim().charAt(0).toUpperCase()}</span>
            <div className="professional-profile-copy">
              <h1 className="page-title page-title-inline">
                {agency.name}
                {agency.verified ? <span className="entity-verified">✓ Verificada</span> : null}
              </h1>
              {agency.city || agency.province ? (
                <p className="page-subtitle">{[agency.city, agency.province].filter(Boolean).join(", ")}</p>
              ) : null}
              <p className="mt-2 text-sm font-semibold u-text-muted">
                {agency.listingsCount.toLocaleString("es-AR")} {agency.listingsCount === 1 ? "publicación" : "publicaciones"}
              </p>
            </div>
            <div className="professional-contact-actions">
              {agency.phone ? <a href={`tel:${agency.phone}`} className="primary-button text-center">Llamar</a> : agency.email ? <a href={`mailto:${agency.email}`} className="primary-button text-center">Enviar email</a> : null}
              {agency.website ? <a href={agency.website} target="_blank" rel="noopener noreferrer nofollow" className="secondary-button text-center">Sitio web</a> : null}
              {agency.phone && agency.email ? <a href={`mailto:${agency.email}`} className="secondary-button text-center">Email</a> : null}
            </div>
          </div>
          {!agency.verified ? (
            <div className="mt-5 rounded-xl border u-border u-surface-sunken p-4 text-sm u-text-muted">
              <p className="font-semibold u-text">¿Sos responsable de esta inmobiliaria?</p>
              <p className="mt-1">Este perfil se arma con información disponible en sus publicaciones. Podés reclamarlo para acreditar su gestión.</p>
              <Link href={`/inmobiliaria/${agency.slug}/reclamar`} className="primary-button mt-3 inline-flex">Reclamar este perfil</Link>
            </div>
          ) : null}
        </header>

        <section aria-labelledby="listings" className="mt-8">
          <h2 id="listings" className="section-heading">Publicaciones</h2>
          {properties.length === 0 ? (
            <p className="mt-4 rounded-xl border u-border u-surface-sunken p-6 text-sm u-text-muted">
              Esta inmobiliaria no tiene publicaciones disponibles en este momento.
            </p>
          ) : (
            <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {properties.map((property) => (
                <PropertyCard key={property.id} property={property} variant="grid" returnTo={returnTo} />
              ))}
            </div>
          )}
        </section>
      </div>
    </SiteShell>
  );
}
