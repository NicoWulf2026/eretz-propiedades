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
  const agencies = await getRealEstateDirectory(query);

  return (
    <SiteShell>
      <div className="container py-8">
        <header className="mb-6">
          <h1 className="text-3xl font-black tracking-[-0.03em] text-[#0b2748]">Inmobiliarias</h1>
          <p className="mt-2 text-sm text-slate-600">
            Todas las inmobiliarias con publicaciones en el catálogo. ERETZ es un agregador
            independiente: los datos provienen de las publicaciones originales.
          </p>
        </header>

        <form action="/inmobiliarias" className="mb-6 flex max-w-xl gap-2" role="search">
          <label className="sr-only" htmlFor="dir-q">Buscar inmobiliaria por nombre</label>
          <input id="dir-q" name="q" type="search" defaultValue={query} placeholder="Buscar por nombre" maxLength={60} className="field-input flex-1 rounded-lg border border-slate-300 px-3 py-2" />
          <button type="submit" className="primary-button">Buscar</button>
        </form>

        {agencies.length === 0 ? (
          <p className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            {query ? `No encontramos inmobiliarias que coincidan con “${query}”.` : "No hay inmobiliarias para mostrar por ahora."}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agencies.map((agency) => (
              <li key={agency.id}>
                <Link href={`/inmobiliaria/${agency.slug}`} className="focus-ring block h-full rounded-xl border border-slate-200 bg-white p-4 hover:border-[#2166a5] hover:shadow-md">
                  <p className="flex items-center gap-2 text-base font-bold text-[#0b2748]">
                    <span className="truncate">{agency.name}</span>
                    {agency.verified ? <span className="rounded-full bg-[#e8f0f7] px-2 py-0.5 text-[11px] font-bold text-[#2166a5]">Verificada</span> : null}
                  </p>
                  {agency.city || agency.province ? (
                    <p className="mt-1 truncate text-sm text-slate-600">{[agency.city, agency.province].filter(Boolean).join(", ")}</p>
                  ) : null}
                  <p className="mt-3 text-sm font-semibold text-slate-700">
                    {agency.listingsCount.toLocaleString("es-AR")} {agency.listingsCount === 1 ? "publicación" : "publicaciones"}
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
