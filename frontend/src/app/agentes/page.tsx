import type { Metadata } from "next";
import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";
import { getAgentDirectory } from "@/lib/property-service";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Agentes",
  description: "Agentes con publicaciones en ERETZ Propiedades.",
};

function one(value: string | string[] | undefined) {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const query = one(params.q).slice(0, 60);
  const { items: agents, failed } = await getAgentDirectory(query);

  return (
    <SiteShell>
      <div className="container py-8">
        <header className="mb-6">
          <h1 className="page-title">Agentes</h1>
          <p className="page-subtitle">
            Agentes que figuran en las publicaciones del catálogo. Sólo se muestran los que tienen datos reales.
          </p>
        </header>

        <form action="/agentes" className="mb-6 flex max-w-xl gap-2" role="search">
          <label className="sr-only" htmlFor="ag-q">Buscar agente por nombre</label>
          <input id="ag-q" name="q" type="search" defaultValue={query} placeholder="Buscar por nombre" maxLength={60} className="flex-1 rounded-lg border border-slate-300 px-3 py-2" />
          <button type="submit" className="primary-button">Buscar</button>
        </form>

        {failed ? (
          <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
            No pudimos cargar el listado de agentes en este momento. Volvé a intentar en unos minutos.
          </p>
        ) : agents.length === 0 ? (
          <p className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            {query ? `No encontramos agentes que coincidan con “${query}”.` : "No hay agentes con datos suficientes para mostrar por ahora."}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <li key={agent.slug}>
                <Link href={`/agente/${agent.slug}`} className="focus-ring entity-card">
                  <span aria-hidden="true" className="entity-monogram">{agent.name.trim().charAt(0).toUpperCase()}</span>
                  <span className="entity-body">
                    <span className="entity-name">{agent.name}</span>
                    {agent.city || agent.province ? (
                      <span className="entity-meta">{[agent.city, agent.province].filter(Boolean).join(", ")}</span>
                    ) : <span className="entity-meta entity-meta-empty">Ubicación no informada</span>}
                    <span className="entity-count">
                      {agent.listingsCount.toLocaleString("es-AR")} {agent.listingsCount === 1 ? "publicación" : "publicaciones"}
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
