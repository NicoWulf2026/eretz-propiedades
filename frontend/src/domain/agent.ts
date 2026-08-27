// Un AGENTE: la persona que comercializa una propiedad.
//
// Hoy en la base hay `agente_nombre`: un texto suelto sacado de la página. Eso
// NO es una persona, y la diferencia importa más de lo que parece.
//
// ---------------------------------------------------------------------------
// UN NOMBRE SCRAPEADO NO ES UNA IDENTIDAD
// ---------------------------------------------------------------------------
//
// De un nombre extraído sabemos exactamente una cosa: ese texto apareció en esa
// página. No sabemos si dos "Juan Pérez" en dos inmobiliarias son la misma
// persona (probablemente no), ni si "Ventas" o "Contacto" son personas (no lo
// son), ni si quien figura sigue trabajando ahí.
//
// Tratar ese texto como entidad tiene dos consecuencias malas y concretas:
//
//   - agrupar por nombre juntaría profesionales distintos bajo un perfil, con
//     el teléfono de uno y las propiedades de otro;
//   - publicar un perfil de una persona real construido por nosotros, sin que
//     ella lo sepa ni pueda corregirlo, es un problema de datos personales
//     antes que técnico.
//
// Por eso la identidad tiene estados, y el primero admite explícitamente que
// no sabemos quién es.

import type { AgentId, BranchId, OrganizationId, UserId } from "./ids";

export const AGENT_IDENTITY_STATUSES = ["EXTRACTED", "MATCHED", "CLAIMED", "VERIFIED"] as const;
export type AgentIdentityStatus = (typeof AGENT_IDENTITY_STATUSES)[number];

/**
 * Qué significa cada estado, para que nadie tenga que deducirlo:
 *
 *   EXTRACTED  Un texto que apareció en una página. Puede no ser una persona.
 *   MATCHED    Vinculamos varias apariciones a un mismo profesional, por
 *              señales (mismo teléfono en la misma inmobiliaria). Sigue siendo
 *              una inferencia nuestra.
 *   CLAIMED    La persona dijo "soy yo" y demostró lo suficiente.
 *   VERIFIED   Además comprobamos su identidad profesional (matrícula).
 */
export function esIdentidadInferida(s: AgentIdentityStatus): boolean {
  return s === "EXTRACTED" || s === "MATCHED";
}

/**
 * ¿Se puede mostrar un perfil público de este agente?
 *
 * Sólo cuando la persona lo reclamó. Deny by default, y por el motivo del
 * encabezado: publicar un perfil de alguien que no pidió tenerlo, armado con
 * datos que dedujimos, no es algo que se arregle después.
 *
 * Que el NOMBRE aparezca en una ficha —como aparece hoy, tal como vino de la
 * fuente— es distinto de publicar un PERFIL. Esto último es lo que se restringe.
 */
export function permitePerfilPublico(s: AgentIdentityStatus): boolean {
  return s === "CLAIMED" || s === "VERIFIED";
}

/**
 * Textos que casi nunca son personas.
 *
 * Se detectan para no crear entidades de agente a partir de una casilla
 * genérica. La lista es conservadora a propósito: ante la duda, se trata como
 * persona y queda en EXTRACTED, que no expone nada.
 */
const ETIQUETAS_NO_PERSONALES = [
  "ventas", "contacto", "informes", "consultas", "administracion", "administración",
  "info", "recepcion", "recepción", "atencion", "atención", "comercial", "alquileres",
];

/**
 * ¿Este texto parece una etiqueta funcional en vez de un nombre?
 *
 * No decide nada por sí solo: marca para que la creación de entidades lo
 * excluya y para que una revisión humana lo mire.
 */
export function pareceEtiquetaFuncional(nombre: string | null | undefined): boolean {
  const n = (nombre ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  if (!n) return false;
  return ETIQUETAS_NO_PERSONALES.some((e) => {
    const base = e.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return n === base || n.startsWith(`${base} `) || n.endsWith(` ${base}`);
  });
}

export type AgentContact = {
  phone: string | null;
  email: string | null;
};

/**
 * Matrícula profesional. En Argentina la otorgan los colegios provinciales, así
 * que el número solo no identifica: hace falta la jurisdicción.
 */
export type AgentLicense = {
  number: string;
  jurisdiction: string;
  verifiedAt: string | null;
};

export type Agent = {
  id: AgentId;
  identityStatus: AgentIdentityStatus;
  /** El nombre tal como se conoce. En EXTRACTED, tal como vino de la fuente. */
  displayName: string;
  contact: AgentContact;
  photoUrl: string | null;
  license: AgentLicense | null;
  organizationId: OrganizationId | null;
  branchId: BranchId | null;
  /** La cuenta de la persona, si reclamó el perfil. */
  userId: UserId | null;
  /** Zonas donde trabaja, declaradas por la persona. Nunca deducidas. */
  zones: readonly string[];
};

export function problemasDeAgente(a: Agent): string[] {
  const problemas: string[] = [];

  if (permitePerfilPublico(a.identityStatus) && a.userId === null) {
    problemas.push(`estado ${a.identityStatus} exige una cuenta asociada`);
  }
  if (esIdentidadInferida(a.identityStatus) && a.userId !== null) {
    problemas.push("una identidad inferida no puede tener cuenta asociada");
  }
  if (a.identityStatus === "VERIFIED" && a.license?.verifiedAt == null) {
    problemas.push("un agente verificado necesita matrícula verificada");
  }
  if (a.branchId !== null && a.organizationId === null) {
    problemas.push("no puede tener sucursal sin organización");
  }
  if (a.zones.length > 0 && esIdentidadInferida(a.identityStatus)) {
    // Las zonas las declara la persona. Deducirlas de dónde publica sería
    // inventar un dato que después se lee como afirmación suya.
    problemas.push("las zonas sólo puede declararlas la persona");
  }
  return problemas;
}
