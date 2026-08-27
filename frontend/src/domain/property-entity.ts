// Una PROPIEDAD FÍSICA: el inmueble del mundo real, no su aviso.
//
// La distinción con `Listing` es la que sostiene tres cosas que hoy no se
// pueden hacer:
//
//   - mostrar "esta propiedad está publicada por 3 inmobiliarias a 3 precios";
//   - dejar que una inmobiliaria corrija SU aviso sin tocar el de otra;
//   - contar la oferta real de un barrio sin contar tres veces el mismo depto.
//
// El tercero es el que más importa para ERETZ Mercado: si el conteo de oferta
// mezcla propiedades con publicaciones, toda métrica de mercado sale inflada
// por un factor desconocido y variable según la zona.
//
// ---------------------------------------------------------------------------
// LA ENTIDAD ES UNA INFERENCIA, NO UN HECHO
// ---------------------------------------------------------------------------
//
// Nadie nos dice "estos dos avisos son el mismo departamento". Lo deducimos por
// señales (dirección, coordenadas, superficie, precio) con una confianza
// asociada, que es lo que ya hace `lib/duplicates.ts`.
//
// Consecuencia que el modelo tiene que respetar: agrupar puede estar MAL. Por
// eso la agrupación es **metadato reversible** y nunca destruye publicaciones.
// Deshacer un agrupamiento equivocado tiene que ser posible sin haber perdido
// nada, y eso obliga a que la publicación siga siendo el registro primario.

import type { ListingId, PropertyEntityId } from "./ids";
import type { LocationConfidence, PropertyType } from "@/types/property";

/**
 * Con cuánta confianza se agrupó una publicación bajo esta entidad.
 *
 * Reusa los niveles del scorer existente (`lib/duplicates.ts`) en lugar de
 * inventar una escala paralela: dos vocabularios para lo mismo garantizan que
 * en algún momento se traduzcan mal.
 *
 * CONFIRMED se reserva para lo verificado por una persona o por una identidad
 * dura (la misma URL de la misma fuente). El scorer nunca lo produce solo.
 */
export const ENTITY_LINK_CONFIDENCE = [
  "CONFIRMED",
  "HIGH_CONFIDENCE",
  "POSSIBLE_MATCH",
] as const;
export type EntityLinkConfidence = (typeof ENTITY_LINK_CONFIDENCE)[number];

/**
 * ¿Esta confianza alcanza para agrupar automáticamente?
 *
 * POSSIBLE_MATCH no alcanza, y ésa es la regla central: agrupar de más funde
 * dos propiedades distintas en una y hace desaparecer oferta real del catálogo,
 * un error que el usuario nunca ve y nosotros tampoco. Agrupar de menos sólo
 * muestra un duplicado, que es visible y molesto pero no destruye nada.
 */
export function agrupaAutomaticamente(c: EntityLinkConfidence): boolean {
  return c === "CONFIRMED" || c === "HIGH_CONFIDENCE";
}

/**
 * El vínculo entre una publicación y la entidad física.
 *
 * Guarda la evidencia además del veredicto: sin `evidence` no hay forma de
 * revisar por qué se agrupó algo, ni de mejorar el scorer con casos reales.
 */
export type EntityLink = {
  listingId: ListingId;
  confidence: EntityLinkConfidence;
  /** Señales que sostuvieron la decisión, legibles por una persona. */
  evidence: readonly string[];
  /** Quién lo decidió: el scorer o una persona. */
  decidedBy: "SCORER" | "HUMAN";
  decidedAt: string | null;
};

/**
 * Los atributos físicos, que por definición no dependen de quién publique.
 *
 * El precio NO está acá, y es intencional: el precio es de la publicación. La
 * misma propiedad puede tener dos precios simultáneos y ninguno es "el precio
 * de la propiedad".
 */
export type PhysicalAttributes = {
  propertyType: PropertyType;
  totalArea: number | null;
  coveredArea: number | null;
  landArea: number | null;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  garages: number | null;
  /** Antigüedad en años según la fuente. */
  age: number | null;
};

export type CanonicalLocation = {
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  /** Se preserva la semántica de cuatro niveles ya existente. */
  confidence: LocationConfidence;
};

export type PropertyEntity = {
  id: PropertyEntityId;
  location: CanonicalLocation;
  attributes: PhysicalAttributes;
  /** Las publicaciones agrupadas bajo esta entidad, con su evidencia. */
  links: readonly EntityLink[];
};

/**
 * Publicaciones que se muestran como "la misma propiedad".
 *
 * Filtra las POSSIBLE_MATCH: están enlazadas para poder revisarlas, pero no se
 * presentan como confirmadas. Enlazar y afirmar son cosas distintas.
 */
export function listingsAgrupados(e: PropertyEntity): ListingId[] {
  return e.links.filter((l) => agrupaAutomaticamente(l.confidence)).map((l) => l.listingId);
}

/** Publicaciones enlazadas con dudas, para una cola de revisión humana. */
export function listingsPorRevisar(e: PropertyEntity): EntityLink[] {
  return e.links.filter((l) => l.confidence === "POSSIBLE_MATCH");
}

/**
 * ¿Cuánto cuenta esta entidad para una métrica de oferta?
 *
 * Siempre 1, y por eso existe la función: para que quede un único lugar donde
 * se afirme "una propiedad física cuenta una vez", en lugar de que cada
 * consulta de Mercado decida por su cuenta si cuenta avisos o inmuebles.
 */
export function pesoEnOferta(): 1 {
  return 1;
}

/**
 * ¿Está la entidad respaldada por algo?
 *
 * Una entidad sin publicaciones agrupadas no debería existir: sería un inmueble
 * del que no tenemos ni un aviso. Si aparece, es un bug de la agrupación —por
 * ejemplo, haber desagrupado todo sin borrar la entidad.
 */
export function estaHuerfana(e: PropertyEntity): boolean {
  return listingsAgrupados(e).length === 0;
}
