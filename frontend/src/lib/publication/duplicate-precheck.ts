// ¿Esta publicación ya existe en el catálogo?
//
// Reutiliza el scorer de `lib/duplicates.ts` en vez de escribir un segundo
// criterio: dos definiciones de "es la misma propiedad" se contradicen en
// cuanto alguien ajuste una.
//
// ---------------------------------------------------------------------------
// UN POSIBLE DUPLICADO NO IMPIDE PUBLICAR
// ---------------------------------------------------------------------------
//
// El caso más común de coincidencia parcial no es alguien duplicando: es una
// inmobiliaria cargando a mano una propiedad que ya scrapeamos de su propio
// sitio. Bloquearla sería impedirle publicar lo suyo.
//
// Por eso el resultado se avisa y no se bloquea. Sólo `CONFIRMED` —que el
// scorer nunca produce solo, hace falta una identidad dura o una persona—
// justificaría frenar, y ese caso hoy no puede ocurrir desde el wizard.
//
// Y sobre todo: **una carga manual nunca modifica una scrapeada**. Si se
// parecen, son dos publicaciones distintas de la misma propiedad física, que es
// exactamente lo que el modelo de entidad ya contempla.

import { classify, scoreMatch, type Confidence, type DupCandidate } from "@/lib/duplicates";
import type { BorradorDePublicacion } from "@/domain/publishing";
import { monedaDelPrecio, montoDelPrecio } from "./adapter";

export type CoincidenciaPosible = {
  candidateId: string;
  confidence: Exclude<Confidence, "NO_MATCH">;
};

export type ResultadoDePrecheck = {
  /** Lo más fuerte que se encontró. */
  confidence: Confidence;
  coincidencias: CoincidenciaPosible[];
  /** Siempre true hoy: ver el encabezado. */
  puedePublicar: boolean;
  /** Qué decirle a la persona, o null si no hay nada que decir. */
  aviso: string | null;
};

/** El borrador con la forma que espera el scorer. */
export function aCandidato(b: BorradorDePublicacion, id = "nueva"): DupCandidate {
  return {
    id,
    operation: b.operation ?? "",
    propertyType: b.propertyType ?? "",
    city: b.city,
    neighborhood: b.neighborhood,
    address: b.address,
    price: montoDelPrecio(b.precio),
    currency: monedaDelPrecio(b.precio),
    totalArea: b.totalArea,
    // El wizard no produce coordenadas: no hay geocoding y no se inventan.
    latitude: null,
    longitude: null,
    title: b.title ?? "",
  };
}

/**
 * Compara contra candidatos YA CARGADOS.
 *
 * No consulta nada: recibe los candidatos que quien llama ya tenga a mano. Sin
 * base extra y sin latencia añadida al formulario.
 */
export function prechequearDuplicados(
  borrador: BorradorDePublicacion,
  candidatos: readonly DupCandidate[],
): ResultadoDePrecheck {
  const propio = aCandidato(borrador);
  const coincidencias: CoincidenciaPosible[] = [];
  let masFuerte: Confidence = "NO_MATCH";

  const rango = (c: Confidence) => (c === "HIGH_CONFIDENCE" ? 2 : c === "POSSIBLE_MATCH" ? 1 : 0);

  for (const candidato of candidatos) {
    if (candidato.id === propio.id) continue;
    const confianza = classify(scoreMatch(propio, candidato));
    if (confianza === "NO_MATCH") continue;
    coincidencias.push({ candidateId: candidato.id, confidence: confianza });
    if (rango(confianza) > rango(masFuerte)) masFuerte = confianza;
  }

  coincidencias.sort((a, b) => rango(b.confidence) - rango(a.confidence) || a.candidateId.localeCompare(b.candidateId));

  return {
    confidence: masFuerte,
    coincidencias,
    // Nunca bloquea. Ver el encabezado.
    puedePublicar: true,
    aviso:
      masFuerte === "HIGH_CONFIDENCE"
        ? "Encontramos una publicación muy parecida. Si ya la publicaste, no hace falta cargarla de nuevo."
        : masFuerte === "POSSIBLE_MATCH"
          ? "Hay una publicación parecida en el catálogo. Revisá que no sea la misma."
          : null,
  };
}
