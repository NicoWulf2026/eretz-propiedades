// Contratos de procedencia geográfica y normalización de texto de ubicación.
//
// NO reemplaza `lib/geo-confidence.ts`. Ese módulo clasifica la confianza en
// cuatro niveles (`high` / `approximate` / `doubtful` / `none`), tiene sus
// etiquetas para la UI y funciona; se preserva entero y se importa desde acá.
//
// Lo que falta y se agrega:
//
//   1. PROCEDENCIA. Hoy una coordenada es un par de números sin historia. No se
//      puede responder de dónde salió, cuándo, con qué precisión, ni si alguien
//      la corrigió a mano. Sin eso no se puede re-geocodificar selectivamente
//      —habría que rehacer las 65.033— ni confiar más en unas que en otras.
//
//   2. NORMALIZACIÓN DE TEXTO, sólo la mecánica.
//
// ---------------------------------------------------------------------------
// NORMALIZAR NO ES ADIVINAR
// ---------------------------------------------------------------------------
//
// Se normaliza lo mecánico: espacios, mayúsculas, puntuación. Eso no cambia el
// significado de nada.
//
// NO se traducen alias de ciudad ni de barrio. La base tiene una tabla
// (`city_normalization_rules`) con reglas construidas contra datos reales, y
// escribir acá un diccionario paralelo garantiza que los dos se contradigan.
//
// Y NO se convierte un barrio en coordenadas. "Fisherton" no es un punto: es
// un polígono de varios kilómetros. Poner el centroide y presentarlo como
// ubicación sería inventar una precisión que no existe — exactamente lo que la
// clasificación de confianza existe para evitar.
//
// Las provincias sí se resuelven, porque son una lista oficial y cerrada de 24
// jurisdicciones. Eso es un hecho, no una inferencia.

import type { LocationConfidence } from "@/types/property";

// --- procedencia -----------------------------------------------------------

/** De dónde salió la ubicación. */
export const GEO_SOURCES = [
  /** La fuente publicaba coordenadas. */
  "SOURCE_COORDINATES",
  /** Se geocodificó un texto de dirección. */
  "GEOCODED",
  /** Una persona la corrigió a mano. */
  "MANUAL",
  /** Se dedujo de otra publicación de la misma propiedad. */
  "INFERRED_FROM_ENTITY",
] as const;
export type GeoSource = (typeof GEO_SOURCES)[number];

/**
 * A qué resolvió la ubicación. Distinto de la confianza.
 *
 * La precisión dice **a qué nivel se resolvió**; la confianza, **cuánto le
 * creemos**. Se pueden combinar de las cuatro formas: una dirección con altura
 * resuelta por un geocoder malo es precisa y poco confiable; un centroide de
 * ciudad bien identificado es impreciso y confiable.
 */
export const GEO_PRECISIONS = [
  "ROOFTOP",
  "STREET_NUMBER",
  "STREET",
  "NEIGHBORHOOD",
  "LOCALITY",
  "UNKNOWN",
] as const;
export type GeoPrecision = (typeof GEO_PRECISIONS)[number];

/**
 * ¿Esta precisión alcanza para mostrar un punto en el mapa como si fuera la
 * propiedad?
 *
 * Un centroide de barrio o de ciudad **no**: el punto caería a cientos de
 * metros o kilómetros del inmueble, y quien lo mira lo lee como su dirección.
 * Esas ubicaciones pueden mostrarse, pero como área y nunca como punto exacto.
 */
export function precisionPermitePunto(p: GeoPrecision): boolean {
  return p === "ROOFTOP" || p === "STREET_NUMBER" || p === "STREET";
}

export type GeoEvidence = {
  /** Qué texto se usó para resolverla. */
  inputText: string | null;
  /** Qué devolvió el proveedor, resumido. Nunca la respuesta completa. */
  matchedText: string | null;
};

/**
 * La historia de una coordenada.
 *
 * `manualOverride` es un booleano aparte y no una `source` más porque puede
 * coexistir: una coordenada geocodificada Y corregida a mano después conserva
 * de dónde vino originalmente.
 */
export type GeoProvenance = {
  source: GeoSource;
  /** Identificador del proveedor. `null` si no intervino ninguno. */
  provider: string | null;
  geocodedAt: string | null;
  precision: GeoPrecision;
  confidence: LocationConfidence;
  manualOverride: boolean;
  evidence: GeoEvidence | null;
};

/** Procedencia de lo que hay hoy: coordenadas sin historia registrada. */
export const PROCEDENCIA_DESCONOCIDA: Readonly<GeoProvenance> = Object.freeze({
  source: "SOURCE_COORDINATES",
  provider: null,
  geocodedAt: null,
  precision: "UNKNOWN",
  confidence: "none",
  manualOverride: false,
  evidence: null,
});

export function problemasDeProcedencia(p: GeoProvenance): string[] {
  const problemas: string[] = [];
  if (p.source === "GEOCODED" && !p.provider) {
    problemas.push("una ubicación geocodificada tiene que decir con qué proveedor");
  }
  if (p.source === "GEOCODED" && !p.geocodedAt) {
    problemas.push("una ubicación geocodificada tiene que decir cuándo");
  }
  if (p.source === "MANUAL" && !p.manualOverride) {
    problemas.push("una corrección manual tiene que quedar marcada como tal");
  }
  if (p.confidence === "none" && p.precision !== "UNKNOWN") {
    problemas.push("sin confianza no puede haber precisión declarada");
  }
  return problemas;
}

// --- normalización mecánica ------------------------------------------------

/**
 * Limpieza que no cambia el significado: espacios, comillas raras, guiones
 * repetidos. Preserva acentos y mayúsculas internas.
 */
export function limpiarTexto(v: string | null | undefined): string | null {
  if (typeof v !== "string") return null;
  const limpio = v
    .replace(/[‘’“”]/g, "'")
    .replace(/\s+/g, " ")
    .replace(/\s*-\s*/g, "-")
    .replace(/-{2,}/g, "-")
    .trim()
    .replace(/^[,;.\-]+|[,;.\-]+$/g, "")
    .trim();
  return limpio || null;
}

/** Clave de comparación: sin acentos, sin puntuación, en minúsculas. */
export function claveDeComparacion(v: string | null | undefined): string {
  if (typeof v !== "string") return "";
  return v
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/**
 * Capitalización para mostrar, respetando las partículas del castellano.
 *
 * "SAN MIGUEL DE TUCUMAN" no se muestra como "San Miguel De Tucuman".
 */
const PARTICULAS = new Set(["de", "del", "la", "las", "los", "el", "y", "en"]);

export function capitalizarUbicacion(v: string | null | undefined): string | null {
  const limpio = limpiarTexto(v);
  if (!limpio) return null;
  return limpio
    .split(" ")
    .map((palabra, i) => {
      const bajo = palabra.toLowerCase();
      if (i > 0 && PARTICULAS.has(bajo)) return bajo;
      return bajo.charAt(0).toUpperCase() + bajo.slice(1);
    })
    .join(" ");
}

// --- provincias: lista oficial y cerrada -----------------------------------

export const PROVINCIAS = [
  "Buenos Aires",
  "Ciudad Autónoma de Buenos Aires",
  "Catamarca",
  "Chaco",
  "Chubut",
  "Córdoba",
  "Corrientes",
  "Entre Ríos",
  "Formosa",
  "Jujuy",
  "La Pampa",
  "La Rioja",
  "Mendoza",
  "Misiones",
  "Neuquén",
  "Río Negro",
  "Salta",
  "San Juan",
  "San Luis",
  "Santa Cruz",
  "Santa Fe",
  "Santiago del Estero",
  "Tierra del Fuego",
  "Tucumán",
] as const;
export type Provincia = (typeof PROVINCIAS)[number];

/**
 * Variantes reconocidas. Son denominaciones oficiales o de uso universal, no
 * un diccionario de errores de tipeo.
 */
const VARIANTES: Readonly<Record<string, Provincia>> = Object.freeze({
  // Las claves ya vienen pasadas por `claveDeComparacion`: minúsculas, sin
  // acentos y con espacios simples.
  "caba": "Ciudad Autónoma de Buenos Aires",
  "capital federal": "Ciudad Autónoma de Buenos Aires",
  "ciudad de buenos aires": "Ciudad Autónoma de Buenos Aires",
  "ciudad autonoma de buenos aires": "Ciudad Autónoma de Buenos Aires",
  "provincia de buenos aires": "Buenos Aires",
  "tierra del fuego antartida e islas del atlantico sur": "Tierra del Fuego",
});

export type ResolucionDeProvincia =
  | { estado: "RESUELTA"; provincia: Provincia }
  | { estado: "AMBIGUA"; candidatas: Provincia[]; motivo: string }
  | { estado: "DESCONOCIDA" };

/**
 * Resuelve un texto a una provincia oficial.
 *
 * El caso que importa es "Buenos Aires" a secas: puede ser la provincia o la
 * Ciudad, y son jurisdicciones distintas. **No se resuelve en silencio.**
 * Elegir una haría que propiedades de Bahía Blanca y de Palermo terminaran en
 * el mismo cajón, y nadie lo notaría hasta ver una estadística absurda.
 */
export function resolverProvincia(texto: string | null | undefined): ResolucionDeProvincia {
  const clave = claveDeComparacion(texto);
  if (!clave) return { estado: "DESCONOCIDA" };

  if (clave === "buenos aires") {
    return {
      estado: "AMBIGUA",
      candidatas: ["Buenos Aires", "Ciudad Autónoma de Buenos Aires"],
      motivo: "puede ser la provincia o la Ciudad Autónoma, que son jurisdicciones distintas",
    };
  }

  const variante = VARIANTES[clave];
  if (variante) return { estado: "RESUELTA", provincia: variante };

  const exacta = PROVINCIAS.find((p) => claveDeComparacion(p) === clave);
  if (exacta) return { estado: "RESUELTA", provincia: exacta };

  return { estado: "DESCONOCIDA" };
}

// --- presentación honesta --------------------------------------------------

/**
 * Cómo mostrar una ubicación según su confianza.
 *
 * `lib/geo-confidence.ts` ya tiene `locationConfidenceLabel` y
 * `locationConfidenceDescription` para el texto, y no se duplican. Lo que falta
 * y se agrega es la decisión de **presentación**: qué se puede dibujar en el
 * mapa y con qué forma.
 */
export type PresentacionGeografica = {
  /** Un punto en el mapa. Sólo si la ubicación lo justifica. */
  puntoExacto: boolean;
  /** Un área. Para lo aproximado, en vez de un punto que miente. */
  area: boolean;
  /** Ni punto ni área: no aparece en el mapa. */
  fueraDelMapa: boolean;
};

export function presentacionDe(
  confidence: LocationConfidence,
  precision: GeoPrecision = "UNKNOWN",
): PresentacionGeografica {
  if (confidence === "none") return { puntoExacto: false, area: false, fueraDelMapa: true };

  // Alta confianza no alcanza sola: si lo que se resolvió fue el centroide de
  // una ciudad, el punto está a kilómetros por más seguros que estemos de la
  // ciudad. Hacen falta las dos cosas.
  if (confidence === "high" && precisionPermitePunto(precision)) {
    return { puntoExacto: true, area: false, fueraDelMapa: false };
  }
  return { puntoExacto: false, area: true, fueraDelMapa: false };
}
