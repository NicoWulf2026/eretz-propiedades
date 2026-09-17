// Capa de aplicación de la publicación.
//
// Orquesta permisos, validación, moderación y persistencia. **No importa nada
// de React**: es una función sobre datos, así que se prueba entera sin montar
// un componente, y el mismo código sirve si mañana el wizard cambia o si se
// llama desde una ruta de API.
//
// El orden de las comprobaciones no es arbitrario. Va de lo más barato y
// definitivo a lo más caro:
//
//   1. PERMISO      no depende del contenido, y si falta, validar es tiempo
//                   perdido y le mostraría a la persona errores de campos que
//                   no tiene derecho a completar;
//   2. LÍMITE       tampoco depende del contenido;
//   3. VALIDACIÓN   reglas duras: sin esto no hay publicación posible;
//   4. MODERACIÓN   necesita el contenido ya válido para no evaluar basura.

import { analizarCalidad } from "@/domain/data-quality";
import { moderar, type ModerationResult } from "@/domain/moderation";
import { can, type Actor } from "@/domain/permissions";
import { calcularScore, type QualityScore } from "@/domain/quality-score";
import {
  POLITICA_PARTICULAR,
  validarBorrador,
  type BorradorDePublicacion,
} from "@/domain/publishing";
import { fallo, ok, type CampoConError, type Resultado } from "./errors";
import {
  organizacionDelActor,
  type ActorDePublicacion,
  type BorradorGuardado,
  type PublicacionEnviada,
  type PublicationRepository,
} from "./repository";
import { aEntradaDeModeracion, aEntradaDeScore, aPublicacionAnalizable } from "./adapter";

export type ContextoDePublicacion = {
  repository: PublicationRepository;
  /** El actor con sus membresías YA CARGADAS. Ver `repository.ts`. */
  actor: ActorDePublicacion;
  /** El actor tal como lo entiende el motor de permisos. */
  permisos: Actor;
  /** Reloj inyectado: hace los tests deterministas. */
  ahora: () => string;
};

/**
 * ¿Puede este actor crear una publicación en este contexto?
 *
 * Reutiliza el motor de permisos existente; no hay un segundo sistema. Para el
 * particular no hay organización, así que no hay nada que autorizar contra un
 * tenant: publica en nombre propio.
 */
export function puedeCrear(ctx: ContextoDePublicacion): boolean {
  const org = organizacionDelActor(ctx.actor);
  if (org === null) return ctx.actor.kind === "INDIVIDUAL";
  return can(ctx.permisos, "listing.create", {
    kind: "LISTING",
    organizationId: org,
    listingId: "nuevo" as never,
    assignedAgentId: null,
  });
}

// --- crear y actualizar ----------------------------------------------------

export async function crearBorrador(
  ctx: ContextoDePublicacion,
  draft: BorradorDePublicacion,
): Promise<Resultado<BorradorGuardado>> {
  if (!puedeCrear(ctx)) {
    return fallo("PERMISSION_DENIED", "No tenés permiso para publicar en nombre de esta inmobiliaria.");
  }

  const limite = await verificarLimite(ctx);
  if (!limite.ok) return limite;

  return ctx.repository.createDraft(ctx.actor, draft, ctx.ahora());
}

export async function actualizarBorrador(
  ctx: ContextoDePublicacion,
  id: string,
  draft: BorradorDePublicacion,
  expectedVersion: number,
): Promise<Resultado<BorradorGuardado>> {
  if (!puedeCrear(ctx)) {
    return fallo("PERMISSION_DENIED", "No tenés permiso para editar esta publicación.");
  }
  return ctx.repository.updateDraft(ctx.actor, id, draft, expectedVersion, ctx.ahora());
}

/**
 * Límite de publicaciones gratuitas del particular.
 *
 * El número vive en `POLITICA_PARTICULAR`, no acá: un 5 escrito en esta función
 * y otro en la UI se desincronizan en cuanto alguien cambie uno.
 */
async function verificarLimite(ctx: ContextoDePublicacion): Promise<Resultado<void>> {
  if (ctx.actor.kind !== "INDIVIDUAL") return ok(undefined);

  const conteo = await ctx.repository.countActiveByOwner(ctx.actor);
  if (!conteo.ok) return conteo;

  if (conteo.value >= POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT) {
    return fallo(
      "LIMIT_REACHED",
      `Llegaste al máximo de ${POLITICA_PARTICULAR.FREE_INDIVIDUAL_LISTING_LIMIT} publicaciones gratuitas.`,
    );
  }
  return ok(undefined);
}

// --- revisión previa al envío ----------------------------------------------

export type SugerenciaDeMejora = { field: string; message: string };

export type RevisionPrevia = {
  /** Lo que impide publicar. Vacío = se puede enviar. */
  bloqueantes: CampoConError[];
  /** Lo que conviene mejorar pero no impide nada. */
  sugerencias: SugerenciaDeMejora[];
  moderacion: ModerationResult;
  /** Interno. NO se muestra como número: ver `sugerencias`. */
  score: QualityScore;
  listoParaEnviar: boolean;
};

/**
 * Traduce el puntaje de calidad en cosas que hacer.
 *
 * Deliberadamente NO devuelve el número. "Tu publicación tiene 82/100" invita a
 * optimizar la métrica en vez de la publicación, y no le dice a nadie qué
 * hacer. "Agregá fotos" sí.
 */
function sugerenciasDesdeElPuntaje(score: QualityScore): SugerenciaDeMejora[] {
  const out: SugerenciaDeMejora[] = [];
  if (score.media.score < 0.5) {
    out.push({ field: "images", message: "Agregá más fotos: es lo primero que se mira." });
  }
  if (score.location.score < 0.6) {
    out.push({ field: "address", message: "Completá la dirección para que aparezca mejor ubicada." });
  }
  if (score.completeness.score < 0.8) {
    out.push({ field: "features", message: "Completá superficie y ambientes: son los filtros más usados." });
  }
  return out;
}

/**
 * Todo lo que hay que saber antes de enviar.
 *
 * La moderación se aplica **sólo a este contenido**, el que la persona está
 * intentando publicar. No es el modo sombra del catálogo ni lo modifica: son
 * dos cosas distintas que usan el mismo motor.
 *
 * Y acá sí una carga manual puede bloquearse, a diferencia de lo scrapeado. La
 * asimetría es deliberada y ya está en `domain/moderation.ts`: rechazar una
 * carga manual cuesta un minuto de quien la hizo; esconder una scrapeada borra
 * inventario que existe.
 */
export function revisarAntesDeEnviar(draft: BorradorDePublicacion): RevisionPrevia {
  const bloqueantes = validarBorrador(draft);

  const analizable = aPublicacionAnalizable(draft);
  const calidad = analizarCalidad(analizable);
  const moderacion = moderar(aEntradaDeModeracion(draft, calidad));
  const score = calcularScore(aEntradaDeScore(draft, calidad));

  if (moderacion.decision === "REJECT") {
    bloqueantes.push({
      field: "contenido",
      code: "MODERACION",
      message: "Revisá los datos: hay algo que no cierra y no podemos publicarla así.",
    });
  }

  return {
    bloqueantes,
    sugerencias: sugerenciasDesdeElPuntaje(score),
    moderacion,
    score,
    listoParaEnviar: bloqueantes.length === 0,
  };
}

// --- envío -----------------------------------------------------------------

/**
 * Clave de idempotencia.
 *
 * La genera el CLIENTE al abrir el formulario y la conserva durante todo el
 * envío, incluidos los reintentos. Si la generara el servidor, dos requests del
 * mismo doble click traerían claves distintas y crearían dos publicaciones, que
 * es exactamente lo que la clave existe para evitar.
 */
export function nuevaClaveDeIdempotencia(): string {
  return globalThis.crypto?.randomUUID?.() ?? `pub-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function enviarPublicacion(
  ctx: ContextoDePublicacion,
  id: string,
  idempotencyKey: string,
): Promise<Resultado<PublicacionEnviada>> {
  if (!puedeCrear(ctx)) {
    return fallo("PERMISSION_DENIED", "No tenés permiso para publicar esto.");
  }

  const guardado = await ctx.repository.getById(ctx.actor, id);
  if (!guardado.ok) return guardado;

  // Se revalida contra lo GUARDADO, no contra lo que mande el cliente: entre
  // que la UI dijo "listo" y llega el envío, el borrador pudo cambiar.
  const revision = revisarAntesDeEnviar(guardado.value.draft);
  if (!revision.listoParaEnviar) {
    const esModeracion = revision.bloqueantes.some((b) => b.code === "MODERACION");
    return fallo(
      esModeracion ? "MODERATION_BLOCKED" : "VALIDATION_ERROR",
      "La publicación todavía tiene datos que corregir.",
      revision.bloqueantes,
    );
  }

  return ctx.repository.submit(ctx.actor, id, idempotencyKey, ctx.ahora());
}
