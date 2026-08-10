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
  const agents = await getAgentDirectory(query);

  return (
    <SiteShell>
      <div className="container py-8">
        <header className="mb-6">
          <h1 className="text-3xl font-black tracking-[-0.03em] text-[#0b2748]">Agentes</h1>
          <p className="mt-2 text-sm text-slate-600">
            Agentes que figuran en las publicaciones del catálogo. Sólo se muestran los que tienen datos reales.
          </p>
        </header>

        <form action="/agentes" className="mb-6 flex max-w-xl gap-2" role="search">
          <label className="sr-only" htmlFor="ag-q">Buscar agente por nombre</label>
          <input id="ag-q" name="q" type="search" defaultValue={query} placeholder="Buscar por nombre" maxLength={60} className="flex-1 rounded-lg border border-slate-300 px-3 py-2" />
          <button type="submit" className="primary-button">Buscar</button>
        </form>

        {agents.length === 0 ? (
          <p className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            {query ? `No encontramos agentes que coincidan con “${query}”.` : "No hay agentes con datos suficientes para mostrar por ahora."}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <li key={agent.slug}>
                <Link href={`/agente/${agent.slug}`} className="focus-ring block h-full rounded-xl border border-slate-200 bg-white p-4 hover:border-[#2166a5] hover:shadow-md">
                  <p className="truncate text-base font-bold text-[#0b2748]">{agent.name}</p>
                  {agent.city || agent.province ? (
                    <p className="mt-1 truncate text-sm text-slate-600">{[agent.city, agent.province].filter(Boolean).join(", ")}</p>
                  ) : null}
                  <p className="mt-3 text-sm font-semibold text-slate-700">
                    {agent.listingsCount.toLocaleString("es-AR")} {agent.listingsCount === 1 ? "publicación" : "publicaciones"}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </SiteShell>
  );
}
