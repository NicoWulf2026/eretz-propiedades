// Cómo el Quality Gate futuro podría recibir moderación y puntaje.
//
// El Gate actual NO se toca. Hoy funciona con un manifiesto CSV precomputado en
// Blob privado, filtrado en Node, fail-closed. Eso sigue igual, y este archivo
// no lo importa ni lo modifica.
//
// Lo que hace es declarar la forma que tendría la entrada si algún día la
// clasificación se calculara a partir de las señales de este dominio en vez de
// venir opaca desde afuera. Es un contrato, no una implementación: no hay
// ejecución de base, ni cambios en el manifiesto remoto.
//
// Por qué vale la pena escribirlo ahora: hoy el Gate dice `INVALID` sin decir
// por qué. Cuando una inmobiliaria pregunte "¿por qué no se ve mi propiedad?",
// no hay respuesta. Con reason codes la hay.

import type { ModerationDecision, ModerationSignal } from "./moderation";
import type { BandaDeCalidad } from "./quality-score";

/** Las cinco clasificaciones del Gate actual, sin cambios. */
export const GATE_CLASSIFICATIONS = [
  "PUBLICABLE_COMPLETE",
  "PUBLICABLE_INCOMPLETE",
  "REVIEW_REQUIRED",
  "INVALID",
  "SOURCE_UNAVAILABLE",
] as const;
export type GateClassification = (typeof GATE_CLASSIFICATIONS)[number];

/** Las que el Gate deja ver. Idéntico al runtime actual. */
export const GATE_VISIBLES: readonly GateClassification[] = Object.freeze([
  "PUBLICABLE_COMPLETE",
  "PUBLICABLE_INCOMPLETE",
]);

export function gateEsVisible(c: GateClassification): boolean {
  return GATE_VISIBLES.includes(c);
}

/**
 * Lo que un generador de manifiesto podría consumir.
 *
 * `sourceAvailable` va aparte de todo lo demás porque es la única señal que no
 * habla de la publicación sino de nuestra capacidad de verla: una fuente caída
 * no vuelve mala a una propiedad.
 */
export type EntradaDeGate = {
  propertyId: string;
  moderation: ModerationDecision;
  band: BandaDeCalidad;
  overall: number;
  signals: readonly ModerationSignal[];
  sourceAvailable: boolean;
};

export type SalidaDeGate = {
  propertyId: string;
  classification: GateClassification;
  visible: boolean;
  /** Los códigos que llevaron a esa clasificación. Es lo que hoy falta. */
  reasonCodes: string[];
};

/**
 * Traduce señales del dominio a una clasificación del Gate.
 *
 * Función pura y determinista, pensada para correr en el generador de
 * manifiesto —fuera del camino de pedido— y no en el runtime.
 *
 * El orden de las comprobaciones es la lógica: la disponibilidad de la fuente
 * primero, después el bloqueo, después la revisión, y sólo al final se
 * distingue entre completa e incompleta.
 */
export function clasificarParaGate(e: EntradaDeGate): SalidaDeGate {
  const codes = e.signals.map((s) => s.code);
  const salida = (classification: GateClassification, reasonCodes: string[]): SalidaDeGate => ({
    propertyId: e.propertyId,
    classification,
    visible: gateEsVisible(classification),
    reasonCodes,
  });

  if (!e.sourceAvailable) {
    return salida("SOURCE_UNAVAILABLE", ["FUENTE_NO_DISPONIBLE"]);
  }
  if (e.moderation === "REJECT") {
    return salida("INVALID", codes);
  }
  if (e.moderation === "REVIEW") {
    return salida("REVIEW_REQUIRED", codes);
  }
  // ALLOW. La banda decide si se la presenta como completa o incompleta; las
  // dos son visibles, así que esto no oculta nada.
  return salida(e.band === "ALTA" ? "PUBLICABLE_COMPLETE" : "PUBLICABLE_INCOMPLETE", codes);
}

/**
 * ¿Coincide con lo que el Gate vigente dice hoy?
 *
 * Pensada para una comparación futura OLD vs NEW: antes de reemplazar la
 * generación del manifiesto habría que comprobar contra el actual y explicar
 * cada diferencia, no confiar en que el modelo nuevo es mejor.
 */
export function difiereDelActual(nueva: GateClassification, actual: GateClassification): boolean {
  return nueva !== actual;
}
