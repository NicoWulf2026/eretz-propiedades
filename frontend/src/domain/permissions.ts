// Motor de permisos: ¿puede este actor hacer esta acción sobre este recurso?
//
// Función pura, sin base y sin red, para que sea testeable de forma exhaustiva.
// Es la clase de código donde un bug no se ve hasta que alguien edita datos
// ajenos, así que se prioriza que sea aburrido y verificable por encima de que
// sea flexible.
//
// ---------------------------------------------------------------------------
// TRES REGLAS QUE NO SE NEGOCIAN
// ---------------------------------------------------------------------------
//
// 1. DENY BY DEFAULT. `can` devuelve false salvo que exista una razón explícita
//    para el sí. Todo camino de error, dato faltante o caso no contemplado
//    termina en false. Nunca hay un `return true` de cierre.
//
// 2. EL TENANT SALE DEL RECURSO, NUNCA DEL PEDIDO. Ésta es la regla que evita
//    la vulnerabilidad clásica de multi-tenancy: si el `organizationId` con el
//    que se compara viene del cliente —query string, body, cabecera, o la
//    organización "seleccionada" en el browser— entonces cualquiera se declara
//    dueño de lo que quiera. `RecursoContext.organizationId` tiene que venir de
//    haber CARGADO el recurso del servidor. El tipo no puede forzar eso, así
//    que lo fuerza la disciplina y lo recuerda este comentario.
//
// 3. EL ROL NO ES EL PERMISO. No hay `if (role === "ADMIN")` disperso por el
//    código. Los roles se traducen a capacidades en un único lugar, y todo lo
//    demás pregunta por capacidades. Cambiar qué puede hacer un MANAGER es
//    entonces editar una tabla, no auditar la aplicación entera.

import type { AgentId, BranchId, ListingId, OrganizationId, UserId } from "./ids";

// --- capacidades -----------------------------------------------------------

/**
 * Todo lo que se puede hacer dentro de una organización.
 *
 * Granularidad deliberada: `organization.branding.edit` está separado de
 * `organization.edit` porque quien diseña el miniportal no tiene por qué poder
 * cambiar la razón social.
 */
export const CAPABILITIES = [
  "organization.view",
  "organization.edit",
  "organization.branding.edit",
  "organization.members.manage",
  "organization.roles.manage",
  "organization.delete",
  "branch.manage",
  "agent.manage",
  "listing.view",
  "listing.create",
  "listing.edit",
  "listing.pause",
  "listing.remove",
  "listing.assign_agent",
  "lead.view",
  "analytics.view",
  "billing.manage",
] as const;
export type Capability = (typeof CAPABILITIES)[number];

// --- roles -----------------------------------------------------------------

export const ROLES = ["OWNER", "ADMIN", "MANAGER", "AGENT", "EDITOR", "VIEWER"] as const;
export type Role = (typeof ROLES)[number];

/**
 * Qué puede cada rol. El único lugar donde un rol se convierte en poder.
 *
 * Notas sobre decisiones que no son obvias:
 *
 * - Sólo OWNER administra roles y facturación. Que un ADMIN pueda ascender a
 *   otro a OWNER es una escalada de privilegios silenciosa.
 * - AGENT edita publicaciones pero NO administra miembros ni otros agentes: es
 *   quien vende, no quien organiza la empresa.
 * - EDITOR toca contenido, incluido branding, pero no ve leads ni analítica:
 *   suele ser alguien externo (una agencia de marketing) y los leads son datos
 *   personales de terceros.
 * - VIEWER sólo mira. Es el rol por defecto seguro.
 *
 * `listing.remove` está restringido a partir de MANAGER a propósito: dar de
 * baja publicaciones ajenas es la acción destructiva más fácil de cometer.
 */
const CAPACIDADES_POR_ROL: Readonly<Record<Role, readonly Capability[]>> = Object.freeze({
  OWNER: CAPABILITIES,
  ADMIN: [
    "organization.view",
    "organization.edit",
    "organization.branding.edit",
    "organization.members.manage",
    "branch.manage",
    "agent.manage",
    "listing.view",
    "listing.create",
    "listing.edit",
    "listing.pause",
    "listing.remove",
    "listing.assign_agent",
    "lead.view",
    "analytics.view",
  ],
  MANAGER: [
    "organization.view",
    "branch.manage",
    "agent.manage",
    "listing.view",
    "listing.create",
    "listing.edit",
    "listing.pause",
    "listing.remove",
    "listing.assign_agent",
    "lead.view",
    "analytics.view",
  ],
  AGENT: [
    "organization.view",
    "listing.view",
    "listing.create",
    "listing.edit",
    "listing.pause",
    "lead.view",
  ],
  EDITOR: [
    "organization.view",
    "organization.branding.edit",
    "listing.view",
    "listing.edit",
  ],
  VIEWER: ["organization.view", "listing.view"],
});

export function capacidadesDeRol(rol: Role): readonly Capability[] {
  return CAPACIDADES_POR_ROL[rol] ?? [];
}

// --- actor -----------------------------------------------------------------

/**
 * La pertenencia de un usuario a una organización.
 *
 * `agentId` conecta al usuario con su ficha profesional cuando existe, y es lo
 * que permite la regla "un agente edita lo suyo": ver `esDuenoDelRecurso`.
 */
export type Membership = {
  organizationId: OrganizationId;
  role: Role;
  agentId: AgentId | null;
  /** Una membresía suspendida existe pero no habilita nada. */
  suspended: boolean;
};

/**
 * Quién pide hacer algo.
 *
 * `ANONYMOUS` es un actor de primera clase, no la ausencia de actor: casi todo
 * ERETZ se usa sin cuenta, y modelarlo como `null` llevaría a `?.` por todos
 * lados y, tarde o temprano, a un permiso concedido por un opcional mal leído.
 */
export type Actor =
  | { kind: "ANONYMOUS" }
  | { kind: "USER"; userId: UserId; memberships: readonly Membership[] };

/**
 * Actor de servicio: procesos internos (el importador, el scraper).
 *
 * NO existe como variante de `Actor` a propósito. Un actor de servicio que
 * pasara por `can()` sería un `if` que devuelve true temprano, y ese `if` es
 * exactamente el que alguien reutiliza mal. Los procesos internos no pasan por
 * este motor: corren fuera del camino de pedido, con sus propias guardas.
 */

// --- recursos --------------------------------------------------------------

/**
 * Sobre qué se actúa.
 *
 * El `organizationId` de cada variante es el del recurso YA CARGADO. Ver la
 * regla 2 del encabezado: si sale del pedido, el motor no protege nada.
 */
export type RecursoContext =
  | { kind: "ORGANIZATION"; organizationId: OrganizationId }
  | { kind: "BRANCH"; organizationId: OrganizationId; branchId: BranchId }
  | {
      kind: "LISTING";
      /** null = publicación sin dueño (scrapeada, no reclamada). */
      organizationId: OrganizationId | null;
      listingId: ListingId;
      /** El agente asignado, si lo hay. Habilita "editar lo mío". */
      assignedAgentId: AgentId | null;
    }
  | { kind: "AGENT"; organizationId: OrganizationId; agentId: AgentId };

/** El tenant dueño del recurso, o null si no tiene. */
export function tenantDelRecurso(r: RecursoContext): OrganizationId | null {
  return r.organizationId;
}

// --- el motor --------------------------------------------------------------

/**
 * Membresía activa del actor en esa organización, si existe.
 *
 * Devuelve null para anónimos, para suspendidos y para quien no pertenece. Los
 * tres casos son "no", y distinguirlos acá sólo invitaría a tratarlos distinto.
 */
export function membresiaEn(actor: Actor, org: OrganizationId | null): Membership | null {
  if (org === null) return null;
  if (actor.kind !== "USER") return null;
  const m = actor.memberships.find((x) => x.organizationId === org);
  if (!m || m.suspended) return null;
  return m;
}

/**
 * ¿El actor es el responsable directo del recurso?
 *
 * Permite que un AGENT edite la publicación que tiene asignada sin darle
 * `listing.edit` sobre todas las de la organización. No concede nada por sí
 * sola: siempre se combina con una capacidad.
 */
function esDuenoDelRecurso(m: Membership, r: RecursoContext): boolean {
  if (m.agentId === null) return false;
  if (r.kind === "LISTING") return r.assignedAgentId === m.agentId;
  if (r.kind === "AGENT") return r.agentId === m.agentId;
  return false;
}

/**
 * Capacidades que un AGENT ejerce sólo sobre lo propio.
 *
 * Sobre recursos de la organización que no le fueron asignados, no las tiene.
 */
const SOLO_SOBRE_LO_PROPIO: readonly Capability[] = Object.freeze([
  "listing.edit",
  "listing.pause",
]);

/**
 * ¿Puede el actor ejecutar la acción sobre el recurso?
 *
 * Único punto de decisión. Todo camino que no encuentre una razón afirmativa
 * termina en false.
 */
export function can(actor: Actor, accion: Capability, recurso: RecursoContext): boolean {
  // Una capacidad desconocida no se concede jamás. Protege contra un typo en el
  // sitio de llamada, que si no pasaría silenciosamente.
  if (!CAPABILITIES.includes(accion)) return false;

  const tenant = tenantDelRecurso(recurso);

  // Recurso sin dueño (una publicación scrapeada no reclamada): nadie la
  // administra. Es el estado de las 257k de hoy, y el "no" acá es lo que impide
  // que reclamar una organización cualquiera dé poder sobre catálogo ajeno.
  if (tenant === null) return false;

  const m = membresiaEn(actor, tenant);
  // Sin membresía activa en el tenant DUEÑO del recurso, no hay nada que hacer.
  // Cubre a la vez al anónimo, al suspendido, y al miembro de otra organización.
  if (m === null) return false;

  if (!capacidadesDeRol(m.role).includes(accion)) return false;

  // El rol la tiene, pero si es una capacidad acotada a lo propio, el AGENT
  // sólo la ejerce sobre lo suyo.
  if (m.role === "AGENT" && SOLO_SOBRE_LO_PROPIO.includes(accion)) {
    return esDuenoDelRecurso(m, recurso);
  }

  return true;
}

/**
 * Variante que explica la negativa.
 *
 * Un `false` pelado no se puede depurar ni mostrar. El motivo es para logs y
 * mensajes internos; nunca para exponer a un usuario anónimo cuál era el tenant
 * dueño de un recurso, que sería filtrar información.
 */
export type Veredicto = { permitido: true } | { permitido: false; motivo: string };

export function canConMotivo(actor: Actor, accion: Capability, recurso: RecursoContext): Veredicto {
  if (!CAPABILITIES.includes(accion)) return { permitido: false, motivo: "capacidad desconocida" };

  const tenant = tenantDelRecurso(recurso);
  if (tenant === null) return { permitido: false, motivo: "el recurso no pertenece a ninguna organización" };

  if (actor.kind !== "USER") return { permitido: false, motivo: "actor anónimo" };

  const cruda = actor.memberships.find((x) => x.organizationId === tenant);
  if (!cruda) return { permitido: false, motivo: "sin membresía en la organización dueña del recurso" };
  if (cruda.suspended) return { permitido: false, motivo: "membresía suspendida" };

  if (!capacidadesDeRol(cruda.role).includes(accion)) {
    return { permitido: false, motivo: `el rol ${cruda.role} no tiene ${accion}` };
  }

  if (cruda.role === "AGENT" && SOLO_SOBRE_LO_PROPIO.includes(accion) && !esDuenoDelRecurso(cruda, recurso)) {
    return { permitido: false, motivo: "un agente sólo puede hacerlo sobre lo que tiene asignado" };
  }

  return { permitido: true };
}
