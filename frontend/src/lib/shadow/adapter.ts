import "server-only";

// Traduce lo que la aplicación ya tiene a lo que los motores del dominio
// esperan. Sin `as`, sin defaults inventados.
//
// ---------------------------------------------------------------------------
// POR QUÉ HACEN FALTA LA FILA CRUDA *Y* LA PROPIEDAD MAPEADA
// ---------------------------------------------------------------------------
//
// `Property` es el resultado de `mapSupabasePropertyToProperty`, y ese mapeo
// toma decisiones de PRESENTACIÓN que borran información que la evaluación
// necesita. Tres casos concretos, encontrados al escribir esto:
//
//   1. Sin título, el mapper escribe `"Propiedad sin título"`. Leer
//      `property.title` haría creer que hay título, y **ninguna publicación
//      aparecería jamás sin él**. La verdad está en `quality.hasValidTitle`.
//
//   2. `normalizeOperation` devuelve `"consultar"` tanto cuando la fuente lo
//      dice como cuando NO HAY DATO. Los dos casos se ven idénticos en
//      `Property`. La distinción sólo existe en `item.operacion`.
//
//   3. El ORIGEN no viaja: `fuente_extraccion` y `cms_origen` están en la fila
//      y no en `Property`.
//
// Los tres empujan en la misma dirección: adaptar sólo desde `Property` daría
// una medición sistemáticamente OPTIMISTA en los campos más básicos, que es
// justo el error que arruinaría el propósito de medir.

import type { EntradaDeModeracion } from "@/domain/moderation";
import type { EntradaDeScore } from "@/domain/quality-score";
import type { ListingOrigin } from "@/domain/listing";
import type { PublicacionAnalizable, QualityReport } from "@/domain/data-quality";
import type { Property, SupabaseProperty } from "@/types/property";

/** Las columnas crudas que la evaluación necesita y `Property` no conserva. */
export type FilaCruda = Pick<SupabaseProperty, "fuente_extraccion" | "cms_origen" | "operacion">;

/**
 * Origen de la publicación, según la fila.
 *
 * No se asume. Casi todo el catálogo viene del pipeline de scraping y va a dar
 * `SCRAPED`, pero eso hay que medirlo — y el subconjunto que NO lo diga es
 * justamente el interesante.
 */
export function origenDeFila(item: FilaCruda): ListingOrigin {
  const fuente = (item.fuente_extraccion ?? "").trim();
  const cms = (item.cms_origen ?? "").trim();
  return fuente || cms ? "SCRAPED" : "UNKNOWN";
}

/** La operación tal como la declaró la fuente, o null si no declaró ninguna. */
export function operacionDeclarada(item: FilaCruda): string | null {
  const crudo = (item.operacion ?? "").trim();
  return crudo || null;
}

/** Host de la fuente. Se usa para no marcar como ajenos los enlaces propios. */
export function hostDeUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

/** El título real, deshaciendo el reemplazo de presentación. */
export function tituloReal(property: Property): string | null {
  return property.quality.hasValidTitle ? property.title : null;
}

/** ¿Hay alguna vía de contacto? Publicador o agente. */
export function tieneContacto(property: Property): boolean {
  return Boolean(
    property.publisher?.phone ||
      property.publisher?.email ||
      property.publisher?.website ||
      property.agentPhone,
  );
}

export function aPublicacionAnalizable(property: Property, item: FilaCruda): PublicacionAnalizable {
  return {
    title: tituloReal(property),
    description: property.description,
    operation: operacionDeclarada(item),
    // `rawPropertyType` y no `propertyType`: el normalizador manda todo lo que
    // no reconoce a "otro", así que el tipo normalizado nunca está ausente y la
    // ausencia real quedaría invisible.
    propertyType: property.rawPropertyType,
    price: property.price,
    currency: property.currency,
    priceUsd: property.priceUsd,
    expenses: property.expenses,
    totalArea: property.totalArea,
    coveredArea: property.coveredArea,
    landArea: property.landArea,
    rooms: property.rooms,
    bedrooms: property.bedrooms,
    bathrooms: property.bathrooms,
    garages: property.garages,
    age: property.age,
    latitude: property.latitude,
    longitude: property.longitude,
    city: property.city,
    province: property.province,
    images: property.images,
  };
}

export function aEntradaDeModeracion(
  property: Property,
  item: FilaCruda,
  quality: QualityReport,
): EntradaDeModeracion {
  return {
    origin: origenDeFila(item),
    publisher: property.publisher ? "IDENTIFIED" : "UNIDENTIFIED",
    quality,
    // Los duplicados NO se evalúan en modo sombra, y hay que tenerlo presente
    // al leer los resultados: detectarlos exige comparar contra el resto del
    // catálogo, no mirar una publicación sola. `NO_MATCH` acá significa "no
    // evaluado", no "verificado que no lo es".
    //
    // Consecuencia directa: el único camino a REJECT para lo scrapeado es
    // DUPLICADO_CONFIRMADO, así que el REJECT de scrapeadas dará 0 **por
    // construcción, no por medición**. Una lectura del informe que celebre ese
    // 0 estaría leyendo mal.
    duplicate: "NO_MATCH",
    title: tituloReal(property),
    description: property.description,
    sourceHost: hostDeUrl(property.sourceUrl),
    hasContact: tieneContacto(property),
    imageCount: property.images.length,
  };
}

export function aEntradaDeScore(
  property: Property,
  item: FilaCruda,
  quality: QualityReport,
): EntradaDeScore {
  return {
    quality,
    locationConfidence: property.locationConfidence,
    imageCount: property.images.length,
    hasDescription: property.description !== null,
    descriptionLength: property.description?.length ?? 0,
    hasPrice: property.price !== null && property.price > 0,
    hasContact: tieneContacto(property),
    presentAttributes: {
      propertyType: property.rawPropertyType !== null,
      operation: operacionDeclarada(item) !== null,
      totalArea: property.totalArea !== null,
      rooms: property.rooms !== null,
      bedrooms: property.bedrooms !== null,
      bathrooms: property.bathrooms !== null,
    },
    publisherIdentified: property.publisher !== null,
    // `verified` ya viene con tres valores del mapper: true, false o null. Se
    // pasa tal cual; colapsarlo presentaría "no evaluada" como "falló".
    publisherVerified: property.publisher?.verified ?? null,
  };
}
