import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { PropertyMap } from "@/components/map/PropertyMap";
import { CollectionPicker } from "@/components/property/CollectionPicker";
import { ContactActions } from "@/components/property/ContactActions";
import { PriceTag } from "@/components/property/PriceTag";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PropertyDetailActions } from "@/components/property/PropertyDetailActions";
import { PropertyDetailFacts } from "@/components/property/PropertyDetailFacts";
import { PropertyGallery } from "@/components/property/PropertyGallery";
import { RecentViewTracker } from "@/components/property/RecentViewTracker";
import { ReportButton } from "@/components/property/ReportButton";
import { locationConfidenceDescription, locationConfidenceLabel } from "@/lib/geo-confidence";
import { propertyDetailGroups, propertyDetailTitle, propertyReturnContext, publicationMatchConfidence } from "@/lib/property-detail";
import { availabilityLabel, formatDate, operationLabels, propertyLocation, propertyPrice, propertySpecs, typeLabels } from "@/lib/property-presenter";
import { parsePropertyFilters, type SearchParams } from "@/lib/property-query";
import { getOtherPublications, getPriceHistory, getPropertyById, getRelatedProperties } from "@/lib/property-service";
import { siteUrl } from "@/lib/site-url";
import { entitySlug } from "@/lib/slug";
import type { PropertySummary } from "@/types/property";

const money = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const property = await getPropertyById(id);
  if (!property) notFound();
  const title = propertyDetailTitle(property);
  const description = `${typeLabels[property.propertyType]} en ${operationLabels[property.operation].toLowerCase()}. ${propertyLocation(property)}. ${propertyPrice(property)}.`;
  const canonical = `${siteUrl}/propiedad/${property.id}`;
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: { title, description, url: canonical, type: "article", images: property.images[0] ? [{ url: property.images[0] }] : [{ url: `${siteUrl}/opengraph-image` }] },
    twitter: { card: "summary_large_image", title, description },
  };
}

function PublicationGroup({ title, description, properties, returnTo }: { title: string; description: string; properties: PropertySummary[]; returnTo: string }) {
  if (!properties.length) return null;
  return (
    <section className="publication-match-group">
      <div><h3>{title}</h3><p>{description}</p></div>
      <div className="detail-related-grid">
        {properties.map((item) => <PropertyCard key={item.id} property={item} returnTo={returnTo} variant="grid" />)}
      </div>
    </section>
  );
}

export default async function PropertyPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<SearchParams> }) {
  const { id } = await params;
  const query = await searchParams;
  const returnCandidate = Array.isArray(query.volver) ? query.volver[0] : query.volver;
  const returnTo = returnCandidate?.startsWith("/") && !returnCandidate.startsWith("//") ? returnCandidate.slice(0, 1600) : "/propiedades";
  const property = await getPropertyById(id);
  if (!property) notFound();
  const [related, otherPublications, priceHistory] = await Promise.all([
    getRelatedProperties(property),
    getOtherPublications(property),
    getPriceHistory(id),
  ]);
  const canonical = `${siteUrl}/propiedad/${property.id}`;
  const title = propertyDetailTitle(property);
  const updated = formatDate(property.updatedAt);
  const published = formatDate(property.publishedAt);
  const specs = propertySpecs(property).slice(0, 5);
  const factGroups = propertyDetailGroups(property);
  const returnContext = propertyReturnContext(returnTo);
  const areaForPrice = property.totalArea ?? property.coveredArea;
  const pricePerSquareMeter = property.price && property.currency && areaForPrice
    ? `${property.currency} ${money.format(property.price / areaForPrice)} por m²`
    : null;
  const highConfidencePublications: PropertySummary[] = [];
  const limitedConfidencePublications: PropertySummary[] = [];
  for (const item of otherPublications) {
    if (publicationMatchConfidence(property, item) === "HIGH_CONFIDENCE") highConfidencePublications.push(item);
    else limitedConfidencePublications.push(item);
  }
  const jsonLd = {
    "@context": "https://schema.org", "@type": "RealEstateListing", name: title, url: canonical,
    description: property.description ?? undefined, image: property.images, dateModified: property.updatedAt ?? undefined,
    offers: property.price && property.currency ? { "@type": "Offer", price: property.price, priceCurrency: property.currency, availability: "https://schema.org/InStock" } : undefined,
    address: { "@type": "PostalAddress", addressLocality: property.city ?? undefined, addressRegion: property.province ?? undefined, addressCountry: property.country ?? "AR" },
  };

  return (
    <SiteShell>
      <RecentViewTracker id={property.id} title={title} price={propertyPrice(property)} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <main className="detail-page container">
        <nav aria-label="Volver al contexto de búsqueda" className="detail-return">
          <Link href={returnTo} scroll={false}>← Volver a resultados</Link>
          {returnContext ? <span>{returnContext}</span> : null}
        </nav>

        <PropertyGallery images={property.images} title={title} />

        <div className="detail-overview-grid">
          <header id="resumen" className="detail-overview scroll-mt-24">
            <div className="detail-kickers">
              <span>{operationLabels[property.operation]}</span>
              <span>{typeLabels[property.propertyType]}</span>
              {availabilityLabel(property.status) ? <span>{availabilityLabel(property.status)}</span> : null}
            </div>
            <h1>{title}</h1>
            <PriceTag property={property} className="detail-price" />
            <div className="detail-price-meta">
              {property.expenses && property.expensesCurrency ? <span>Expensas {property.expensesCurrency} {money.format(property.expenses)}</span> : null}
              {pricePerSquareMeter ? <span>{pricePerSquareMeter}</span> : null}
            </div>
            <p className="detail-location">{propertyLocation(property)}</p>
            {specs.length ? <ul className="detail-specs" aria-label="Características principales">{specs.map((spec) => <li key={spec}>{spec}</li>)}</ul> : null}
            <PropertyDetailActions property={property} canonical={canonical} />
          </header>
          <div id="contacto" className="detail-contact-column scroll-mt-24">
            <ContactActions property={property} canonical={canonical} />
            <CollectionPicker propertyId={property.id} />
          </div>
        </div>

        <div className="detail-body-grid">
          <div className="detail-content">
            <nav aria-label="Secciones de la propiedad" className="ficha-section-nav">
              <a href="#caracteristicas">Características</a>
              {property.description ? <a href="#descripcion">Descripción</a> : null}
              {property.amenities.length ? <a href="#servicios">Servicios</a> : null}
              <a href="#ubicacion">Ubicación</a>
              {property.publisher || property.agentName ? <a href="#publicador">Publicador</a> : null}
              <a href="#transparencia">Transparencia</a>
            </nav>
            <PropertyDetailFacts groups={factGroups} />
            {property.description ? <section id="descripcion" className="detail-panel scroll-mt-24"><h2>Descripción</h2><p className="detail-description">{property.description}</p></section> : null}
            {property.amenities.length ? <section id="servicios" className="detail-panel scroll-mt-24"><h2>Servicios y amenities</h2><ul className="detail-amenities">{property.amenities.map((amenity) => <li key={amenity}>{amenity}</li>)}</ul></section> : null}
            <section id="ubicacion" className="detail-panel scroll-mt-24">
              <div className="detail-section-heading"><h2>Ubicación</h2><span className={`location-confidence-badge is-${property.locationConfidence}`}>{locationConfidenceLabel(property.locationConfidence)}</span></div>
              <p className="detail-description">{property.address ? `${property.address}, ` : ""}{propertyLocation(property)}</p>
              {property.locationConfidence !== "high" ? <p className="detail-location-note">{locationConfidenceDescription(property.locationConfidence)}</p> : null}
              <p className="detail-fineprint">La ubicación depende de la precisión disponible en la publicación original.</p>
              {property.locationConfidence === "none" ? <div className="location-unavailable" role="status">Esta propiedad no tiene una ubicación utilizable en el mapa.</div> : <div className="detail-map"><PropertyMap properties={[property]} filters={parsePropertyFilters({})} label="Ubicación de la propiedad" returnTo={returnTo} /></div>}
            </section>
            {property.publisher || property.agentName ? (
              <section id="publicador" className="detail-panel scroll-mt-24">
                <p className="eyebrow">Quién publica</p><h2>{property.publisher?.name ?? property.agentName}</h2>
                {property.publisher?.verified ? <p className="detail-verified">Identidad verificada en ERETZ</p> : null}
                {property.agentName && property.agentName !== property.publisher?.name ? <p className="detail-description">Agente: {property.agentName}</p> : null}
                {property.publisher?.id ? <Link href={`/inmobiliaria/${entitySlug(property.publisher.id, property.publisher.name)}`} className="inline-action">Ver perfil y publicaciones →</Link> : null}
              </section>
            ) : null}
            <section id="transparencia" className="detail-panel detail-transparency scroll-mt-24">
              <h2>Información de la publicación</h2>
              <dl>
                <div><dt>ID ERETZ</dt><dd>{property.id}</dd></div>
                {updated ? <div><dt>Actualización</dt><dd>{updated}</dd></div> : null}
                {published ? <div><dt>Publicación</dt><dd>{published}</dd></div> : null}
                <div><dt>Disponibilidad</dt><dd>{availabilityLabel(property.status) ?? "Confirmada en el último relevamiento"}</dd></div>
              </dl>
              <div className="detail-transparency-actions">
                {property.sourceUrl ? <a href={property.sourceUrl} target="_blank" rel="noopener noreferrer nofollow">Ver publicación original ↗</a> : null}
                <ReportButton propertyId={property.id} />
                <Link href={`/baja-o-correccion?propiedad=${encodeURIComponent(property.id)}`}>Solicitar corrección</Link>
              </div>
              <p>La información proviene de terceros y puede cambiar. Confirmala con quien publicó el aviso.</p>
            </section>
          </div>
        </div>

        {priceHistory.length > 1 ? (
          <section className="detail-lower-section" aria-labelledby="price-history-heading">
            <p className="eyebrow">Transparencia</p><h2 id="price-history-heading" className="section-title">Historial de precio</h2>
            <div className="price-history-summary">
              <p><span>Precio inicial</span><strong>{priceHistory[0].currency ? `${priceHistory[0].currency} ` : ""}{money.format(priceHistory[0].price)}</strong></p>
              <p><span>Precio actual</span><strong>{priceHistory.at(-1)?.currency ? `${priceHistory.at(-1)?.currency} ` : ""}{money.format(priceHistory.at(-1)?.price ?? 0)}</strong></p>
              <p><span>Cambios registrados</span><strong>{priceHistory.length - 1}</strong></p>
            </div>
            <ol className="price-history-list">{priceHistory.map((point, index) => <li key={`${point.at}-${index}`}><time dateTime={point.at}>{formatDate(point.at)}</time><strong>{point.currency ? `${point.currency} ` : ""}{money.format(point.price)}</strong></li>)}</ol>
          </section>
        ) : null}

        {otherPublications.length ? (
          <section className="detail-lower-section" aria-labelledby="other-publications-heading">
            <p className="eyebrow">Publicaciones relacionadas</p><h2 id="other-publications-heading" className="section-title">Avisos que podrían corresponder a esta propiedad</h2>
            <p className="section-intro">La coincidencia se calcula con señales disponibles; no afirmamos que dos avisos sean la misma propiedad sin evidencia suficiente.</p>
            <PublicationGroup title="Alta confianza" description="Varias señales coinciden de forma consistente." properties={highConfidencePublications} returnTo={returnTo} />
            <PublicationGroup title="Confianza limitada" description="Comparten algunas señales, pero necesitás confirmar la relación con cada publicador." properties={limitedConfidencePublications} returnTo={returnTo} />
          </section>
        ) : null}

        {related.length ? (
          <section className="detail-lower-section" aria-labelledby="related-heading">
            <p className="eyebrow">También puede interesarte</p><h2 id="related-heading" className="section-title">Propiedades similares</h2>
            <p className="section-intro">Coinciden por ubicación, tipo y operación. El orden es neutral.</p>
            <div className="detail-related-grid is-four">
              {related.map(({ property: item, reasons }) => (
                <div key={item.id} className="related-item">
                  <PropertyCard property={item} returnTo={returnTo} variant="grid" />
                  {/* Por qué se parece, en palabras. Nunca el puntaje: un
                      número interno no le dice nada a quien mira y sugeriría un
                      orden comercial que no existe. */}
                  {reasons.length ? (
                    <ul className="related-reasons">
                      {reasons.slice(0, 3).map((motivo) => <li key={motivo}>{motivo}</li>)}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </SiteShell>
  );
}
