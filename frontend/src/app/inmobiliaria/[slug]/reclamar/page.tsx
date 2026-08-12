import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { ClaimForm } from "@/components/local/ClaimForm";
import { getRealEstateById } from "@/lib/property-service";
import { idFromSlug } from "@/lib/slug";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Reclamar perfil",
  robots: { index: false, follow: false },
};

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agency = await getRealEstateById(idFromSlug(slug));
  if (!agency) notFound();

  return (
    <SiteShell>
      <div className="container py-8">
        <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Link href={`/inmobiliaria/${agency.slug}`} className="font-bold text-[color:var(--accent-soft)]">← {agency.name}</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Reclamar perfil</span>
        </nav>
        <header className="mt-6 mb-6">
          <h1 className="text-3xl font-black tracking-[-0.03em] text-[color:var(--ink)]">Reclamar {agency.name}</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Completá tus datos para reclamar la gestión de este perfil. La solicitud queda pendiente de
            verificación humana; no se aprueba automáticamente ni se modifica el perfil hasta confirmar.
          </p>
        </header>
        <ClaimForm tipo="inmobiliaria" entidadId={agency.id} entidadNombre={agency.name} />
      </div>
    </SiteShell>
  );
}
