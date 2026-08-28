// Traduce un borrador del wizard a lo que esperan los motores de dominio.
//
// Existe para no duplicar reglas. Los motores de calidad, moderación y puntaje
// ya están escritos y probados; lo único que falta es que sepan leer la forma
// del borrador, que es distinta de la de una propiedad del catálogo.
//
// Diferencia importante con el adaptador del modo sombra: allá había que
// deshacer el saneo del mapper, porque la propiedad venía de la base ya
// procesada. Acá el borrador es lo que la persona escribió, sin pasar por
// ningún normalizador, así que los valores se leen tal cual.

import type { PublicacionAnalizable, QualityReport } from "@/domain/data-quality";
import type { EntradaDeModeracion } from "@/domain/moderation";
import type { EntradaDeScore } from "@/domain/quality-score";
import type { BorradorDePublicacion, PrecioDeclarado } from "@/domain/publishing";

/**
 * El monto, o `null` si es "a consultar".
 *
 * Los dos casos son legítimos y distintos, y el `null` que devuelve acá para
 * "a consultar" no es una pérdida de información: el análisis de calidad trata
 * la ausencia de precio como algo normal, no como un defecto.
 */
export function montoDelPrecio(precio: PrecioDeclarado | null): number | null {
  return precio?.kind === "MONTO" ? precio.amount : null;
}

export function monedaDelPrecio(precio: PrecioDeclarado | null): string | null {
  return precio?.kind === "MONTO" ? precio.currency : null;
}

export function aPublicacionAnalizable(b: BorradorDePublicacion): PublicacionAnalizable {
  const monto = montoDelPrecio(b.precio);
  return {
    title: b.title,
    description: b.description,
    operation: b.operation,
    propertyType: b.propertyType,
    price: monto,
    currency: monedaDelPrecio(b.precio),
    // `priceUsd` sólo cuando la persona eligió dólares. No se convierte: no hay
    // cotización, y usar una inventada haría que los rangos de precio evaluaran
    // otra cosa.
    priceUsd: b.precio?.kind === "MONTO" && b.precio.currency === "USD" ? b.precio.amount : null,
    expenses: b.expenses,
    totalArea: b.totalArea,
    coveredArea: b.coveredArea,
    landArea: null,
    rooms: b.rooms,
    bedrooms: b.bedrooms,
    bathrooms: b.bathrooms,
    garages: null,
    age: null,
    // El wizard no pide coordenadas y no las inventa: no hay geocoding.
    latitude: null,
    longitude: null,
    city: b.city,
    province: b.province,
    images: b.images,
  };
}

export function aEntradaDeModeracion(
  b: BorradorDePublicacion,
  quality: QualityReport,
): EntradaDeModeracion {
  return {
    // Una publicación del wizard es MANUAL, siempre. Es lo que habilita
    // bloquearla cuando corresponde, a diferencia de lo scrapeado.
    origin: "MANUAL",
    // Quien carga a mano está identificado por su sesión, sea particular,
    // agente u organización.
    publisher: "IDENTIFIED",
    quality,
    // Los duplicados se evalúan aparte, contra candidatos ya cargados. Ver
    // `duplicate-precheck.ts`.
    duplicate: "NO_MATCH",
    title: b.title,
    description: b.description,
    // No hay fuente externa: la publicación nace acá.
    sourceHost: null,
    hasContact: Boolean(b.contactPhone?.trim() || b.contactEmail?.trim()),
    imageCount: b.images.length,
  };
}

export function aEntradaDeScore(b: BorradorDePublicacion, quality: QualityReport): EntradaDeScore {
  return {
    quality,
    // Sin coordenadas ni geocoding, la confianza de ubicación se deriva de qué
    // tan específico es el texto. `none` sería mentir hacia abajo cuando hay
    // dirección; `high` sería mentir hacia arriba sin haber verificado nada.
    locationConfidence: b.address?.trim() ? "approximate" : b.city?.trim() ? "doubtful" : "none",
    imageCount: b.images.length,
    hasDescription: Boolean(b.description?.trim()),
    descriptionLength: b.description?.trim().length ?? 0,
    hasPrice: b.precio !== null,
    hasContact: Boolean(b.contactPhone?.trim() || b.contactEmail?.trim()),
    presentAttributes: {
      propertyType: b.propertyType !== null,
      operation: b.operation !== null,
      totalArea: b.totalArea !== null,
      rooms: b.rooms !== null,
      bedrooms: b.bedrooms !== null,
      bathrooms: b.bathrooms !== null,
    },
    publisherIdentified: true,
    // Verificación del publicador: `null` es "no evaluada", que es la verdad.
    // `false` diría que falló una verificación que nunca se intentó.
    publisherVerified: null,
  };
}
