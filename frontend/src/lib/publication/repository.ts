// El contrato de persistencia, y un adaptador en memoria para probarlo.
//
// ---------------------------------------------------------------------------
// LA FRONTERA
// ---------------------------------------------------------------------------
//
//   UI  →  Application Service  →  PublicationRepository  →  (futuro adaptador)
//
// Esta interfaz ES la frontera. La UI no sabe qué hay del otro lado, y no debe:
// no menciona Supabase, ni PostgreSQL, ni tablas, ni SQL, ni un proveedor de
// archivos. Cuando exista persistencia real, se implementa esta interfaz y no
// se toca ni el wizard ni el servicio.
//
// Los métodos son los que el flujo necesita y ninguno más. Un contrato con
// métodos "por si acaso" obliga al primer adaptador real a implementar cosas
// que nadie llama.
//
// ---------------------------------------------------------------------------
// TRES COSAS QUE EL CONTRATO EXIGE Y SUELEN OLVIDARSE
// ---------------------------------------------------------------------------
//
// 1. IDEMPOTENCIA. `submit` recibe una clave. Dos envíos con la misma clave son
//    el mismo envío, no dos publicaciones. Sin esto, un doble click crea dos.
//
// 2. PROPIEDAD. Todo borrador tiene un dueño, y las lecturas la reciben para
//    poder negar. Un `getById` sin actor devuelve borradores ajenos a quien
//    sepa un id.
//
// 3. AUDITORÍA. Cada operación registra quién y cuándo. Es lo que permite
//    responder después qué pasó, y agregarlo más tarde es imposible: los
//    eventos que no se guardaron no se recuperan.

import type { AgentId, ListingId, OrganizationId, UserId } from "@/domain/ids";
import type { BorradorDePublicacion } from "@/domain/publishing";
import { fallo, ok, type Resultado } from "./errors";

/** Quién actúa, y en nombre de quién. */
export type ActorDePublicacion =
  | { kind: "INDIVIDUAL"; userId: UserId }
  | { kind: "AGENT"; userId: UserId; agentId: AgentId; organizationId: OrganizationId }
  | { kind: "ORGANIZATION"; userId: UserId; organizationId: OrganizationId };

/**
 * La organización en nombre de la que se publica, si la hay.
 *
 * Sale del actor, y el actor lo arma el servidor a partir de la sesión y las
 * membresías cargadas. **Nunca de lo que mande el cliente**: un
 * `organizationId` que viene en el body es una afirmación, no una prueba.
 */
export function organizacionDelActor(actor: ActorDePublicacion): OrganizationId | null {
  return actor.kind === "INDIVIDUAL" ? null : actor.organizationId;
}

export type MetadatosDeAuditoria = {
  actorUserId: UserId;
  at: string;
  action: "DRAFT_CREATED" | "DRAFT_UPDATED" | "SUBMITTED";
};

export type BorradorGuardado = {
  id: string;
  draft: BorradorDePublicacion;
  ownerUserId: UserId;
  organizationId: OrganizationId | null;
  createdAt: string;
  updatedAt: string;
  /** Para detectar escrituras concurrentes. */
  version: number;
  audit: readonly MetadatosDeAuditoria[];
};

export type PublicacionEnviada = {
  id: string;
  listingId: ListingId | null;
  submittedAt: string;
  idempotencyKey: string;
};

/**
 * Lo que hace falta de la persistencia. Nada más.
 *
 * Todos los métodos reciben el actor: la autorización no se resuelve antes y se
 * confía después. Un repositorio que acepta operaciones sin actor es un
 * repositorio que alguien va a llamar sin verificar.
 */
export type PublicationRepository = {
  createDraft(
    actor: ActorDePublicacion,
    draft: BorradorDePublicacion,
    at: string,
  ): Promise<Resultado<BorradorGuardado>>;

  updateDraft(
    actor: ActorDePublicacion,
    id: string,
    draft: BorradorDePublicacion,
    expectedVersion: number,
    at: string,
  ): Promise<Resultado<BorradorGuardado>>;

  getById(actor: ActorDePublicacion, id: string): Promise<Resultado<BorradorGuardado>>;

  submit(
    actor: ActorDePublicacion,
    id: string,
    idempotencyKey: string,
    at: string,
  ): Promise<Resultado<PublicacionEnviada>>;

  /** Cuántas publicaciones activas tiene, para la política del particular. */
  countActiveByOwner(actor: ActorDePublicacion): Promise<Resultado<number>>;
};

// --- adaptador en memoria --------------------------------------------------

/**
 * Implementación en memoria. **Sólo para tests y QA interno.**
 *
 * No es una persistencia a medias: no sobrevive al proceso, y por eso nunca
 * debe alimentar una pantalla pública. Su valor es poder recorrer el flujo
 * entero —wizard, servicio, repositorio, resultado— y comprobar que la frontera
 * es real: si el servicio dependiera de algo de la base, este adaptador no
 * podría existir.
 */
export function crearRepositorioEnMemoria(): PublicationRepository & {
  /** Sólo para inspeccionar en tests. */
  _todos(): BorradorGuardado[];
} {
  const borradores = new Map<string, BorradorGuardado>();
  const enviosPorClave = new Map<string, PublicacionEnviada>();
  let siguienteId = 1;

  /** ¿Este actor puede tocar este borrador? */
  const puedeAcceder = (actor: ActorDePublicacion, guardado: BorradorGuardado): boolean => {
    if (guardado.ownerUserId === actor.userId) return true;
    // Alguien de la misma organización puede continuarlo; la capacidad concreta
    // la evalúa el servicio con el motor de permisos.
    const org = organizacionDelActor(actor);
    return org !== null && guardado.organizationId === org;
  };

  return {
    _todos: () => [...borradores.values()],

    async createDraft(actor, draft, at) {
      const id = `draft-${siguienteId++}`;
      const guardado: BorradorGuardado = {
        id,
        draft,
        ownerUserId: actor.userId,
        organizationId: organizacionDelActor(actor),
        createdAt: at,
        updatedAt: at,
        version: 1,
        audit: [{ actorUserId: actor.userId, at, action: "DRAFT_CREATED" }],
      };
      borradores.set(id, guardado);
      return ok(guardado);
    },

    async getById(actor, id) {
      const guardado = borradores.get(id);
      // Mismo error para "no existe" y "no es tuyo": distinguirlos le confirma
      // a quien prueba ids que ese borrador existe.
      if (!guardado || !puedeAcceder(actor, guardado)) {
        return fallo("DRAFT_NOT_FOUND", "No encontramos ese borrador.");
      }
      return ok(guardado);
    },

    async updateDraft(actor, id, draft, expectedVersion, at) {
      const guardado = borradores.get(id);
      if (!guardado || !puedeAcceder(actor, guardado)) {
        return fallo("DRAFT_NOT_FOUND", "No encontramos ese borrador.");
      }
      if (guardado.version !== expectedVersion) {
        return fallo("CONFLICT", "Alguien modificó este borrador desde que lo abriste.");
      }
      const siguiente: BorradorGuardado = {
        ...guardado,
        draft,
        updatedAt: at,
        version: guardado.version + 1,
        audit: [...guardado.audit, { actorUserId: actor.userId, at, action: "DRAFT_UPDATED" }],
      };
      borradores.set(id, siguiente);
      return ok(siguiente);
    },

    async submit(actor, id, idempotencyKey, at) {
      // La comprobación de idempotencia va PRIMERO, antes de mirar el borrador:
      // si el envío ya se procesó, la respuesta es la misma aunque el borrador
      // haya cambiado o desaparecido después.
      const previo = enviosPorClave.get(idempotencyKey);
      if (previo) return fallo("DUPLICATE_SUBMISSION", "Este envío ya se había registrado.");

      const guardado = borradores.get(id);
      if (!guardado || !puedeAcceder(actor, guardado)) {
        return fallo("DRAFT_NOT_FOUND", "No encontramos ese borrador.");
      }

      const enviada: PublicacionEnviada = {
        id: guardado.id,
        // `null` a propósito: la publicación todavía no existe como listing.
        // Ese id lo asigna la persistencia real cuando exista.
        listingId: null,
        submittedAt: at,
        idempotencyKey,
      };
      enviosPorClave.set(idempotencyKey, enviada);
      borradores.set(id, {
        ...guardado,
        audit: [...guardado.audit, { actorUserId: actor.userId, at, action: "SUBMITTED" }],
      });
      return ok(enviada);
    },

    async countActiveByOwner(actor) {
      return ok([...borradores.values()].filter((b) => b.ownerUserId === actor.userId).length);
    },
  };
}
