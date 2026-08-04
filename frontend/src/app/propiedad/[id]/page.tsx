import type { Metadata } from "next";
import { siteUrl } from "@/lib/site-url";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyMap } from "@/components/map/PropertyMap";
import { ContactActions } from "@/components/property/ContactActions";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PropertyGallery } from "@/components/property/PropertyGallery";
import { formatDate, operationLabels, propertyLocation, propertyPrice, propertySpecs, typeLabels } from "@/lib/property-presenter";
import { getPropertyById, getRelatedProperties } from "@/lib/property-service";


export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const property = await getPropertyById(id);
  if (!property) return { title: "Propiedad no encontrada | ERETZ Propiedades", robots: { index: false } };
  const description = `${typeLabels[property.propertyType]} en ${operationLabels[property.operation]}. ${propertyLocation(property)}. ${propertyPrice(property)}.`;
  const canonical = `${siteUrl}/propiedad/${property.id}`;
  return {
    title: property.title,
    description,
    alternates: { canonical },
    openGraph: { title: property.title, description, url: canonical, type: "article", images: property.images[0] ? [{ url: property.images[0] }] : [{ url: `${siteUrl}/og.png` }] },
    twitter: { card: "summary_large_image", title: property.title, description },
  };
}

export default async function PropertyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
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
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <div className="container py-8">
        <nav aria-label="Migas de pan" className="text-sm text-slate-500"><Link href="/">Inicio</Link> <span aria-hidden="true">/</span> <Link href="/propiedades">Propiedades</Link> <span aria-hidden="true">/</span> <span aria-current="page">{typeLabels[property.propertyType]}</span></nav>
        <header className="mt-6">
          <div className="flex flex-wrap gap-2"><span className="pill">{operationLabels[property.operation]}</span><span className="pill pill-light">{typeLabels[property.propertyType]}</span>{property.mortgageEligible && <span className="pill pill-gold">Apto crédito</span>}</div>
          <h1 className="mt-5 max-w-4xl text-3xl font-black leading-tight tracking-[-0.03em] text-[#0b2748] sm:text-5xl">{property.title}</h1>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3"><div><p className="text-3xl font-black text-[#2166a5]">{propertyPrice(property)}</p><p className="mt-2 text-sm text-slate-600">{propertyLocation(property)}</p></div>{updated && <p className="text-xs text-slate-500">Actualizado el {updated}</p>}</div>
        </header>
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(320px,.7fr)]">
          <div className="min-w-0 space-y-8">
            <PropertyGallery images={property.images} title={property.title} />
            <section className="detail-panel"><h2>Características</h2>{specs.length ? <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">{specs.map((spec) => <li key={spec} className="rounded-xl bg-[#eef5fb] p-3 text-sm font-bold text-[#0b2748]">{spec}</li>)}</ul> : <p className="mt-3 text-slate-600">Características no informadas.</p>}{property.toilettes && <p className="mt-4 text-sm text-slate-600">{property.toilettes} toilette{property.toilettes > 1 ? "s" : ""}</p>}{property.age && <p className="mt-2 text-sm text-slate-600">Antigüedad informada: {property.age} años</p>}</section>
            <section className="detail-panel"><h2>Descripción</h2><p className="mt-4 whitespace-pre-line text-base leading-7 text-slate-700">{property.description ?? "Descripción no disponible"}</p></section>
            {property.amenities.length > 0 && <section className="detail-panel"><h2>Amenities</h2><ul className="mt-4 flex flex-wrap gap-2">{property.amenities.map((amenity) => <li className="rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-700" key={amenity}>{amenity}</li>)}</ul></section>}
            <section className="detail-panel"><h2>Ubicación</h2><p className="mt-3 text-slate-600">{property.address ? `${property.address}, ` : ""}{propertyLocation(property)}</p><div className="mt-5"><PropertyMap properties={[property]} label="Ubicación de la propiedad" /></div></section>
          </div>
          <div className="min-w-0 lg:sticky lg:top-24 lg:self-start"><ContactActions property={property} canonical={canonical} /><div className="mt-4 rounded-2xl bg-amber-50 p-5 text-xs leading-5 text-amber-950"><strong>Información de terceros.</strong> El precio, la disponibilidad y las características pueden cambiar. Confirmá los datos con el responsable de la publicación. ERETZ no responde por errores del aviso original.</div></div>
        </div>
        {related.length > 0 && <section className="mt-16"><p className="eyebrow">También puede interesarte</p><h2 className="section-title">Propiedades relacionadas</h2><div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{related.map((item) => <PropertyCard key={item.id} property={item} />)}</div></section>}
      </div>
    </SiteShell>
  );
}
