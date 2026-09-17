// Cómo una inmobiliaria administra una publicación que scrapeamos de su sitio.
//
// El caso: la inmobiliaria López reclama su organización, entra, y ve que la
// ficha de un departamento suyo tiene el precio viejo y un teléfono que ya no
// usa. Quiere corregirlo. Razonable, y hoy imposible.
//
// La tentación es dejarla editar la fila y listo. No se hace, por dos motivos
// que se refuerzan:
//
//   1. El scraper vuelve a pasar. Si editó la fila, el próximo scrapeo le pisa
//      la corrección con el dato viejo de la fuente, y ella vuelve a corregir,
//      y así. Sin una capa aparte, la corrección tiene fecha de vencimiento.
//
//   2. Se pierde la trazabilidad. Ese dato salió de una página concreta en una
//      fecha concreta. Si se sobrescribe, ya no se puede responder "¿de dónde
//      sacaron este precio?", ni ante un reclamo ni ante un problema legal.
//
// De ahí las tres capas:
//
//   SOURCE SNAPSHOT   lo que dice la fuente. Sólo lo escribe el scraper.
//                     Inmutable para todo lo demás.
//   EDITORIAL OVERRIDE lo que corrige el dueño, campo por campo, con autor y
//                     fecha.
//   PUBLISHED VIEW    lo que ve el público: el snapshot con los overrides
//                     aplicados encima.
//
// La vista publicada NO se guarda: se calcula. Guardarla crearía una tercera
// copia que se desincroniza de las otras dos, que es el problema original con
// un paso más.

import type { AgentId, ListingId, UserId } from "./ids";

/**
 * Campos que el dueño puede corregir.
 *
 * Lista cerrada a propósito. Dos que NO están, y conviene decir por qué:
 *
 * - `sourceUrl`: es la prueba de dónde salió el dato. Editarla rompe la
 *   trazabilidad, que es justamente lo que estas capas protegen.
 * - `id`: la identidad no se corrige.
 *
 * `operation` y `propertyType` sí están: un scraper puede clasificar mal, y el
 * dueño sabe si es venta o alquiler.
 */
export const CAMPOS_CORREGIBLES = [
  "title",
  "description",
  "price",
  "currency",
  "expenses",
  "operation",
  "propertyType",
  "rooms",
  "bedrooms",
  "bathrooms",
  "garages",
  "totalArea",
  "coveredArea",
  "landArea",
  "age",
  "address",
  "neighborhood",
  "city",
  "province",
  "latitude",
  "longitude",
  "images",
  "videoUrl",
  "floorPlanUrl",
  "amenities",
  "contactPhone",
  "contactEmail",
  "assignedAgentId",
] as const;
export type CampoCorregible = (typeof CAMPOS_CORREGIBLES)[number];

export function esCampoCorregible(campo: string): campo is CampoCorregible {
  return (CAMPOS_CORREGIBLES as readonly string[]).includes(campo);
}

/**
 * Una corrección sobre un campo.
 *
 * `value: null` es una corrección válida y significativa: "este dato que la
 * fuente trae está mal, no hay dato". Es distinto de no tener override, que
 * significa "usá lo que dice la fuente". Por eso el override se representa por
 * su presencia en el mapa y no por su valor.
 */
export type Override = {
  field: CampoCorregible;
  value: unknown;
  authorUserId: UserId;
  at: string;
  /** Motivo declarado, si lo dio. Útil ante un reclamo posterior. */
  reason: string | null;
};

/** Estado editorial que el dueño puede fijar, con efecto sobre la visibilidad. */
export const ESTADOS_EDITORIALES = ["NONE", "PAUSED", "DELISTING_REQUESTED"] as const;
export type EstadoEditorial = (typeof ESTADOS_EDITORIALES)[number];

export type EditorialLayer = {
  listingId: ListingId;
  /** Un override por campo: el último gana. La historia va en `AuditEvent`. */
  overrides: Readonly<Record<string, Override>>;
  estado: EstadoEditorial;
  assignedAgentId: AgentId | null;
};

/**
 * Aplica los overrides sobre el snapshot.
 *
 * Genérico sobre la forma del snapshot para no atarlo a `Property`: la capa de
 * presentación puede cambiar sin tocar esta lógica.
 *
 * Acepta overrides sobre campos que el snapshot no trae, y los agrega. No es
 * permisividad: una fuente puede no traer `videoUrl` y el dueño querer
 * cargarlo, y rechazarlo obligaría a que la fuente tuviera todos los campos
 * vacíos para poder corregirlos.
 *
 * De ahí el `Partial<Record<CampoCorregible, unknown>>` en el tipo de retorno:
 * el resultado puede tener claves que `T` no declara, y decir sólo `T` sería
 * un tipo que miente sobre lo que la función hace.
 */
export function aplicarOverrides<T extends Record<string, unknown>>(
  snapshot: T,
  capa: EditorialLayer | null,
): T & Partial<Record<CampoCorregible, unknown>> & { overriddenFields: readonly CampoCorregible[] } {
  const aplicados: CampoCorregible[] = [];
  const resultado: Record<string, unknown> = { ...snapshot };

  for (const [campo, override] of Object.entries(capa?.overrides ?? {})) {
    if (!esCampoCorregible(campo)) continue;
    resultado[campo] = override.value;
    aplicados.push(campo);
  }

  aplicados.sort();
  return { ...(resultado as T), overriddenFields: aplicados };
}

/**
 * Qué campos difieren entre la fuente y lo publicado.
 *
 * Sirve para dos cosas concretas: mostrarle al dueño qué corrigió, y detectar
 * cuándo la fuente se actualizó y alcanzó al override —momento en que la
 * corrección dejó de hacer falta y conviene ofrecer quitarla, en vez de
 * mantener una capa que ya no corrige nada—.
 */
export function correccionesRedundantes<T extends Record<string, unknown>>(
  snapshot: T,
  capa: EditorialLayer | null,
): CampoCorregible[] {
  const redundantes: CampoCorregible[] = [];
  for (const [campo, override] of Object.entries(capa?.overrides ?? {})) {
    if (!esCampoCorregible(campo)) continue;
    // Comparación estructural: sirve para escalares y para arrays de imágenes.
    if (JSON.stringify(snapshot[campo]) === JSON.stringify(override.value)) {
      redundantes.push(campo);
    }
  }
  return redundantes.sort();
}

/**
 * ¿Puede mostrarse públicamente, según la capa editorial?
 *
 * Una baja SOLICITADA no oculta por sí sola, y es deliberado: dar de baja una
 * publicación de la que sólo tenemos evidencia scrapeada, a pedido de quien
 * dice ser el dueño, es una acción con consecuencias —podría usarse para
 * borrar la competencia—. La solicitud abre un caso; la decisión es aparte.
 *
 * Pausar sí es inmediato: el riesgo de pausar de más es que se vea menos
 * oferta, temporal y reversible.
 */
export function capaPermiteMostrar(capa: EditorialLayer | null): boolean {
  if (!capa) return true;
  return capa.estado !== "PAUSED";
}

/**
 * ¿Es válida esta corrección?
 *
 * Se valida al REGISTRARLA, no al aplicarla: una corrección inválida guardada
 * rompería la ficha en cada lectura posterior, y el momento de rechazarla es
 * cuando alguien la escribe y puede corregirla.
 */
export function problemasDeOverride(o: Override): string[] {
  const problemas: string[] = [];
  if (!esCampoCorregible(o.field)) {
    problemas.push(`${o.field} no es un campo corregible`);
  }
  if (!o.authorUserId) problemas.push("toda corrección necesita autor");
  if (!o.at) problemas.push("toda corrección necesita fecha");
  return problemas;
}
