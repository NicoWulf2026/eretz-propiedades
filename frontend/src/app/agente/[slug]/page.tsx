import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyCard } from "@/components/property/PropertyCard";
import { getAgentBySlug, getPropertiesByAgent } from "@/lib/property-service";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const agent = await getAgentBySlug(slug);
  if (!agent) return { title: "Agente no encontrado", robots: { index: false } };
  return { title: `${agent.name} — Agente`, description: `Publicaciones de ${agent.name} en ERETZ Propiedades.` };
}

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgentBySlug(slug);
  if (!agent) notFound();

  const properties = await getPropertiesByAgent(agent.name);
  const returnTo = `/agente/${agent.slug}`;

  return (
    <SiteShell>
      <div className="container py-8">
        <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Link href="/agentes" className="font-bold text-[color:var(--accent-soft)]">← Agentes</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{agent.name}</span>
        </nav>

        <header className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
          <h1 className="page-title">{agent.name}</h1>
          {agent.city || agent.province ? (
            <p className="page-subtitle">{[agent.city, agent.province].filter(Boolean).join(", ")}</p>
          ) : null}
          <p className="mt-2 text-sm font-semibold text-slate-700">
            {agent.listingsCount.toLocaleString("es-AR")} {agent.listingsCount === 1 ? "publicación" : "publicaciones"}
          </p>
          {agent.phone ? <a href={`tel:${agent.phone}`} className="secondary-button mt-4 inline-flex">Teléfono</a> : null}
        </header>

        <section aria-labelledby="listings" className="mt-8">
          <h2 id="listings" className="section-heading">Publicaciones</h2>
          {properties.length === 0 ? (
            <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
              Este agente no tiene publicaciones disponibles en este momento.
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
