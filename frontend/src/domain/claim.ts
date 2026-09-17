// RECLAMACIÓN: alguien dice "esta inmobiliaria es mía" y hay que decidir.
//
// Es el flujo con más consecuencias de todo ERETZ, y conviene ser explícito
// sobre por qué: aprobar una reclamación entrega control editorial sobre
// contenido público. Un falso positivo no es un inconveniente administrativo,
// es una persona editando la ficha de un negocio ajeno —cambiando su teléfono,
// por ejemplo— con la apariencia de legitimidad que da la plataforma.
//
// El sesgo del diseño, entonces, es hacia el falso negativo: ante la duda, a
// revisión humana. Que un dueño legítimo espere dos días es un costo; que un
// tercero tome control de un negocio ajeno, no tiene arreglo posterior.
//
// ---------------------------------------------------------------------------
// LA FUERZA DE LA EVIDENCIA NO ES UNA ESCALA, SON DOS CATEGORÍAS
// ---------------------------------------------------------------------------
//
// La distinción que decide todo es si la evidencia se puede FALSIFICAR por
// alguien que sólo mira la web pública:
//
//   - El sitio de la inmobiliaria publica el teléfono y el email. Que alguien
//     los sepa no prueba nada: están a la vista de cualquiera.
//   - Recibir un código EN ese email o EN ese teléfono sí prueba algo: hay que
//     controlar la casilla o la línea.
//
// Por eso `CONOCE_EL_DATO` nunca aprueba sola. Sólo `CONTROLA_EL_CANAL` puede,
// y aun así con condiciones.

import type { ClaimId, OrganizationId, UserId } from "./ids";

export const CLAIM_STATUSES = [
  "PENDING",
  "VERIFIED_AUTOMATIC",
  "NEEDS_REVIEW",
  "APPROVED",
  "REJECTED",
  "CANCELLED",
] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

/**
 * Transiciones válidas. Deny by default, como el ciclo de publicación.
 *
 * `VERIFIED_AUTOMATIC` es un estado intermedio, no final: la verificación
 * automática salió bien, pero la aprobación sigue siendo un acto registrado.
 * Separarlos permite, si más adelante hiciera falta, exigir revisión también
 * en casos automáticos sin rehacer el modelo.
 */
export const TRANSICIONES_CLAIM: Readonly<Record<ClaimStatus, readonly ClaimStatus[]>> = Object.freeze({
  PENDING: ["VERIFIED_AUTOMATIC", "NEEDS_REVIEW", "REJECTED", "CANCELLED"],
  VERIFIED_AUTOMATIC: ["APPROVED", "NEEDS_REVIEW", "CANCELLED"],
  NEEDS_REVIEW: ["APPROVED", "REJECTED", "CANCELLED"],
  // Terminales. Revocar un acceso ya otorgado es otra operación, con su propio
  // registro de auditoría: no es "mover la reclamación para atrás".
  APPROVED: [],
  REJECTED: [],
  CANCELLED: [],
});

export function puedeTransicionarClaim(desde: ClaimStatus, hacia: ClaimStatus): boolean {
  return TRANSICIONES_CLAIM[desde]?.includes(hacia) ?? false;
}

export function esClaimTerminal(estado: ClaimStatus): boolean {
  return TRANSICIONES_CLAIM[estado].length === 0;
}

/** ¿Este estado otorga control sobre la organización? Sólo uno. */
export function otorgaControl(estado: ClaimStatus): boolean {
  return estado === "APPROVED";
}

// --- evidencia -------------------------------------------------------------

export const EVIDENCE_KINDS = [
  "EMAIL_DOMAIN",
  "EMAIL_CODE",
  "PHONE_CODE",
  "DOMAIN_TOKEN",
  "TAX_ID",
  "LICENSE",
  "DOCUMENT",
] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

/**
 * ¿Qué prueba realmente cada tipo de evidencia?
 *
 *   CONTROLA_EL_CANAL  Demuestra control de algo que la organización controla:
 *                      su casilla, su teléfono, su dominio.
 *   CONOCE_EL_DATO     Demuestra saber algo que puede ser público o estar en un
 *                      papel. Un CUIT figura en facturas; una matrícula, en
 *                      registros. Saberlos no prueba ser su titular.
 */
export type FuerzaDeEvidencia = "CONTROLA_EL_CANAL" | "CONOCE_EL_DATO";

export const FUERZA_POR_EVIDENCIA: Readonly<Record<EvidenceKind, FuerzaDeEvidencia>> = Object.freeze({
  // El email termina en el dominio de la inmobiliaria Y se confirmó recibiéndolo.
  EMAIL_DOMAIN: "CONTROLA_EL_CANAL",
  EMAIL_CODE: "CONTROLA_EL_CANAL",
  PHONE_CODE: "CONTROLA_EL_CANAL",
  // Publicar un token en el DNS o en la web del dominio: control del dominio.
  DOMAIN_TOKEN: "CONTROLA_EL_CANAL",
  TAX_ID: "CONOCE_EL_DATO",
  LICENSE: "CONOCE_EL_DATO",
  // Un documento subido puede ser real o fabricado: sólo una persona decide.
  DOCUMENT: "CONOCE_EL_DATO",
});

export type ClaimEvidence = {
  kind: EvidenceKind;
  /**
   * Si la comprobación se completó con éxito.
   *
   * Una evidencia aportada pero no confirmada NO cuenta. Es la diferencia
   * entre "dijo que su email es X" y "recibió el código en X".
   */
  confirmed: boolean;
  confirmedAt: string | null;
  /**
   * Referencia a la prueba, nunca la prueba en sí. No se guarda el código, ni
   * el documento, ni el email completo en este objeto: sólo un puntero.
   */
  reference: string | null;
};

export type Claim = {
  id: ClaimId;
  organizationId: OrganizationId;
  claimantUserId: UserId;
  status: ClaimStatus;
  evidence: readonly ClaimEvidence[];
  createdAt: string;
  decidedAt: string | null;
  /** Quién decidió, cuando fue una persona. null si fue automático. */
  decidedByUserId: UserId | null;
  /** Motivo del rechazo, para poder comunicarlo. */
  rejectionReason: string | null;
};

// --- decisión --------------------------------------------------------------

export type DecisionDeClaim = {
  siguiente: ClaimStatus;
  motivo: string;
};

/**
 * Decide el estado siguiente de una reclamación recién presentada.
 *
 * Función pura y determinista: las mismas evidencias dan siempre la misma
 * decisión, que es lo que permite auditarla y explicarla a quien reclama.
 *
 * Nunca devuelve APPROVED: la aprobación es un acto aparte, con registro. Lo
 * más lejos que llega automáticamente es VERIFIED_AUTOMATIC.
 *
 * @param evidencias las presentadas con la reclamación
 * @param organizacionYaReclamada si otra persona ya tiene el control
 */
export function decidirClaim(
  evidencias: readonly ClaimEvidence[],
  organizacionYaReclamada = false,
): DecisionDeClaim {
  // Una organización con dueño no se reclama por la vía automática, por fuerte
  // que sea la evidencia: quitarle el control a alguien es siempre una decisión
  // humana. Se comprueba primero, antes que nada.
  if (organizacionYaReclamada) {
    return { siguiente: "NEEDS_REVIEW", motivo: "la organización ya tiene dueño" };
  }

  const confirmadas = evidencias.filter((e) => e.confirmed);
  if (confirmadas.length === 0) {
    return { siguiente: "NEEDS_REVIEW", motivo: "no hay ninguna evidencia confirmada" };
  }

  const controlaCanal = confirmadas.some((e) => FUERZA_POR_EVIDENCIA[e.kind] === "CONTROLA_EL_CANAL");
  if (!controlaCanal) {
    // Saber el CUIT o la matrícula no prueba ser su titular.
    return {
      siguiente: "NEEDS_REVIEW",
      motivo: "la evidencia demuestra conocer datos, no controlar canales de la organización",
    };
  }

  return { siguiente: "VERIFIED_AUTOMATIC", motivo: "control de un canal de la organización confirmado" };
}

/**
 * ¿Puede aprobarse esta reclamación?
 *
 * Separado de `decidirClaim` porque son momentos distintos: uno evalúa la
 * evidencia al presentarla, el otro autoriza el cambio de control. Un `NEEDS_REVIEW`
 * lo aprueba una persona; un `VERIFIED_AUTOMATIC` puede aprobarse solo.
 */
export function puedeAprobarse(claim: Claim, aprobadaPorPersona: boolean): boolean {
  if (!puedeTransicionarClaim(claim.status, "APPROVED")) return false;
  if (claim.status === "NEEDS_REVIEW") return aprobadaPorPersona;
  return true;
}
