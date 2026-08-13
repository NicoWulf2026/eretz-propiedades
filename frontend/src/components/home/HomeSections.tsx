import Link from "next/link";
import { PropertyImage } from "@/components/property/PropertyImage";
import { PriceTag } from "@/components/property/PriceTag";
import { propertyLocation, typeLabels } from "@/lib/property-presenter";
import { displayableImages } from "@/lib/image-quality";
import type { CityBlock, Carousel } from "@/lib/home-data";
import type { RealEstateSummary } from "@/types/property";

const number = new Intl.NumberFormat("es-AR");

// Tarjeta de lugar: misma geometría que la referencia (288x216, radio 16) pero
// tipográfica. Ver el comentario en home-data.ts: no hay dataset curado de
// imagen por ciudad y usar la foto de un aviso terminaba mostrando el logo de
// una inmobiliaria como portada.
export function PlaceCard({ block }: { block: CityBlock }) {
  return (
    <Link href={`/propiedades?ubicaciones=${encodeURIComponent(block.name)}`} className="place-card" prefetch={false}>
      <span className="place-card-body">
        <span className="place-card-name">{block.name}</span>
        <span className="place-card-count">{number.format(block.count)} propiedades</span>
      </span>
    </Link>
  );
}

export function PlaceGrid({ blocks, title, id }: { blocks: CityBlock[]; title: string; id: string }) {
  if (!blocks.length) return null;
  return (
    <section className="home-section" id={id}>
      <div className="container">
        <h2 className="home-section-title">{title}</h2>
        <div className="place-grid">
          {blocks.map((b) => <PlaceCard key={b.name} block={b} />)}
        </div>
      </div>
    </section>
  );
}

export function PlaceChips({ blocks, label }: { blocks: CityBlock[]; label: string }) {
  if (!blocks.length) return null;
  return (
    <section className="home-chips" aria-label={label}>
      <div className="container">
        <ul className="place-chip-list">
          {blocks.map((b) => (
            <li key={b.name}>
              <Link href={`/propiedades?ubicaciones=${encodeURIComponent(b.name)}`} className="place-chip" prefetch={false}>
                {b.name}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// Carrusel horizontal de propiedades reales. Misma tarjeta 288x216 y gap 16 que
// la referencia, con scroll horizontal.
export function PropertyCarousel({ data }: { data: Carousel }) {
  return (
    <section className="home-section">
      <div className="container">
        <div className="home-section-head">
          <h2 className="home-section-title">{data.title}</h2>
          <Link href={data.href} className="home-section-more" prefetch={false}>Ver todas</Link>
        </div>
      </div>
      <div className="container">
        <ul className="home-carousel">
          {data.properties.map((p) => {
            const images = displayableImages(p.images ?? [], p.publisher?.name);
            return (
              <li key={p.id}>
                <Link href={`/propiedad/${p.id}`} className="carousel-card" prefetch={false}>
                  <span className="carousel-card-media" aria-hidden="true">
                    {images[0] ? <PropertyImage src={images[0]} alt="" /> : null}
                  </span>
                  <PriceTag property={p} className="carousel-card-price" />
                  <span className="carousel-card-type">{typeLabels[p.propertyType]}</span>
                  <span className="carousel-card-location">{propertyLocation(p)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

export function FeatureGrid({ title, subtitle, items }: {
  title: string; subtitle: string;
  items: { icon: string; name: string; text: string; href: string }[];
}) {
  return (
    <section className="home-section home-section-centered">
      <div className="container">
        <h2 className="home-section-title">{title}</h2>
        <p className="home-section-lede">{subtitle}</p>
        <div className="feature-grid">
          {items.map((f) => (
            <Link key={f.name} href={f.href} className="feature-card" prefetch={false}>
              <span className="feature-icon" aria-hidden="true">{f.icon}</span>
              <h3>{f.name}</h3>
              <p>{f.text}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

export function AgencyStrip({ agencies }: { agencies: RealEstateSummary[] }) {
  if (!agencies.length) return null;
  return (
    <section className="home-section home-agencies">
      <div className="container">
        <div className="home-section-head">
          <h2 className="home-section-title">Inmobiliarias en ERETZ</h2>
          <Link href="/inmobiliarias" className="home-section-more" prefetch={false}>Ver el directorio</Link>
        </div>
        <p className="home-section-lede home-section-lede-left">
          ERETZ es un agregador independiente: los datos provienen de las publicaciones originales y el
          contacto se realiza siempre con quien publicó cada propiedad.
        </p>
        <ul className="agency-strip">
          {agencies.map((a) => (
            <li key={a.id}>
              <Link href={`/inmobiliaria/${a.slug}`} className="agency-chip-card" prefetch={false}>
                <span className="agency-chip-monogram" aria-hidden="true">{a.name.slice(0, 1)}</span>
                <span className="agency-chip-body">
                  <span className="agency-chip-name">{a.name}</span>
                  <span className="agency-chip-meta">{number.format(a.listingsCount)} publicaciones</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function AboutSection({ total }: { total: number }) {
  return (
    <section className="home-section home-about">
      <div className="container">
        <h2 className="home-section-title">Qué es ERETZ Propiedades</h2>
        <div className="home-about-grid">
          <div>
            <p>
              ERETZ Propiedades centraliza avisos inmobiliarios de toda la Argentina para que buscar
              sea más fácil. Hoy hay {number.format(total)} publicaciones en el catálogo, provenientes
              de inmobiliarias y desarrolladoras de todo el país.
            </p>
            <p>
              No mostramos propiedades solamente: ordenamos y normalizamos la información para que se
              pueda comparar, y mantenemos la trazabilidad a la publicación original.
            </p>
          </div>
          <div>
            <p>
              ERETZ no vende propiedades ni cobra por alterar el orden orgánico de los resultados. El
              contacto y la operación se realizan siempre con quien publicó cada aviso.
            </p>
            <p>
              La información es de terceros y puede cambiar: el precio, la disponibilidad y las
              características deben confirmarse con el responsable de la publicación.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
