import Link from "next/link";
import Image from "next/image";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PublicSearchForm } from "@/components/search/PublicSearchForm";
import { getHomeInventory } from "@/lib/property-service";

export const dynamic = "force-dynamic";

export default async function Home() {
  const inventory = await getHomeInventory();
  return (
    <SiteShell>
      <section className="hero">
        <Image
          src="/og.png"
          alt=""
          fill
          priority
          quality={78}
          sizes="100vw"
          className="hero-image object-cover"
        />
        <div className="hero-overlay" aria-hidden="true" />
        <div className="container relative py-16 sm:py-20 lg:py-28">
          <div className="max-w-3xl">
            <p className="eyebrow text-[#f0dba9]">Propiedades en toda Argentina</p>
            <h1 className="mt-4 text-4xl font-black leading-[1.05] tracking-[-0.04em] text-white sm:text-6xl">
              Encontrá un lugar que se sienta tuyo.
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-white/75">
              Explorá avisos de inmobiliarias y desarrolladoras, filtrá lo importante y contactá directamente a quien publica.
            </p>
          </div>
          <div className="mt-9 rounded-2xl bg-white p-4 shadow-2xl sm:p-5">
            <PublicSearchForm />
          </div>
          <div className="mt-5 flex flex-wrap gap-4 text-sm text-white/70">
            {inventory.count > 0 && <span><strong className="text-white">{inventory.count.toLocaleString("es-AR")}</strong> avisos activos disponibles</span>}
            <span>Sin registro</span><span>Contacto directo</span>
          </div>
        </div>
      </section>

      <section className="container py-16">
        <div className="flex items-end justify-between gap-4">
          <div><p className="eyebrow">Inventario activo</p><h2 className="section-title">Propiedades destacadas</h2></div>
          <Link href="/propiedades" className="text-sm font-bold text-[#2166a5]">Ver todas →</Link>
        </div>
        {inventory.error ? (
          <div className="empty-panel mt-8"><p className="font-bold">No pudimos cargar las propiedades.</p><Link href="/" className="mt-3 inline-block font-bold text-[#2166a5]">Reintentar</Link></div>
        ) : (
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {inventory.recent.map((property, index) => <PropertyCard key={property.id} property={property} priority={index < 2} />)}
          </div>
        )}
      </section>

      <section className="bg-[#eef5fb] py-16">
        <div className="container grid gap-5 md:grid-cols-3">
          {[
            ["Comprar", "Buscá por tipo, ubicación, moneda y precio sin mezclar criterios.", "/propiedades?operacion=venta"],
            ["Alquilar", "Encontrá alquileres permanentes o temporarios en un solo lugar.", "/propiedades?operacion=alquiler"],
            ["Invertir", "Compará superficie, ubicación y publicación original antes de decidir.", "/propiedades?orden=area_desc"],
          ].map(([title, copy, href]) => (
            <Link key={title} href={href} className="rounded-2xl border border-[#2166a5]/10 bg-white p-6 transition hover:-translate-y-1 hover:shadow-lg">
              <h2 className="text-2xl font-black text-[#0b2748]">{title}</h2><p className="mt-3 text-sm leading-6 text-slate-600">{copy}</p><span className="mt-5 inline-block text-sm font-bold text-[#2166a5]">Explorar →</span>
            </Link>
          ))}
        </div>
      </section>

      <section id="como-funciona" className="container py-16">
        <p className="eyebrow">Simple y transparente</p><h2 className="section-title">Cómo funciona ERETZ</h2>
        <ol className="mt-8 grid gap-6 md:grid-cols-3">
          {[
            ["1", "Buscá", "Usá filtros reales sobre el inventario público; no descargamos toda la base."],
            ["2", "Revisá", "Compará la información disponible y abrí la fuente original cuando lo necesites."],
            ["3", "Contactá", "Hablá directamente con la inmobiliaria, desarrolladora o responsable del aviso."],
          ].map(([number, title, copy]) => <li key={number} className="rounded-2xl border border-slate-200 bg-white p-6"><span className="grid size-10 place-items-center rounded-full bg-[#0b2748] font-black text-white">{number}</span><h3 className="mt-5 text-xl font-black text-[#0b2748]">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{copy}</p></li>)}
        </ol>
      </section>
    </SiteShell>
  );
}
