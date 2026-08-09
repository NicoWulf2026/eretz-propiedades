import type { Metadata } from "next";
import { siteUrl } from "@/lib/site-url";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyMap } from "@/components/map/PropertyMap";
import { ContactActions } from "@/components/property/ContactActions";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PropertyGallery } from "@/components/property/PropertyGallery";
import { RecentViewTracker } from "@/components/property/RecentViewTracker";
import { availabilityLabel, formatDate, operationLabels, propertyLocation, propertyPrice, propertySpecs, typeLabels } from "@/lib/property-presenter";
import { getPropertyById, getRelatedProperties } from "@/lib/property-service";
import { parsePropertyFilters, type SearchParams } from "@/lib/property-query";


export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const property = await getPropertyById(id);
  if (!property) notFound();
  const description = `${typeLabels[property.propertyType]} en ${operationLabels[property.operation]}. ${propertyLocation(property)}. ${propertyPrice(property)}.`;
  const canonical = `${siteUrl}/propiedad/${property.id}`;
  return {
    title: property.title,
    description,
    alternates: { canonical },
    openGraph: { title: property.title, description, url: canonical, type: "article", images: property.images[0] ? [{ url: property.images[0] }] : [{ url: `${siteUrl}/opengraph-image` }] },
    twitter: { card: "summary_large_image", title: property.title, description },
  };
}

export default async function PropertyPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<SearchParams> }) {
  const { id } = await params;
  const query = await searchParams;
  const returnCandidate = Array.isArray(query.volver) ? query.volver[0] : query.volver;
  const returnTo = returnCandidate?.startsWith("/") && !returnCandidate.startsWith("//") ? returnCandidate.slice(0, 1600) : "/";
  const property = await getPropertyById(id);
  if (!property) notFound();
  const related = await getRelatedProperties(property);
  const canonical = `${siteUrl}/propiedad/${property.id}`;
  const updated = formatDate(property.updatedAt);
  const specs = propertySpecs(property);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    name: property.title,
    url: canonical,
    description: property.description ?? undefined,
    image: property.images,
    dateModified: property.updatedAt ?? undefined,
    offers: property.price && property.currency ? { "@type": "Offer", price: property.price, priceCurrency: property.currency, availability: "https://schema.org/InStock" } : undefined,
    address: { "@type": "PostalAddress", addressLocality: property.city ?? undefined, addressRegion: property.province ?? undefined, addressCountry: property.country ?? "AR" },
  };
  return (
    <SiteShell>
      <RecentViewTracker id={property.id} title={property.title} price={propertyPrice(property)} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <div className="container py-8">
        <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-2 text-sm text-slate-600"><Link href={returnTo} className="font-bold text-[#2166a5]">← Volver a resultados</Link><span aria-hidden="true">/</span><span aria-current="page">{typeLabels[property.propertyType]}</span></nav>
        <header id="resumen" className="mt-6 scroll-mt-24">
          <div className="flex flex-wrap gap-2"><span className="pill">{operationLabels[property.operation]}</span><span className="pill pill-light">{typeLabels[property.propertyType]}</span>{property.mortgageEligible && <span className="pill pill-gold">Apto crédito</span>}{availabilityLabel(property.status) ? <span className="pill pill-light" title="La disponibilidad de esta publicación no está confirmada en el último relevamiento.">{availabilityLabel(property.status)}</span> : null}</div>
          <h1 className="mt-5 max-w-4xl text-3xl font-black leading-tight tracking-[-0.03em] text-[#0b2748] sm:text-5xl">{property.title}</h1>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3"><div><p className="text-3xl font-black text-[#2166a5]">{propertyPrice(property)}</p><p className="mt-2 text-sm text-slate-600">{propertyLocation(property)}</p>{property.publisher ? <p className="mt-2 text-sm font-bold text-[#0b2748]">Publicado por {property.publisher.name}</p> : null}</div><div className="text-right">{updated && <p className="text-xs text-slate-600">Actualizado el {updated}</p>}<p className="mt-1 text-xs text-slate-600">ID ERETZ {property.id}</p></div></div>
        </header>
        <nav aria-label="Secciones de la propiedad" className="ficha-section-nav">
          <a href="#resumen">Resumen</a>
          <a href="#descripcion">Descripción</a>
          <a href="#caracteristicas">Características</a>
          {property.amenities.length > 0 ? <a href="#servicios">Servicios</a> : null}
          <a href="#ubicacion">Ubicación</a>
          <a href="#publicador">Publicador</a>
          <a href="#aviso">Información del aviso</a>
        </nav>
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(320px,.7fr)]">
          <div className="min-w-0 space-y-8">
            <PropertyGallery images={property.images} title={property.title} />
            <section id="caracteristicas" className="detail-panel scroll-mt-24"><h2>Características</h2>{specs.length ? <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">{specs.map((spec) => <li key={spec} className="rounded-xl bg-[#eef5fb] p-3 text-sm font-bold text-[#0b2748]">{spec}</li>)}</ul> : <p className="mt-3 text-slate-600">Características no informadas.</p>}<div className="mt-4 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">{property.toilettes ? <p>{property.toilettes} toilette{property.toilettes > 1 ? "s" : ""}</p> : null}{property.age ? <p>Antigüedad: {property.age} años</p> : null}{property.floor ? <p>Piso: {property.floor}</p> : null}{property.landArea ? <p>Terreno: {Intl.NumberFormat("es-AR").format(property.landArea)} m²</p> : null}{property.expenses && property.expensesCurrency ? <p>Expensas: {property.expensesCurrency} {Intl.NumberFormat("es-AR").format(property.expenses)}</p> : null}</div></section>
            <section id="descripcion" className="detail-panel scroll-mt-24"><h2>Descripción</h2><p className="mt-4 whitespace-pre-line text-base leading-7 text-slate-700">{property.description ?? "Descripción no disponible"}</p></section>
            {property.amenities.length > 0 && <section id="servicios" className="detail-panel scroll-mt-24"><h2>Servicios y amenities</h2><ul className="mt-4 flex flex-wrap gap-2">{property.amenities.map((amenity) => <li className="rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-700" key={amenity}>{amenity}</li>)}</ul></section>}
            <section id="ubicacion" className="detail-panel scroll-mt-24"><h2>Ubicación</h2><p className="mt-3 text-slate-600">{property.address ? `${property.address}, ` : ""}{propertyLocation(property)}</p><div className="mt-5 h-[420px] overflow-hidden rounded-2xl"><PropertyMap properties={[property]} filters={parsePropertyFilters({})} label="Ubicación de la propiedad" returnTo={returnTo} /></div></section>
            <section id="publicador" className="detail-panel scroll-mt-24"><h2>Publicador</h2>{property.publisher ? <p className="mt-3 text-slate-700">{property.publisher.name}{property.publisher.verified ? " · Verificada" : ""}</p> : <p className="mt-3 text-slate-600">Publicador no especificado.</p>}<p className="mt-2 text-sm text-slate-500">Los datos de contacto están en el panel lateral.</p></section>
            <section id="aviso" className="detail-panel scroll-mt-24"><h2>Información del aviso</h2><div className="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2"><p>Operación: {operationLabels[property.operation]}</p><p>Precio: {propertyPrice(property)}</p>{updated ? <p>Actualizado el {updated}</p> : null}<p>ID ERETZ: {property.id}</p></div>{property.sourceUrl ? <p className="mt-3 text-sm"><a className="font-bold text-[#2166a5]" href={property.sourceUrl} target="_blank" rel="noopener noreferrer nofollow">Ver aviso original</a></p> : null}<p className="mt-3 text-xs leading-5 text-slate-500"><strong>Información de terceros.</strong> El precio, la disponibilidad y las características pueden cambiar. Confirmá con el responsable de la publicación.</p></section>
          </div>
          <div id="contacto" className="min-w-0 scroll-mt-24 lg:sticky lg:top-24 lg:self-start"><ContactActions property={property} canonical={canonical} /><div className="mt-4 rounded-2xl bg-amber-50 p-5 text-xs leading-5 text-amber-950"><strong>Información de terceros.</strong> El precio, la disponibilidad y las características pueden cambiar. Confirmá los datos con el responsable de la publicación. ERETZ no responde por errores del aviso original.</div></div>
        </div>
        {related.length > 0 && <section className="mt-16"><p className="eyebrow">También puede interesarte</p><h2 className="section-title">Propiedades relacionadas</h2><p className="mt-2 text-sm text-slate-600">Selección por ubicación, tipo y operación; no es una recomendación de IA.</p><div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{related.map((item) => <PropertyCard key={item.id} property={item} returnTo={returnTo} />)}</div></section>}
      </div>
    </SiteShell>
  );
}
