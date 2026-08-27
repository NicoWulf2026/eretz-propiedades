import "server-only";

// Corre los motores del dominio sobre propiedades reales y agrega el resultado.
//
// ---------------------------------------------------------------------------
// SIN EFECTOS. NI UNO.
// ---------------------------------------------------------------------------
//
// Esta función recibe propiedades y devuelve un resumen. **No devuelve las
// propiedades**, no las muta, y quien la llama descarta el resumen después de
// loguearlo. Es la forma de que sea estructuralmente imposible que el modo
// sombra cambie una respuesta: no hay por dónde.
//
// El tipo lo refuerza: `ResumenShadow` no contiene ninguna propiedad ni nada
// que se le parezca — sólo conteos, códigos y números.
//
// ---------------------------------------------------------------------------
// QUÉ SE LOGUEA Y QUÉ NO
// ---------------------------------------------------------------------------
//
// Un log por propiedad daría 24 líneas por request de listado y ninguna
// legible. Se agrega por request: una línea con la distribución.
//
// NO viaja nada de esto: título, descripción, dirección, teléfono, email,
// nombre de agente, texto de búsqueda, URL de la fuente. Sólo códigos de
// razón, conteos y puntajes.
//
// Los IDs de propiedad SÍ viajan, acotados a tres por código de razón, y con
// un motivo: sin un ejemplo concreto, "este código marca el 20% del catálogo"
// no se puede investigar. Un id de propiedad es público —está en la URL de su
// ficha— y no identifica a ninguna persona.

import { analizarCalidad, type QualityVerdict } from "@/domain/data-quality";
import { moderar, type ModerationDecision } from "@/domain/moderation";
import { calcularScore } from "@/domain/quality-score";
import type { ListingOrigin } from "@/domain/listing";
import type { Property } from "@/types/property";
import { aEntradaDeModeracion, aEntradaDeScore, aPublicacionAnalizable, type FilaCruda } from "./adapter";
import { entraEnMuestra, type ConfiguracionShadow } from "./flag";

/** Cuántos ejemplos se guardan por código de razón. */
export const EJEMPLOS_POR_RAZON = 3;
/** Cuántos códigos de razón entran en el resumen. */
export const RAZONES_EN_RESUMEN = 8;

export type ConteoPorDecision = Record<ModerationDecision, number>;
export type ConteoPorVeredicto = Record<QualityVerdict, number>;

export type RazonAgregada = {
  code: string;
  count: number;
  /** IDs de propiedad, públicos, para poder mirar un caso concreto. */
  ejemplos: string[];
};

export type DistribucionDePuntaje = {
  p10: number;
  p50: number;
  p90: number;
  /** Mediana de cada dimensión: dice cuál arrastra el puntaje hacia abajo. */
  dimensiones: {
    completeness: number;
    consistency: number;
    location: number;
    media: number;
    publisherConfidence: number;
  };
};

export type ResumenShadow = {
  evaluadas: number;
  /** Vistas pero fuera de la muestra. */
  omitidas: number;
  moderacion: ConteoPorDecision;
  calidadDeDatos: ConteoPorVeredicto;
  puntaje: DistribucionDePuntaje | null;
  razones: RazonAgregada[];
  porOrigen: Record<string, { evaluadas: number; review: number; reject: number }>;
};

const percentil = (ordenados: readonly number[], p: number): number => {
  if (ordenados.length === 0) return 0;
  if (ordenados.length === 1) return ordenados[0];
  const pos = (ordenados.length - 1) * p;
  const bajo = Math.floor(pos);
  const alto = Math.ceil(pos);
  if (bajo === alto) return ordenados[bajo];
  return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo);
};

const redondear = (n: number) => Math.round(n * 1000) / 1000;

/** Entrada mínima: la propiedad ya mapeada y las columnas crudas que faltan. */
export type ParaEvaluar = { property: Property; item: FilaCruda };

/**
 * Evalúa un lote y devuelve el agregado.
 *
 * Pura respecto de la entrada: no toca `property` ni `item`. Determinista: el
 * muestreo sale del hash del id, así que dos corridas sobre las mismas
 * propiedades dan el mismo resumen.
 */
export function evaluarLote(
  lote: readonly ParaEvaluar[],
  config: ConfiguracionShadow,
): ResumenShadow | null {
  if (!config.activo || lote.length === 0) return null;

  const moderacion: ConteoPorDecision = { ALLOW: 0, REVIEW: 0, REJECT: 0 };
  const calidadDeDatos: ConteoPorVeredicto = { VALID: 0, SUSPICIOUS: 0, INVALID: 0, QUARANTINE: 0 };
  const porOrigen: ResumenShadow["porOrigen"] = {};
  const razones = new Map<string, { count: number; ejemplos: string[] }>();

  const overalls: number[] = [];
  const dims = { completeness: [] as number[], consistency: [] as number[], location: [] as number[], media: [] as number[], publisherConfidence: [] as number[] };

  let evaluadas = 0;
  let omitidas = 0;

  for (const { property, item } of lote) {
    const id = String(property.id);
    if (!entraEnMuestra(id, config.fraccion)) {
      omitidas += 1;
      continue;
    }
    evaluadas += 1;

    const calidad = analizarCalidad(aPublicacionAnalizable(property, item));
    calidadDeDatos[calidad.verdict] += 1;

    const entradaModeracion = aEntradaDeModeracion(property, item, calidad);
    const decision = moderar(entradaModeracion);
    moderacion[decision.decision] += 1;

    const score = calcularScore(aEntradaDeScore(property, item, calidad));
    overalls.push(score.overall);
    dims.completeness.push(score.completeness.score);
    dims.consistency.push(score.consistency.score);
    dims.location.push(score.location.score);
    dims.media.push(score.media.score);
    dims.publisherConfidence.push(score.publisherConfidence.score);

    const origen: ListingOrigin = entradaModeracion.origin;
    const acumOrigen = (porOrigen[origen] ??= { evaluadas: 0, review: 0, reject: 0 });
    acumOrigen.evaluadas += 1;
    if (decision.decision === "REVIEW") acumOrigen.review += 1;
    if (decision.decision === "REJECT") acumOrigen.reject += 1;

    // Se cuentan las señales de moderación, que ya incluyen las anomalías de
    // calidad traducidas: contar las dos listas duplicaría cada código.
    for (const señal of decision.signals) {
      const acum = (razones.get(señal.code) ?? { count: 0, ejemplos: [] });
      acum.count += 1;
      if (acum.ejemplos.length < EJEMPLOS_POR_RAZON) acum.ejemplos.push(id);
      razones.set(señal.code, acum);
    }
  }

  if (evaluadas === 0) {
    return { evaluadas: 0, omitidas, moderacion, calidadDeDatos, puntaje: null, razones: [], porOrigen };
  }

  const ordenar = (xs: number[]) => [...xs].sort((a, b) => a - b);
  const o = ordenar(overalls);

  return {
    evaluadas,
    omitidas,
    moderacion,
    calidadDeDatos,
    puntaje: {
      p10: redondear(percentil(o, 0.1)),
      p50: redondear(percentil(o, 0.5)),
      p90: redondear(percentil(o, 0.9)),
      dimensiones: {
        completeness: redondear(percentil(ordenar(dims.completeness), 0.5)),
        consistency: redondear(percentil(ordenar(dims.consistency), 0.5)),
        location: redondear(percentil(ordenar(dims.location), 0.5)),
        media: redondear(percentil(ordenar(dims.media), 0.5)),
        publisherConfidence: redondear(percentil(ordenar(dims.publisherConfidence), 0.5)),
      },
    },
    razones: [...razones.entries()]
      .map(([code, v]) => ({ code, count: v.count, ejemplos: v.ejemplos }))
      // Desempate por código para que el resumen sea comparable entre corridas.
      .sort((a, b) => b.count - a.count || a.code.localeCompare(b.code))
      .slice(0, RAZONES_EN_RESUMEN),
    porOrigen,
  };
}

// --- aplanado para el log --------------------------------------------------

/**
 * Convierte el resumen en campos escalares.
 *
 * Hace falta porque `logEvent` **descarta en silencio** todo campo extra que no
 * sea string, número o booleano: un objeto anidado no da error, simplemente no
 * aparece en la línea. Loguear el resumen tal cual habría escrito una línea
 * casi vacía y nadie se habría enterado.
 *
 * Esa restricción del logger es una buena defensa —impide que un objeto
 * anidado cuele datos de una persona sin pasar por el redactor— y por eso se
 * aplana acá en vez de aflojarla allá.
 */
export function aplanarResumen(r: ResumenShadow): Record<string, string | number> {
  const salida: Record<string, string | number> = {
    evaluadas: r.evaluadas,
    omitidas: r.omitidas,
    mod_allow: r.moderacion.ALLOW,
    mod_review: r.moderacion.REVIEW,
    mod_reject: r.moderacion.REJECT,
    dq_valid: r.calidadDeDatos.VALID,
    dq_suspicious: r.calidadDeDatos.SUSPICIOUS,
    dq_invalid: r.calidadDeDatos.INVALID,
    dq_quarantine: r.calidadDeDatos.QUARANTINE,
  };

  if (r.puntaje) {
    salida.score_p10 = r.puntaje.p10;
    salida.score_p50 = r.puntaje.p50;
    salida.score_p90 = r.puntaje.p90;
    salida.dim_completeness = r.puntaje.dimensiones.completeness;
    salida.dim_consistency = r.puntaje.dimensiones.consistency;
    salida.dim_location = r.puntaje.dimensiones.location;
    salida.dim_media = r.puntaje.dimensiones.media;
    salida.dim_publisher = r.puntaje.dimensiones.publisherConfidence;
  }

  // `CODIGO:conteo:id,id,id`. Los ids son públicos —están en la URL de la
  // ficha— y sin un caso concreto un porcentaje no se puede investigar.
  r.razones.forEach((razon, i) => {
    salida[`razon_${i + 1}`] = `${razon.code}:${razon.count}:${razon.ejemplos.join(",")}`;
  });

  for (const [origen, v] of Object.entries(r.porOrigen)) {
    salida[`origen_${origen}`] = `${v.evaluadas}/${v.review}/${v.reject}`;
  }

  return salida;
}

// --- umbrales de diagnóstico -----------------------------------------------

/**
 * Umbrales para avisar que las reglas podrían estar mal calibradas.
 *
 * Son diagnósticos, NO enforcement: superarlos no oculta nada ni cambia nada,
 * sólo escribe un `warn` en el log. Los números salen de una idea simple: si
 * una regla marca a una porción grande del catálogo real, lo más probable es
 * que el problema esté en la regla y no en el catálogo.
 */
export const UMBRALES_DIAGNOSTICOS = Object.freeze({
  /** Un rechazo sobre lo scrapeado esconde inventario: casi nunca debería pasar. */
  fraccionRejectMaxima: 0.01,
  /** Si una de cada cuatro va a revisión, la cola es impracticable. */
  fraccionReviewMaxima: 0.25,
  /** Un solo código marcando más de la mitad casi siempre es un bug de regla. */
  fraccionPorRazonMaxima: 0.5,
});

export type Advertencia = { code: string; detalle: string };

export function advertencias(r: ResumenShadow): Advertencia[] {
  const out: Advertencia[] = [];
  if (r.evaluadas === 0) return out;

  const frac = (n: number) => n / r.evaluadas;

  if (frac(r.moderacion.REJECT) > UMBRALES_DIAGNOSTICOS.fraccionRejectMaxima) {
    out.push({
      code: "REJECT_ALTO",
      detalle: `${Math.round(frac(r.moderacion.REJECT) * 100)}% rechazadas`,
    });
  }
  if (frac(r.moderacion.REVIEW) > UMBRALES_DIAGNOSTICOS.fraccionReviewMaxima) {
    out.push({
      code: "REVIEW_ALTO",
      detalle: `${Math.round(frac(r.moderacion.REVIEW) * 100)}% a revisión`,
    });
  }
  for (const razon of r.razones) {
    if (frac(razon.count) > UMBRALES_DIAGNOSTICOS.fraccionPorRazonMaxima) {
      out.push({
        code: "RAZON_DOMINANTE",
        detalle: `${razon.code} en el ${Math.round(frac(razon.count) * 100)}%`,
      });
    }
  }
  return out;
}
