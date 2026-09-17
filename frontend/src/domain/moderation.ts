// Motor de moderación: ¿esta publicación se muestra, se revisa o se bloquea?
//
// Determinista y explicable. Sin IA, sin proveedor externo, sin heurística
// opaca: toda decisión viene con las señales que la produjeron y un texto que
// una persona puede leer y discutir.
//
// ---------------------------------------------------------------------------
// MODERACIÓN NO ES CALIDAD DE DATOS
// ---------------------------------------------------------------------------
//
// `data-quality.ts` responde "¿este dato está bien?". Esto responde "¿qué
// hacemos con esta publicación?". Son preguntas distintas y la segunda depende
// de cosas que la primera no mira: de dónde vino, quién publica, si es un
// duplicado confirmado.
//
// Una publicación puede tener datos perfectos y ser spam. Una puede tener la
// superficie mal cargada y ser un departamento real que conviene mostrar.
//
// ---------------------------------------------------------------------------
// LA MISMA SEÑAL, DISTINTA ACCIÓN SEGÚN EL ORIGEN
// ---------------------------------------------------------------------------
//
// Es la decisión central de este módulo, y no estaba en el encargo.
//
// Rechazar una carga MANUAL cuesta poco: la persona ve el error, lo corrige y
// vuelve a enviar. El costo es un minuto suyo.
//
// Rechazar una SCRAPEADA cuesta mucho y de forma invisible: esa propiedad
// existe en el mundo real y está publicada en el sitio de la inmobiliaria.
// Bloquearla no la hace desaparecer, sólo hace que ERETZ no la tenga. Nadie se
// entera de lo que falta. Y son 257.073 publicaciones: un criterio apenas
// estricto de más borra miles de propiedades reales del catálogo.
//
// Por eso el mismo conjunto de señales da REJECT en manual y REVIEW en
// scrapeado. No es indulgencia: es que el error caro apunta en direcciones
// opuestas según quién cargó el dato.

import type { QualityReport } from "./data-quality";
import type { ListingOrigin } from "./listing";

export const MODERATION_DECISIONS = ["ALLOW", "REVIEW", "REJECT"] as const;
export type ModerationDecision = (typeof MODERATION_DECISIONS)[number];

export const SIGNAL_SEVERITIES = ["LOW", "MEDIUM", "HIGH"] as const;
export type SignalSeverity = (typeof SIGNAL_SEVERITIES)[number];

export type ModerationSignal = {
  code: string;
  severity: SignalSeverity;
  /** Qué se observó, concreto y citable. */
  evidence: string;
  /** Por qué eso importa, en castellano. */
  explanation: string;
};

/** Confianza de duplicado, con el vocabulario del scorer existente. */
export type DuplicateSignal = "CONFIRMED" | "HIGH_CONFIDENCE" | "POSSIBLE_MATCH" | "NO_MATCH";

export type PublisherSignal = "IDENTIFIED" | "UNIDENTIFIED";

export type EntradaDeModeracion = {
  origin: ListingOrigin;
  publisher: PublisherSignal;
  /** Informe de `analizarCalidad`. Es una entrada, no la decisión. */
  quality: QualityReport;
  duplicate: DuplicateSignal;
  title: string | null;
  description: string | null;
  /** Host de la fuente, para distinguir enlaces propios de ajenos. */
  sourceHost: string | null;
  hasContact: boolean;
  imageCount: number;
};

export type ModerationResult = {
  decision: ModerationDecision;
  signals: ModerationSignal[];
  /** Resumen legible de por qué se decidió así. */
  explanation: string;
};

// --- detección de spam, determinista ---------------------------------------

/**
 * Umbrales de las reglas de texto.
 *
 * Conservadores a propósito. Cada falso positivo acá esconde una publicación
 * legítima, y la escritura comercial inmobiliaria es naturalmente enfática:
 * mayúsculas, signos de exclamación y repetición de la zona son estilo, no
 * spam. Las reglas apuntan a lo que ninguna redacción normal produce.
 */
export const UMBRALES_TEXTO = Object.freeze({
  /** Fracción de letras en mayúscula que delata GRITAR. */
  fraccionMayusculas: 0.7,
  /** A partir de cuántos caracteres se evalúan las mayúsculas. */
  largoMinimoParaMayusculas: 40,
  /** Mismo carácter repetido seguido. */
  repeticionDeCaracter: 6,
  /** Veces que una misma palabra larga se repite: relleno de palabras clave. */
  repeticionDePalabra: 8,
  /** Dominios externos distintos enlazados en la descripción. */
  dominiosExternos: 2,
  /** Descripción por debajo de esto: no aporta nada. */
  descripcionMinima: 20,
});

const sinAcentos = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");

/** Grita: mayoría abrumadora de mayúsculas en un texto largo. */
function detectaGritos(texto: string): ModerationSignal | null {
  if (texto.length < UMBRALES_TEXTO.largoMinimoParaMayusculas) return null;
  const letras = texto.replace(/[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]/g, "");
  if (letras.length < UMBRALES_TEXTO.largoMinimoParaMayusculas) return null;
  const mayus = letras.replace(/[^A-ZÁÉÍÓÚÜÑ]/g, "").length;
  const fraccion = mayus / letras.length;
  if (fraccion < UMBRALES_TEXTO.fraccionMayusculas) return null;
  return {
    code: "TEXTO_EN_MAYUSCULAS",
    severity: "LOW",
    evidence: `${Math.round(fraccion * 100)}% del texto en mayúsculas`,
    explanation: "escribir todo en mayúsculas es típico de publicaciones de baja calidad",
  };
}

/** Caracteres repetidos: `!!!!!!!!` o `aaaaaaa`. */
function detectaRepeticion(texto: string): ModerationSignal | null {
  const re = new RegExp(`(.)\\1{${UMBRALES_TEXTO.repeticionDeCaracter - 1},}`);
  const m = re.exec(texto);
  if (!m) return null;
  return {
    code: "CARACTERES_REPETIDOS",
    severity: "LOW",
    evidence: `secuencia "${m[0].slice(0, 10)}"`,
    explanation: "la repetición de caracteres no aporta información",
  };
}

/** Relleno de palabras clave: la misma palabra larga muchas veces. */
function detectaRelleno(texto: string): ModerationSignal | null {
  const palabras = sinAcentos(texto.toLowerCase()).match(/[a-z]{5,}/g) ?? [];
  const cuenta = new Map<string, number>();
  for (const p of palabras) cuenta.set(p, (cuenta.get(p) ?? 0) + 1);
  for (const [palabra, n] of cuenta) {
    if (n >= UMBRALES_TEXTO.repeticionDePalabra) {
      return {
        code: "RELLENO_DE_PALABRAS",
        severity: "MEDIUM",
        evidence: `"${palabra}" aparece ${n} veces`,
        explanation: "repetir una palabra clave muchas veces es una técnica de posicionamiento, no descripción",
      };
    }
  }
  return null;
}

/**
 * Enlaces a dominios ajenos.
 *
 * Los enlaces al sitio de la propia inmobiliaria son normales y no cuentan: por
 * eso hace falta `sourceHost`. Sin él no se puede distinguir el enlace propio
 * del ajeno, y marcar todos convertiría cualquier ficha con su propia URL en
 * sospechosa.
 */
function detectaEnlacesExternos(texto: string, sourceHost: string | null): ModerationSignal | null {
  const urls = texto.match(/https?:\/\/[^\s<>"']+/gi) ?? [];
  const propio = (sourceHost ?? "").replace(/^www\./, "").toLowerCase();
  const ajenos = new Set<string>();

  for (const u of urls) {
    const m = /^https?:\/\/([^/?#:]+)/i.exec(u);
    if (!m) continue;
    const host = m[1].replace(/^www\./, "").toLowerCase();
    if (propio && (host === propio || host.endsWith(`.${propio}`))) continue;
    ajenos.add(host);
  }

  if (ajenos.size < UMBRALES_TEXTO.dominiosExternos) return null;
  return {
    code: "ENLACES_EXTERNOS",
    severity: "MEDIUM",
    evidence: `${ajenos.size} dominios ajenos: ${[...ajenos].slice(0, 3).join(", ")}`,
    explanation: "varios enlaces a sitios ajenos suelen indicar promoción de terceros",
  };
}

/** Descripción que no dice nada, o que sólo repite el título. */
function detectaDescripcionVacia(
  titulo: string | null,
  descripcion: string | null,
): ModerationSignal | null {
  const d = (descripcion ?? "").trim();
  if (!d) return null;

  if (d.length < UMBRALES_TEXTO.descripcionMinima) {
    return {
      code: "DESCRIPCION_INSUFICIENTE",
      severity: "LOW",
      evidence: `${d.length} caracteres`,
      explanation: "una descripción demasiado breve no ayuda a decidir",
    };
  }

  const norm = (s: string) => sinAcentos(s.toLowerCase()).replace(/[^a-z0-9]+/g, " ").trim();
  if (titulo && norm(d) === norm(titulo)) {
    return {
      code: "DESCRIPCION_REPITE_TITULO",
      severity: "LOW",
      evidence: "la descripción es idéntica al título",
      explanation: "no agrega información sobre la propiedad",
    };
  }
  return null;
}

/** Todas las señales de texto de una publicación. */
export function analizarTexto(
  titulo: string | null,
  descripcion: string | null,
  sourceHost: string | null,
): ModerationSignal[] {
  const texto = `${titulo ?? ""}\n${descripcion ?? ""}`.trim();
  if (!texto) return [];

  return [
    detectaGritos(texto),
    detectaRepeticion(texto),
    detectaRelleno(texto),
    detectaEnlacesExternos(texto, sourceHost),
    detectaDescripcionVacia(titulo, descripcion),
  ].filter((s): s is ModerationSignal => s !== null);
}

// --- señales estructurales -------------------------------------------------

function senalesEstructurales(e: EntradaDeModeracion): ModerationSignal[] {
  const s: ModerationSignal[] = [];

  if (e.duplicate === "CONFIRMED") {
    s.push({
      code: "DUPLICADO_CONFIRMADO",
      severity: "HIGH",
      evidence: "coincide con otra publicación ya existente",
      explanation: "mostrar dos veces la misma propiedad ensucia el catálogo y las métricas",
    });
  } else if (e.duplicate === "HIGH_CONFIDENCE") {
    s.push({
      code: "DUPLICADO_PROBABLE",
      severity: "MEDIUM",
      evidence: "coincide con alta confianza con otra publicación",
      explanation: "conviene agrupar antes de mostrar por separado",
    });
  } else if (e.duplicate === "POSSIBLE_MATCH") {
    // No es señal de moderación: es ruido esperable. Se anota con severidad
    // baja para que quede en la evidencia, sin peso en la decisión.
    s.push({
      code: "DUPLICADO_POSIBLE",
      severity: "LOW",
      evidence: "se parece a otra publicación",
      explanation: "no alcanza para agrupar ni para bloquear; queda anotado",
    });
  }

  if (!e.hasContact) {
    s.push({
      code: "SIN_CONTACTO",
      severity: "MEDIUM",
      evidence: "no hay teléfono ni email",
      explanation: "una publicación que nadie puede contactar no le sirve a nadie",
    });
  }

  if (e.imageCount === 0) {
    s.push({
      code: "SIN_IMAGENES",
      severity: "LOW",
      evidence: "no tiene fotos",
      explanation: "reduce mucho su utilidad, pero no la vuelve falsa",
    });
  }

  return s;
}

/** Traduce el informe de calidad a señales de moderación. */
function senalesDeCalidad(q: QualityReport): ModerationSignal[] {
  return q.anomalies
    // Los campos ausentes ya se cubren con señales estructurales propias.
    .filter((a) => a.severity !== "INFO")
    .map((a) => ({
      code: a.code,
      severity: a.severity === "INVALID" ? ("HIGH" as const) : ("MEDIUM" as const),
      evidence: a.detail,
      explanation:
        a.severity === "INVALID"
          ? "el dato se contradice a sí mismo"
          : "es un valor atípico: raro, no imposible",
    }));
}

// --- decisión --------------------------------------------------------------

/**
 * Cuántas señales MEDIUM equivalen a una HIGH para decidir.
 *
 * Existe para que "muchas cosas raras a la vez" pese, sin que una sola alcance.
 */
export const MEDIAS_PARA_ESCALAR = 3;

/**
 * Modera una publicación.
 *
 * El bloqueo directo se reserva a lo que es un problema con independencia del
 * origen. Todo lo demás escala según lo que cueste equivocarse: en una carga
 * manual se rechaza, en una scrapeada se manda a revisión.
 */
export function moderar(e: EntradaDeModeracion): ModerationResult {
  const signals = [
    ...senalesDeCalidad(e.quality),
    ...senalesEstructurales(e),
    ...analizarTexto(e.title, e.description, e.sourceHost),
  ];

  const altas = signals.filter((s) => s.severity === "HIGH");
  const medias = signals.filter((s) => s.severity === "MEDIUM");

  const decidir = (): { decision: ModerationDecision; explanation: string } => {
    // Un duplicado confirmado se bloquea venga de donde venga: no se pierde la
    // propiedad, ya está en el catálogo bajo la otra publicación.
    if (signals.some((s) => s.code === "DUPLICADO_CONFIRMADO")) {
      return { decision: "REJECT", explanation: "duplicado confirmado de una publicación existente" };
    }

    const grave = altas.length > 0 || medias.length >= MEDIAS_PARA_ESCALAR;
    if (!grave) {
      if (medias.length > 0) {
        return {
          decision: "REVIEW",
          explanation: `señales que conviene mirar: ${medias.map((s) => s.code).join(", ")}`,
        };
      }
      return {
        decision: "ALLOW",
        explanation: signals.length ? "sólo señales menores" : "sin señales",
      };
    }

    // Acá está la asimetría por origen.
    const motivo = altas.length
      ? altas.map((s) => s.code).join(", ")
      : `${medias.length} señales medias a la vez`;

    if (e.origin === "MANUAL" || e.origin === "API") {
      return { decision: "REJECT", explanation: `no se publica: ${motivo}` };
    }
    return {
      decision: "REVIEW",
      explanation:
        `a revisión y no bloqueada por ser ${e.origin.toLowerCase()}: ${motivo}. ` +
        "Bloquearla escondería una propiedad que existe y está publicada en su fuente",
    };
  };

  const { decision, explanation } = decidir();
  return { decision, signals, explanation };
}

/**
 * ¿La decisión permite mostrarla?
 *
 * REVIEW **muestra**. Es la decisión con más consecuencias del módulo, así que
 * conviene que sea explícita: si REVIEW ocultara, cualquier señal media sacaría
 * publicaciones reales del catálogo sin que nadie lo note, y con 257.073
 * publicaciones eso son miles. REVIEW significa "que alguien la mire", no "que
 * no se vea".
 *
 * Lo que oculta es REJECT.
 */
export function permiteMostrar(d: ModerationDecision): boolean {
  return d !== "REJECT";
}
