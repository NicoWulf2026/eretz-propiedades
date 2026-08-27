// Una PUBLICACIÓN: la aparición concreta de una propiedad en algún lado.
//
// Este archivo existe para deshacer una fusión que hoy está en el código.
// `src/types/property.ts` tiene un único tipo `Property` que mezcla tres cosas
// que cambian por motivos distintos y en momentos distintos:
//
//   1. la propiedad FÍSICA (un departamento en tal calle);
//   2. la PUBLICACIÓN de esa propiedad (un aviso, con precio y fotos);
//   3. quién la PUBLICA (una inmobiliaria, un agente, un particular).
//
// Mientras todo venía de scraping y se mostraba de a una, la fusión no molestaba.
// Rompe en cuanto aparece lo que viene: la misma propiedad publicada por dos
// inmobiliarias con precios distintos, o una inmobiliaria que corrige su propio
// aviso scrapeado sin poder tocar el original.
//
// `Property` NO se elimina ni se reescribe: sigue siendo el tipo de la capa de
// presentación actual, que funciona. Esto es el modelo hacia el que migrar.
//
// ---------------------------------------------------------------------------
// LOS TRES EJES DE ESTADO, Y POR QUÉ NO SON UNO
// ---------------------------------------------------------------------------
//
// El encargo proponía un único ciclo DRAFT → PENDING → ACTIVE → PAUSED →
// REMOVED / REJECTED, dejando abierto usar "mejor modelo si el código actual
// sugiere otro". El código actual sugiere otro, y con una razón concreta.
//
// Hoy `PropertyStatus` vale "activa" | "no_detectada_en_ultimo_scraping" |
// "desconocida". Eso NO es un ciclo de vida: es **lo que el scraper vio la
// última vez que miró**. Nadie decidió "activa"; se observó.
//
// Para las 257.073 publicaciones scrapeadas de hoy, el ciclo de vida editorial
// sencillamente NO EXISTE: ningún publicador apretó "publicar" en ERETZ. Meter
// esas filas en un campo `lifecycle: ACTIVE` sería inventar una decisión que
// nadie tomó, y después sería imposible distinguir "el dueño la activó" de
// "la vimos publicada en otro lado".
//
// Por eso son tres ejes independientes:
//
//   OBSERVACIÓN  — qué vimos.        Aplica a todo lo scrapeado.
//   CICLO        — qué decidió quien publica. Sólo existe si alguien publicó acá.
//   MODERACIÓN   — qué decidimos nosotros.    Ortogonal a los otros dos.
//
// Una publicación puede estar observada como activa, sin ciclo de vida (nunca
// se publicó en ERETZ) y en moderación REVIEW. Los tres a la vez, sin
// contradicción.

import type { AgentId, BranchId, ListingId, OrganizationId, PropertyEntityId, UserId } from "./ids";

// --- eje 1: origen ---------------------------------------------------------

/**
 * De dónde salió la publicación.
 *
 * Determina qué ejes de estado tienen sentido y qué se puede editar. Es el
 * discriminante más importante del modelo.
 */
export const LISTING_ORIGINS = ["SCRAPED", "MANUAL", "IMPORTED", "API", "UNKNOWN"] as const;
export type ListingOrigin = (typeof LISTING_ORIGINS)[number];

/**
 * `UNKNOWN` se agregó al enfrentar el modelo con datos reales.
 *
 * El origen no viaja en `Property`: vive en la fila cruda (`fuente_extraccion`,
 * `cms_origen`). Cuando ninguno de los dos está, no sabemos de dónde vino esa
 * publicación, y las dos salidas fáciles son malas: asumir `SCRAPED` es
 * inventar un hecho —además del que casi siempre acierta, que es peor, porque
 * vuelve invisible al que no—, y omitir la evaluación deja un hueco en la
 * medición justo donde el dato es más pobre.
 *
 * Al no ser `MANUAL` ni `API`, cae por construcción en la rama conservadora de
 * la moderación: revisar, no bloquear. Es la respuesta correcta ante la duda.
 */

/**
 * ¿El origen implica que alguien publicó deliberadamente EN ERETZ?
 *
 * Sólo en ese caso existe un ciclo de vida editorial. Para lo scrapeado no hay
 * decisión de publicación que registrar, y el modelo no debe fingir que la hay.
 */
export function tieneCicloEditorial(origin: ListingOrigin): boolean {
  return origin === "MANUAL" || origin === "API";
}

// --- eje 2: observación ----------------------------------------------------

/**
 * Qué vimos la última vez que miramos la fuente.
 *
 * Conserva exactamente la semántica de `PropertyStatus` actual, incluidos los
 * nombres, para que la migración sea una traducción y no una reinterpretación.
 */
export const OBSERVATION_STATUSES = ["ACTIVE", "NOT_SEEN_LAST_SCRAPE", "UNKNOWN"] as const;
export type ObservationStatus = (typeof OBSERVATION_STATUSES)[number];

/** Traducción exacta desde el `estado` de la base. Sin adivinar. */
export function observacionDesdeEstado(estado: string | null | undefined): ObservationStatus {
  if (estado === "activa") return "ACTIVE";
  if (estado === "no_detectada_en_ultimo_scraping") return "NOT_SEEN_LAST_SCRAPE";
  return "UNKNOWN";
}

/**
 * ¿Está confirmada la disponibilidad?
 *
 * Sólo ACTIVE lo está. Y lo que importa: NOT_SEEN y UNKNOWN son distintos entre
 * sí —uno es "la buscamos y no estaba", el otro "no sabemos"— y NINGUNO de los
 * dos significa "no disponible". La UI ya respeta esto ("Disponibilidad no
 * confirmada"); el modelo lo hace explícito para que siga respetándose.
 */
export function disponibilidadConfirmada(o: ObservationStatus): boolean {
  return o === "ACTIVE";
}

// --- eje 3: ciclo de vida editorial ----------------------------------------

/**
 * Qué decidió quien publica. `null` cuando no aplica (todo lo scrapeado).
 *
 * REMOVED es terminal por decisión del publicador; REJECTED es terminal por
 * decisión de moderación pero se registra acá porque cambia lo que el
 * publicador puede hacer después.
 */
export const PUBLICATION_STATUSES = [
  "DRAFT",
  "PENDING_REVIEW",
  "PUBLISHED",
  "PAUSED",
  "REMOVED",
  "REJECTED",
] as const;
export type PublicationStatus = (typeof PUBLICATION_STATUSES)[number];

/**
 * Transiciones permitidas.
 *
 * Deny by default: lo que no está acá, no se puede. Un mapa explícito se lee y
 * se testea; una cadena de `if` se olvida.
 */
export const TRANSICIONES_PUBLICACION: Readonly<Record<PublicationStatus, readonly PublicationStatus[]>> =
  Object.freeze({
    DRAFT: ["PENDING_REVIEW", "REMOVED"],
    // Una moderación puede aprobar (PUBLISHED) o rechazar (REJECTED); el
    // publicador puede volver a editarla (DRAFT) o darla de baja.
    PENDING_REVIEW: ["PUBLISHED", "REJECTED", "DRAFT", "REMOVED"],
    PUBLISHED: ["PAUSED", "REMOVED", "PENDING_REVIEW"],
    PAUSED: ["PUBLISHED", "REMOVED"],
    // Terminales. Rehacer una publicación dada de baja es crear otra, no
    // resucitar ésta: así el historial no miente sobre qué estuvo visible.
    REMOVED: [],
    // Un rechazo se corrige editando, lo que devuelve a DRAFT. No hay atajo a
    // PUBLISHED que saltee la revisión.
    REJECTED: ["DRAFT"],
  });

export function puedeTransicionar(desde: PublicationStatus, hacia: PublicationStatus): boolean {
  return TRANSICIONES_PUBLICACION[desde]?.includes(hacia) ?? false;
}

export function esEstadoTerminal(estado: PublicationStatus): boolean {
  return TRANSICIONES_PUBLICACION[estado].length === 0;
}

export class TransicionInvalida extends Error {
  constructor(
    readonly desde: PublicationStatus,
    readonly hacia: PublicationStatus,
  ) {
    super(`Transición inválida: ${desde} → ${hacia}`);
    this.name = "TransicionInvalida";
  }
}

/** Aplica una transición o falla. No muta: devuelve el estado nuevo. */
export function transicionar(desde: PublicationStatus, hacia: PublicationStatus): PublicationStatus {
  if (!puedeTransicionar(desde, hacia)) throw new TransicionInvalida(desde, hacia);
  return hacia;
}

// --- eje 4: moderación -----------------------------------------------------

/**
 * Qué decidimos nosotros sobre el contenido. Independiente de los otros ejes.
 *
 * NOT_ASSESSED no es lo mismo que ALLOWED: una publicación que nadie evaluó no
 * está aprobada, sólo no mirada. Esa diferencia es la que permite tratarlas
 * distinto sin mentir sobre cuál es cuál.
 */
export const MODERATION_STATUSES = ["NOT_ASSESSED", "ALLOWED", "UNDER_REVIEW", "BLOCKED"] as const;
export type ModerationStatus = (typeof MODERATION_STATUSES)[number];

/**
 * ¿Puede mostrarse públicamente?
 *
 * Fail-closed a propósito, y en el mismo espíritu que el Quality Gate: sólo se
 * ocultan BLOCKED y UNDER_REVIEW. NOT_ASSESSED se muestra porque es el estado
 * de las 257k publicaciones existentes; tratarlo como oculto vaciaría el
 * catálogo. Queda explícito para que sea una decisión visible y no un descuido.
 */
export function moderacionPermiteMostrar(m: ModerationStatus): boolean {
  return m === "ALLOWED" || m === "NOT_ASSESSED";
}

// --- publicador ------------------------------------------------------------

/**
 * Quién publica. Unión discriminada, no tres campos opcionales.
 *
 * Con campos opcionales sería representable el estado "tiene organizationId y
 * también es particular", que no significa nada. Con unión, no.
 */
export type PublisherRef =
  | { kind: "ORGANIZATION"; organizationId: OrganizationId; branchId: BranchId | null; agentId: AgentId | null }
  | { kind: "AGENT"; agentId: AgentId; organizationId: OrganizationId | null }
  | { kind: "INDIVIDUAL"; userId: UserId }
  // Lo scrapeado: sabemos el nombre que apareció, no quién es. Es el estado
  // más común hoy y el modelo tiene que nombrarlo en vez de dejarlo en null.
  | { kind: "UNIDENTIFIED"; displayName: string | null; sourceHost: string | null };

/** ¿La publicación pertenece a un tenant administrable? */
export function organizacionDePublicador(p: PublisherRef): OrganizationId | null {
  if (p.kind === "ORGANIZATION") return p.organizationId;
  if (p.kind === "AGENT") return p.organizationId;
  return null;
}

// --- la publicación --------------------------------------------------------

/**
 * Marcas de tiempo, separadas porque significan cosas distintas.
 *
 * El encargo pide explícitamente no usar `firstSeenAt` como fecha de
 * publicación, y tiene razón: que la hayamos visto por primera vez el martes
 * no dice nada sobre cuándo se publicó. Cuando `publishedAt` es null, es null.
 */
export type ListingTimestamps = {
  /** Cuándo se publicó, según la fuente. null si la fuente no lo dice. */
  publishedAt: string | null;
  /** La primera vez que ERETZ la vio. Nunca es la fecha de publicación. */
  firstSeenAt: string | null;
  /** La última vez que ERETZ la vio en la fuente. */
  lastSeenAt: string | null;
  /** Última modificación del registro en ERETZ. */
  updatedAt: string | null;
};

export type Listing = {
  id: ListingId;

  /**
   * La propiedad física que publica. `null` mientras no se resolvió.
   *
   * Nullable a propósito: resolver qué publicaciones son la misma propiedad es
   * un proceso con confianza asociada (ver `lib/duplicates.ts`), no un hecho
   * disponible al insertar. Forzar un valor acá obligaría a inventar entidades
   * de una publicación cada una, que es exactamente el problema a evitar.
   */
  propertyEntityId: PropertyEntityId | null;

  origin: ListingOrigin;
  publisher: PublisherRef;

  observation: ObservationStatus;
  /** null cuando el origen no tiene ciclo editorial. Ver `tieneCicloEditorial`. */
  lifecycle: PublicationStatus | null;
  moderation: ModerationStatus;

  timestamps: ListingTimestamps;

  /** URL en la fuente original. Se conserva siempre, también tras editar. */
  sourceUrl: string | null;
};

/**
 * ¿El modelo es internamente coherente?
 *
 * Existe porque las combinaciones imposibles se cuelan en cuanto hay dos
 * caminos de escritura. Devuelve la lista de problemas en vez de un booleano:
 * un "false" pelado no se puede depurar.
 */
export function problemasDeCoherencia(l: Listing): string[] {
  const problemas: string[] = [];

  if (tieneCicloEditorial(l.origin) && l.lifecycle === null) {
    problemas.push(`origen ${l.origin} exige ciclo de vida y es null`);
  }
  if (!tieneCicloEditorial(l.origin) && l.lifecycle !== null) {
    problemas.push(`origen ${l.origin} no tiene ciclo de vida y vale ${l.lifecycle}`);
  }
  if (l.origin === "SCRAPED" && l.publisher.kind === "INDIVIDUAL") {
    problemas.push("una publicación scrapeada no puede atribuirse a un particular identificado");
  }
  return problemas;
}

/**
 * ¿Se puede mostrar en el sitio público?
 *
 * Deliberadamente NO incluye el Quality Gate: ése es una autoridad aparte, con
 * su propio manifiesto, y mezclarlos acá haría que una de las dos barreras
 * pareciera redundante y alguien la sacara. Esto es la barrera del dominio; el
 * Gate es la barrera de datos. Se aplican las dos.
 */
export function esVisiblePublicamente(l: Listing): boolean {
  if (!moderacionPermiteMostrar(l.moderation)) return false;
  // Sin ciclo editorial (scrapeado), la visibilidad la deciden observación y
  // moderación. Con ciclo, además tiene que estar efectivamente publicada.
  if (l.lifecycle !== null && l.lifecycle !== "PUBLISHED") return false;
  return l.observation !== "NOT_SEEN_LAST_SCRAPE";
}
