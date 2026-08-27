// Historia de una publicación: qué cambió, cuándo lo supimos, y qué NO sabemos.
//
// ---------------------------------------------------------------------------
// SEIS FECHAS QUE NO SON LA MISMA
// ---------------------------------------------------------------------------
//
//   publishedAt        cuándo se publicó, según la fuente
//   sourceUpdatedAt    cuándo la fuente dice que la modificó
//   firstSeenAt        la primera vez que ERETZ la vio
//   lastSeenAt         la última vez que ERETZ la vio en la fuente
//   updatedAt          cuándo cambió nuestro registro
//   observedAt         cuándo se tomó una observación puntual
//
// La confusión cara es usar `firstSeenAt` como fecha de publicación. Que la
// hayamos visto por primera vez el martes no dice nada sobre cuándo se publicó:
// pudo estar publicada dos años antes de que ERETZ existiera. Presentarla como
// "publicada el martes" convierte todo el catálogo en falsamente reciente, y
// además arruina cualquier métrica de antigüedad de la oferta.
//
// Cuando `publishedAt` es null, es null. Se muestra "Actualizada" —que es lo
// que la ficha ya hace— y no se rellena con la primera observación.
//
// ---------------------------------------------------------------------------
// UN CAMBIO ENTRE DOS OBSERVACIONES NO TIENE FECHA, TIENE INTERVALO
// ---------------------------------------------------------------------------
//
// Si el lunes vimos USD 100.000 y el viernes USD 90.000, sabemos que bajó. NO
// sabemos cuándo: pudo ser el martes o el jueves. El evento ocurrió en algún
// momento del intervalo (lunes, viernes].
//
// Esto no es una sutileza. Un gráfico de precios que ponga la baja el viernes
// está afirmando algo que no observamos, y con scraping semanal el error es de
// hasta siete días en cada punto de la serie. Por eso `CambioDetectado` lleva
// el intervalo entero y no una fecha, y quien dibuje la serie decide cómo
// representar esa incertidumbre en vez de perderla.

import type { ListingId } from "./ids";
import type { ObservationStatus } from "./listing";

/** Las fechas de una publicación, con sus significados separados. */
export type MarcasDeTiempo = {
  publishedAt: string | null;
  sourceUpdatedAt: string | null;
  firstSeenAt: string | null;
  lastSeenAt: string | null;
  updatedAt: string | null;
};

/**
 * La mejor fecha disponible para mostrar, y qué es realmente.
 *
 * Devuelve la etiqueta junto al valor para que la UI no tenga que adivinar si
 * lo que recibió es una publicación o una actualización. Es lo que evita que
 * alguien muestre "Publicada" sobre un `firstSeenAt`.
 */
export type FechaParaMostrar =
  | { fecha: string; tipo: "PUBLICADA" }
  | { fecha: string; tipo: "ACTUALIZADA" }
  | { fecha: null; tipo: "SIN_FECHA" };

export function fechaParaMostrar(m: MarcasDeTiempo): FechaParaMostrar {
  if (m.publishedAt) return { fecha: m.publishedAt, tipo: "PUBLICADA" };
  // `sourceUpdatedAt` antes que `updatedAt`: la fecha de la fuente le dice algo
  // a quien mira; la de nuestro registro sólo nos dice a nosotros.
  const actualizada = m.sourceUpdatedAt ?? m.updatedAt;
  if (actualizada) return { fecha: actualizada, tipo: "ACTUALIZADA" };
  return { fecha: null, tipo: "SIN_FECHA" };
}

/**
 * ¿`firstSeenAt` se está usando como fecha de publicación?
 *
 * Existe como función para poder testear la regla, no sólo escribirla en un
 * comentario que nadie relee.
 */
export function esFechaDePublicacionLegitima(m: MarcasDeTiempo, fecha: string | null): boolean {
  if (fecha === null) return true;
  if (fecha === m.firstSeenAt && fecha !== m.publishedAt) return false;
  return true;
}

// --- snapshots -------------------------------------------------------------

/**
 * Lo que observamos de una publicación en un momento dado.
 *
 * Sólo los atributos que cambian. El tipo de propiedad o la superficie no van:
 * si cambiaran, no es que la publicación se actualizó, es que estamos mirando
 * otra propiedad.
 */
export type ListingSnapshot = {
  listingId: ListingId;
  observedAt: string;
  price: number | null;
  currency: string | null;
  expenses: number | null;
  availability: ObservationStatus;
  publisherKey: string | null;
  /** De qué corrida de scraping salió. Permite auditar una serie rara. */
  source: string | null;
};

export const TIPOS_DE_CAMBIO = [
  "PRICE_INCREASED",
  "PRICE_DECREASED",
  "CURRENCY_CHANGED",
  "EXPENSES_CHANGED",
  "BECAME_UNAVAILABLE",
  "RETURNED",
  "PUBLISHER_CHANGED",
] as const;
export type TipoDeCambio = (typeof TIPOS_DE_CAMBIO)[number];

/**
 * Un cambio detectado entre dos observaciones.
 *
 * `desde`/`hasta` acotan cuándo pudo ocurrir. No hay campo `fecha` a propósito:
 * no la sabemos, y ofrecerla invitaría a usarla como si fuera exacta.
 */
export type CambioDetectado = {
  tipo: TipoDeCambio;
  /** Última observación en la que todavía no había cambiado. */
  desde: string;
  /** Primera observación en la que ya había cambiado. */
  hasta: string;
  anterior: string | number | null;
  nuevo: string | number | null;
};

/**
 * Compara dos observaciones consecutivas.
 *
 * `previo` tiene que ser anterior a `actual`; si vienen al revés se devuelve
 * vacío en vez de inventar cambios invertidos.
 */
export function compararSnapshots(
  previo: ListingSnapshot,
  actual: ListingSnapshot,
): CambioDetectado[] {
  if (previo.listingId !== actual.listingId) return [];
  if (!(previo.observedAt < actual.observedAt)) return [];

  const cambios: CambioDetectado[] = [];
  const agregar = (
    tipo: TipoDeCambio,
    anterior: string | number | null,
    nuevo: string | number | null,
  ) => cambios.push({ tipo, desde: previo.observedAt, hasta: actual.observedAt, anterior, nuevo });

  // El precio sólo se compara dentro de la misma moneda. Comparar 100.000 ARS
  // con 100.000 USD y reportar "sin cambios" sería peor que no comparar.
  const mismaMoneda = previo.currency === actual.currency;

  if (previo.currency !== actual.currency && (previo.currency || actual.currency)) {
    agregar("CURRENCY_CHANGED", previo.currency, actual.currency);
  }

  if (mismaMoneda && previo.price !== null && actual.price !== null && previo.price !== actual.price) {
    agregar(actual.price > previo.price ? "PRICE_INCREASED" : "PRICE_DECREASED", previo.price, actual.price);
  }

  if (mismaMoneda && previo.expenses !== actual.expenses) {
    // Que aparezcan expensas donde no había es un cambio; que sigan ausentes, no.
    if (previo.expenses !== null || actual.expenses !== null) {
      agregar("EXPENSES_CHANGED", previo.expenses, actual.expenses);
    }
  }

  const estabaDisponible = previo.availability === "ACTIVE";
  const estaDisponible = actual.availability === "ACTIVE";
  // Sólo se reportan las transiciones desde y hacia ACTIVE. Pasar de UNKNOWN a
  // NOT_SEEN no es que la propiedad se haya ido: es que seguimos sin saber.
  if (estabaDisponible && actual.availability === "NOT_SEEN_LAST_SCRAPE") {
    agregar("BECAME_UNAVAILABLE", previo.availability, actual.availability);
  }
  if (!estabaDisponible && estaDisponible && previo.availability === "NOT_SEEN_LAST_SCRAPE") {
    agregar("RETURNED", previo.availability, actual.availability);
  }

  if (previo.publisherKey !== actual.publisherKey && previo.publisherKey && actual.publisherKey) {
    agregar("PUBLISHER_CHANGED", previo.publisherKey, actual.publisherKey);
  }

  return cambios;
}

/**
 * Recorre una serie completa de observaciones.
 *
 * Ordena por fecha antes de comparar: las observaciones pueden llegar
 * desordenadas de distintas corridas, y compararlas en ese orden produciría
 * subidas y bajadas alternadas que nunca ocurrieron.
 */
export function historialDeCambios(snapshots: readonly ListingSnapshot[]): CambioDetectado[] {
  const ordenados = [...snapshots].sort((a, b) => a.observedAt.localeCompare(b.observedAt));
  const cambios: CambioDetectado[] = [];
  for (let i = 1; i < ordenados.length; i++) {
    cambios.push(...compararSnapshots(ordenados[i - 1], ordenados[i]));
  }
  return cambios;
}

/**
 * ¿Se puede afirmar algo sobre la historia de esta publicación?
 *
 * Con menos de dos observaciones no hay historia: hay una foto. Devolver "sin
 * cambios" en ese caso sería afirmar estabilidad que no observamos.
 */
export function tieneHistoria(snapshots: readonly ListingSnapshot[]): boolean {
  return snapshots.length >= 2;
}

/**
 * Resumen de la serie de precios, o por qué no se puede resumir.
 *
 * `precioInicial` es el del primer snapshot y no "el precio original": si la
 * publicación existía antes de la primera observación, su precio original pudo
 * ser otro y no hay forma de saberlo.
 */
export type ResumenDePrecio =
  | { disponible: false; motivo: string }
  | {
      disponible: true;
      precioInicial: number;
      precioActual: number;
      variacion: number;
      /** Desde cuándo tenemos observaciones. NO es cuándo se publicó. */
      observadaDesde: string;
      cambios: number;
    };

export function resumirPrecio(snapshots: readonly ListingSnapshot[]): ResumenDePrecio {
  if (!tieneHistoria(snapshots)) {
    return { disponible: false, motivo: "hacen falta al menos dos observaciones" };
  }

  const ordenados = [...snapshots].sort((a, b) => a.observedAt.localeCompare(b.observedAt));
  const conPrecio = ordenados.filter((s) => s.price !== null);
  if (conPrecio.length < 2) {
    return { disponible: false, motivo: "no hay suficientes observaciones con precio" };
  }

  const monedas = new Set(conPrecio.map((s) => s.currency));
  if (monedas.size > 1) {
    // Una serie que cambia de moneda no es una serie de precios: es dos.
    return { disponible: false, motivo: "la serie cambia de moneda" };
  }

  const primero = conPrecio[0];
  const ultimo = conPrecio[conPrecio.length - 1];
  const inicial = primero.price as number;
  const actual = ultimo.price as number;

  return {
    disponible: true,
    precioInicial: inicial,
    precioActual: actual,
    variacion: inicial === 0 ? 0 : (actual - inicial) / inicial,
    observadaDesde: primero.observedAt,
    cambios: historialDeCambios(ordenados).filter(
      (c) => c.tipo === "PRICE_INCREASED" || c.tipo === "PRICE_DECREASED",
    ).length,
  };
}
