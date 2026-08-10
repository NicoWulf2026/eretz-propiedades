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
        <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Link href="/inmobiliarias" className="font-bold text-[#2166a5]">← Inmobiliarias</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{agency.name}</span>
        </nav>

        <header className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="flex items-center gap-3 text-3xl font-black tracking-[-0.03em] text-[#0b2748]">
                {agency.name}
                {agency.verified ? <span className="rounded-full bg-[#e8f0f7] px-2.5 py-1 text-xs font-bold text-[#2166a5]">Verificada</span> : null}
              </h1>
              {agency.city || agency.province ? (
                <p className="mt-2 text-sm text-slate-600">{[agency.city, agency.province].filter(Boolean).join(", ")}</p>
              ) : null}
              <p className="mt-2 text-sm font-semibold text-slate-700">
                {agency.listingsCount.toLocaleString("es-AR")} {agency.listingsCount === 1 ? "publicación" : "publicaciones"}
              </p>
            </div>
            <div className="flex flex-col gap-2 text-sm">
              {agency.website ? <a href={agency.website} target="_blank" rel="noopener noreferrer nofollow" className="secondary-button text-center">Sitio web</a> : null}
              {agency.phone ? <a href={`tel:${agency.phone}`} className="secondary-button text-center">Teléfono</a> : null}
              {agency.email ? <a href={`mailto:${agency.email}`} className="secondary-button text-center">Email</a> : null}
            </div>
          </div>
          {!agency.verified ? (
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              <p className="font-semibold text-slate-800">¿Sos responsable de esta inmobiliaria?</p>
              <p className="mt-1">Este perfil es público y se genera con datos de las publicaciones. Podés reclamarlo para gestionarlo.</p>
              <Link href={`/inmobiliaria/${agency.slug}/reclamar`} className="primary-button mt-3 inline-flex">Reclamar este perfil</Link>
            </div>
          ) : null}
        </header>

        <section aria-labelledby="listings" className="mt-8">
          <h2 id="listings" className="text-xl font-black text-[#0b2748]">Publicaciones</h2>
          {properties.length === 0 ? (
            <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
              Esta inmobiliaria no tiene publicaciones disponibles en este momento.
            </p>
          ) : (
            <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {properties.map((property) => (
                <PropertyCard key={property.id} property={property} variant="full" returnTo={returnTo} />
              ))}
            </div>
          )}
        </section>
      </div>
    </SiteShell>
  );
}
