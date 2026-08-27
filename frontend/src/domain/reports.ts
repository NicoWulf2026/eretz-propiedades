// Expedientes de reporte y corrección.
//
// Hoy `/api/reports` y `/api/claims` reciben y responden, pero no hay
// expediente: no hay estado, ni cola, ni auditoría, ni forma de que quien
// reportó sepa qué pasó. Este módulo define eso; nada se persiste todavía.
//
// ---------------------------------------------------------------------------
// EL ANTIABUSO ACTUAL NO CAMBIA, Y NO ES LO QUE PARECE
// ---------------------------------------------------------------------------
//
// `lib/abuse/` limita por tasa y deduplica EN MEMORIA, por proceso. En
// serverless hay muchos procesos y se reciclan solos, así que el límite real es
// "N por ventana por instancia viva", no "N por ventana".
//
// Es un badén, no un control: frena el envío repetido de alguien apurado o un
// script torpe. No frena a quien quiera saturar el sistema a propósito. Se
// documenta como `BASIC_LOCAL_MITIGATION` y no se lo presenta como otra cosa,
// porque la mentira cómoda acá es creer que el problema está resuelto y
// descubrir que no cuando alguien lo prueba.
//
// Un control de verdad necesita estado compartido, y eso es infraestructura
// que hoy no se agrega.

import type { ListingId, OrganizationId, ReportId, UserId } from "./ids";

/** Nivel real de protección del antiabuso vigente. */
export const NIVEL_ANTIABUSO = "BASIC_LOCAL_MITIGATION" as const;

export const REPORT_REASONS = [
  "NO_EXISTE",
  "YA_NO_DISPONIBLE",
  "PRECIO_INCORRECTO",
  "DATOS_INCORRECTOS",
  "FOTOS_NO_CORRESPONDEN",
  "DUPLICADA",
  "CONTENIDO_INAPROPIADO",
  "ES_MIA_Y_NO_AUTORICE",
  "DATOS_PERSONALES",
  "OTRO",
] as const;
export type ReportReason = (typeof REPORT_REASONS)[number];

/**
 * Motivos que se atienden antes que el resto.
 *
 * No es una jerarquía de importancia: son los que involucran a una persona
 * concreta perjudicada ahora —sus datos publicados, su propiedad publicada sin
 * permiso— y donde cada día de demora es daño que sigue ocurriendo. Un precio
 * desactualizado también hay que corregirlo, pero no le pasa a nadie en
 * particular.
 */
export const MOTIVOS_PRIORITARIOS: readonly ReportReason[] = Object.freeze([
  "DATOS_PERSONALES",
  "ES_MIA_Y_NO_AUTORICE",
  "CONTENIDO_INAPROPIADO",
]);

export function esPrioritario(r: ReportReason): boolean {
  return MOTIVOS_PRIORITARIOS.includes(r);
}

export const REPORT_STATUSES = [
  "RECEIVED",
  "TRIAGED",
  "NEEDS_INFO",
  "ACCEPTED",
  "REJECTED",
  "RESOLVED",
] as const;
export type ReportStatus = (typeof REPORT_STATUSES)[number];

/**
 * Transiciones válidas. Deny by default, como el resto del dominio.
 *
 * `ACCEPTED` y `RESOLVED` están separados a propósito: aceptar es decidir que
 * el reporte tiene razón; resolver es haber hecho el cambio. Entre los dos hay
 * trabajo real, y colapsarlos haría imposible responder "¿cuántos aceptamos y
 * todavía no arreglamos?", que es la métrica que importa.
 *
 * `REJECTED` no es terminal: quien reportó puede aportar algo que cambie la
 * decisión, y obligarlo a abrir otro expediente perdería el hilo.
 */
export const TRANSICIONES_REPORTE: Readonly<Record<ReportStatus, readonly ReportStatus[]>> =
  Object.freeze({
    RECEIVED: ["TRIAGED", "REJECTED"],
    TRIAGED: ["NEEDS_INFO", "ACCEPTED", "REJECTED"],
    NEEDS_INFO: ["TRIAGED", "REJECTED"],
    ACCEPTED: ["RESOLVED"],
    REJECTED: ["TRIAGED"],
    RESOLVED: [],
  });

export function puedeTransicionarReporte(desde: ReportStatus, hacia: ReportStatus): boolean {
  return TRANSICIONES_REPORTE[desde]?.includes(hacia) ?? false;
}

export function esReporteTerminal(e: ReportStatus): boolean {
  return TRANSICIONES_REPORTE[e].length === 0;
}

export type ReportEvidence = {
  kind: "TEXT" | "URL" | "SCREENSHOT" | "DOCUMENT";
  /** Referencia, no el contenido. */
  reference: string;
  addedAt: string;
};

export type ReportDecision = {
  status: Extract<ReportStatus, "ACCEPTED" | "REJECTED">;
  /** Motivo, para poder comunicárselo a quien reportó. */
  rationale: string;
  decidedByUserId: UserId;
  decidedAt: string;
};

/**
 * Una entrada de auditoría. Sólo se agrega, nunca se modifica ni se borra.
 *
 * Es lo que permite responder más adelante quién decidió qué y cuándo. Un
 * expediente que sólo guarda su estado actual no puede reconstruir cómo llegó
 * ahí, que es justo lo que se pregunta cuando algo salió mal.
 */
export type AuditEntry = {
  at: string;
  actorUserId: UserId | null;
  action: string;
  from: ReportStatus | null;
  to: ReportStatus | null;
  note: string | null;
};

export type ReportCase = {
  id: ReportId;
  listingId: ListingId | null;
  organizationId: OrganizationId | null;
  reason: ReportReason;
  status: ReportStatus;
  /** Quién reportó, si tenía cuenta. Anónimo es válido y frecuente. */
  reporterUserId: UserId | null;
  /** Descripción libre de quien reporta. */
  description: string | null;
  evidence: readonly ReportEvidence[];
  decision: ReportDecision | null;
  audit: readonly AuditEntry[];
  createdAt: string;
  updatedAt: string;
};

export function problemasDeExpediente(c: ReportCase): string[] {
  const problemas: string[] = [];

  if ((c.status === "ACCEPTED" || c.status === "REJECTED") && c.decision === null) {
    problemas.push(`un expediente ${c.status} necesita una decisión registrada`);
  }
  if (c.decision && c.decision.status !== "ACCEPTED" && c.decision.status !== "REJECTED") {
    problemas.push("la decisión sólo puede ser aceptar o rechazar");
  }
  if (c.status === "RESOLVED" && c.decision?.status !== "ACCEPTED") {
    // Resolver algo que no se aceptó no significa nada.
    problemas.push("sólo se resuelve un expediente aceptado");
  }
  if (c.audit.length === 0) {
    problemas.push("todo expediente arranca con al menos una entrada de auditoría");
  }
  if (c.listingId === null && c.organizationId === null) {
    problemas.push("un reporte tiene que apuntar a algo");
  }
  return problemas;
}

/**
 * Aplica una transición y deja rastro.
 *
 * Devuelve un expediente nuevo en vez de mutar: un expediente mutado en el
 * lugar puede quedar a medio actualizar si algo falla entre medio, y el
 * historial es justamente lo que no puede quedar a medias.
 */
export class TransicionDeReporteInvalida extends Error {
  constructor(readonly desde: ReportStatus, readonly hacia: ReportStatus) {
    super(`Transición de reporte inválida: ${desde} → ${hacia}`);
    this.name = "TransicionDeReporteInvalida";
  }
}

export function transicionarReporte(
  c: ReportCase,
  hacia: ReportStatus,
  actorUserId: UserId | null,
  at: string,
  note: string | null = null,
): ReportCase {
  if (!puedeTransicionarReporte(c.status, hacia)) {
    throw new TransicionDeReporteInvalida(c.status, hacia);
  }
  return {
    ...c,
    status: hacia,
    updatedAt: at,
    audit: [
      ...c.audit,
      { at, actorUserId, action: "STATUS_CHANGE", from: c.status, to: hacia, note },
    ],
  };
}

/**
 * Orden de atención de una cola de expedientes.
 *
 * Primero los prioritarios, después los más viejos. Sin la segunda regla, un
 * expediente sin prioridad puede quedar al fondo para siempre mientras entren
 * otros.
 */
export function ordenarCola(casos: readonly ReportCase[]): ReportCase[] {
  return [...casos].sort((a, b) => {
    const pa = esPrioritario(a.reason) ? 0 : 1;
    const pb = esPrioritario(b.reason) ? 0 : 1;
    return pa - pb || a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id);
  });
}

/** Expedientes abiertos: los que todavía esperan algo de alguien. */
export function estaAbierto(c: ReportCase): boolean {
  return c.status !== "RESOLVED";
}
