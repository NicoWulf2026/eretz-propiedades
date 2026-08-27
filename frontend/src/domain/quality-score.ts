// Puntaje de calidad de una publicación, explicable dimensión por dimensión.
//
// ---------------------------------------------------------------------------
// ESTO NO ES RANKING. REGLA ABSOLUTA.
// ---------------------------------------------------------------------------
//
// El score NO ordena resultados de búsqueda. La tentación de usarlo es fuerte
// —"lo más completo primero" suena razonable— y es una mala idea por dos
// motivos concretos:
//
//   1. Premiaría a quien tiene mejor CMS, no a quien tiene mejor propiedad. Una
//      inmobiliaria chica con fotos de celular quedaría sistemáticamente última
//      aunque su departamento sea exactamente el que la persona busca.
//
//   2. Convierte el score en un objetivo. En cuanto ordenar dependa de él,
//      aparecen descripciones infladas y campos rellenados con cualquier cosa
//      para subir, y el score deja de medir calidad para medir quién entendió
//      la fórmula.
//
// Para qué SÍ sirve: operaciones de datos, moderación, priorizar qué corregir,
// detectar fuentes que scrapean mal, y alimentar el Quality Gate futuro.
//
//   QUALITY ≠ POPULARITY ≠ RANKING
//
// Sin modelo de machine learning y sin pesos aprendidos: los pesos están
// escritos, se leen y se discuten.

import type { QualityReport } from "./data-quality";
import type { LocationConfidence } from "@/types/property";

/** Una dimensión evaluada, con su porqué. */
export type SubScore = {
  /** De 0 a 1. */
  score: number;
  /** Qué sumó y qué restó, legible. */
  reasons: string[];
};

export type QualityScore = {
  /** De 0 a 1, combinación ponderada de las dimensiones. */
  overall: number;
  completeness: SubScore;
  consistency: SubScore;
  location: SubScore;
  media: SubScore;
  publisherConfidence: SubScore;
  /** Resumen de una línea. */
  explanation: string;
};

/**
 * Pesos de cada dimensión. Suman 1.
 *
 * `consistency` pesa más que `completeness` a propósito: un dato que se
 * contradice es peor que un dato ausente. Una publicación sin superficie
 * declarada es incompleta; una que dice que la cubierta supera a la total está
 * mal, y eso desconfía del resto de sus datos.
 */
export const PESOS = Object.freeze({
  completeness: 0.25,
  consistency: 0.3,
  location: 0.2,
  media: 0.15,
  publisherConfidence: 0.1,
});

export type EntradaDeScore = {
  quality: QualityReport;
  locationConfidence: LocationConfidence;
  imageCount: number;
  hasDescription: boolean;
  descriptionLength: number;
  hasPrice: boolean;
  hasContact: boolean;
  /** Atributos físicos presentes, de los que se consideran fundamentales. */
  presentAttributes: {
    propertyType: boolean;
    operation: boolean;
    totalArea: boolean;
    rooms: boolean;
    bedrooms: boolean;
    bathrooms: boolean;
  };
  publisherIdentified: boolean;
  publisherVerified: boolean | null;
};

const acotar = (n: number) => Math.max(0, Math.min(1, n));

/**
 * Completitud: cuántos de los campos que importan están.
 *
 * No se cuentan todos los campos por igual. Operación y tipo son
 * imprescindibles —sin ellos la publicación no se puede ni filtrar—; el resto
 * suma de forma pareja.
 */
function evaluarCompletitud(e: EntradaDeScore): SubScore {
  const reasons: string[] = [];
  const a = e.presentAttributes;

  // Sin operación o sin tipo, la publicación es casi inutilizable.
  if (!a.operation || !a.propertyType) {
    reasons.push("faltan operación o tipo de propiedad, que son imprescindibles");
    return { score: 0, reasons };
  }
  reasons.push("tiene operación y tipo");

  const opcionales: Array<[string, boolean]> = [
    ["precio", e.hasPrice],
    ["superficie", a.totalArea],
    ["ambientes", a.rooms],
    ["dormitorios", a.bedrooms],
    ["baños", a.bathrooms],
    ["descripción", e.hasDescription],
    ["contacto", e.hasContact],
  ];
  const presentes = opcionales.filter(([, hay]) => hay);
  const faltantes = opcionales.filter(([, hay]) => !hay).map(([n]) => n);

  if (faltantes.length) reasons.push(`faltan: ${faltantes.join(", ")}`);
  else reasons.push("tiene todos los datos habituales");

  return { score: acotar(presentes.length / opcionales.length), reasons };
}

/**
 * Coherencia: penaliza contradicciones, y menos los valores atípicos.
 *
 * Una incoherencia hunde el puntaje; una rareza lo baja un poco. Es la misma
 * distinción de `data-quality`, y mantenerla acá evita que una publicación
 * legítimamente inusual quede indistinguible de una con datos rotos.
 */
function evaluarCoherencia(e: EntradaDeScore): SubScore {
  const reasons: string[] = [];
  const invalidas = e.quality.anomalies.filter((a) => a.severity === "INVALID");
  const sospechosas = e.quality.anomalies.filter((a) => a.severity === "SUSPICIOUS");

  if (invalidas.length === 0 && sospechosas.length === 0) {
    return { score: 1, reasons: ["sin contradicciones ni valores atípicos"] };
  }

  if (invalidas.length) {
    reasons.push(`contradicciones: ${invalidas.map((a) => a.code).join(", ")}`);
  }
  if (sospechosas.length) {
    reasons.push(`valores atípicos: ${sospechosas.map((a) => a.code).join(", ")}`);
  }

  // Cada contradicción cuesta 0,5; cada rareza 0,1. Dos contradicciones dejan
  // el puntaje en cero.
  const penalizacion = invalidas.length * 0.5 + sospechosas.length * 0.1;
  return { score: acotar(1 - penalizacion), reasons };
}

/** Ubicación: reusa la semántica de cuatro niveles que ya existe. */
function evaluarUbicacion(e: EntradaDeScore): SubScore {
  const tabla: Record<LocationConfidence, [number, string]> = {
    high: [1, "ubicación precisa"],
    approximate: [0.6, "ubicación aproximada"],
    doubtful: [0.3, "ubicación dudosa"],
    none: [0, "sin ubicación en el mapa"],
  };
  const [score, motivo] = tabla[e.locationConfidence];
  return { score, reasons: [motivo] };
}

/**
 * Fotos y descripción.
 *
 * El puntaje por fotos satura pronto: la diferencia entre 0 y 3 es enorme,
 * entre 12 y 20 no le cambia la vida a nadie. Premiar linealmente incentivaría
 * subir treinta fotos del mismo ambiente.
 */
export const FOTOS_PARA_PUNTAJE_PLENO = 6;
export const DESCRIPCION_PARA_PUNTAJE_PLENO = 200;

function evaluarMedia(e: EntradaDeScore): SubScore {
  const reasons: string[] = [];

  const fotos = acotar(e.imageCount / FOTOS_PARA_PUNTAJE_PLENO);
  if (e.imageCount === 0) reasons.push("sin fotos");
  else if (e.imageCount >= FOTOS_PARA_PUNTAJE_PLENO) reasons.push(`${e.imageCount} fotos`);
  else reasons.push(`${e.imageCount} fotos, pocas para mostrar la propiedad`);

  const texto = acotar(e.descriptionLength / DESCRIPCION_PARA_PUNTAJE_PLENO);
  if (!e.hasDescription) reasons.push("sin descripción");
  else if (e.descriptionLength < DESCRIPCION_PARA_PUNTAJE_PLENO) reasons.push("descripción breve");

  // Las fotos pesan el doble que el texto: en inmuebles se mira antes de leer.
  return { score: acotar((fotos * 2 + texto) / 3), reasons };
}

/**
 * Confianza en el publicador.
 *
 * Es la dimensión de menor peso, y a propósito: castigar fuerte al publicador
 * no identificado penalizaría a casi todo el catálogo actual por una carencia
 * nuestra —no sabemos quién es— y no por un defecto de la publicación.
 *
 * `publisherVerified` puede ser `null`, que no es lo mismo que `false`: no
 * evaluada no se penaliza como si hubiera fallado una verificación.
 */
function evaluarPublicador(e: EntradaDeScore): SubScore {
  if (!e.publisherIdentified) {
    return { score: 0.3, reasons: ["publicador no identificado"] };
  }
  if (e.publisherVerified === true) {
    return { score: 1, reasons: ["publicador verificado"] };
  }
  if (e.publisherVerified === false) {
    return { score: 0.6, reasons: ["publicador identificado, sin verificar"] };
  }
  return { score: 0.6, reasons: ["publicador identificado; verificación no evaluada"] };
}

/**
 * Calcula el puntaje completo.
 *
 * Nunca devuelve sólo un número: las dimensiones y sus motivos viajan siempre,
 * porque un puntaje sin explicación no se puede discutir ni accionar.
 */
export function calcularScore(e: EntradaDeScore): QualityScore {
  const completeness = evaluarCompletitud(e);
  const consistency = evaluarCoherencia(e);
  const location = evaluarUbicacion(e);
  const media = evaluarMedia(e);
  const publisherConfidence = evaluarPublicador(e);

  const overall =
    completeness.score * PESOS.completeness +
    consistency.score * PESOS.consistency +
    location.score * PESOS.location +
    media.score * PESOS.media +
    publisherConfidence.score * PESOS.publisherConfidence;

  // La dimensión más floja es la que hay que arreglar primero: es lo accionable.
  const dimensiones: Array<[string, SubScore]> = [
    ["completitud", completeness],
    ["coherencia", consistency],
    ["ubicación", location],
    ["fotos y texto", media],
    ["publicador", publisherConfidence],
  ];
  const peor = dimensiones.reduce((a, b) => (b[1].score < a[1].score ? b : a));

  return {
    overall: acotar(overall),
    completeness,
    consistency,
    location,
    media,
    publisherConfidence,
    explanation:
      peor[1].score >= 0.9
        ? "todas las dimensiones están bien"
        : `lo más flojo es ${peor[0]}: ${peor[1].reasons[0]}`,
  };
}

/**
 * Bandas para operaciones. NO para ordenar resultados.
 *
 * Existen para poder decir "revisar las 4.000 publicaciones en banda BAJA de
 * esta fuente" sin que cada consulta invente sus propios cortes.
 */
export const BANDAS = ["ALTA", "MEDIA", "BAJA"] as const;
export type BandaDeCalidad = (typeof BANDAS)[number];

export function bandaDeScore(overall: number): BandaDeCalidad {
  if (overall >= 0.75) return "ALTA";
  if (overall >= 0.45) return "MEDIA";
  return "BAJA";
}
