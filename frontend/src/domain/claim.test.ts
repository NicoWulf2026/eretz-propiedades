import { describe, expect, it } from "vitest";
import { claimId, organizationId, userId } from "./ids";
import {
  CLAIM_STATUSES,
  EVIDENCE_KINDS,
  FUERZA_POR_EVIDENCIA,
  TRANSICIONES_CLAIM,
  type Claim,
  type ClaimEvidence,
  type ClaimStatus,
  type EvidenceKind,
  decidirClaim,
  esClaimTerminal,
  otorgaControl,
  puedeAprobarse,
  puedeTransicionarClaim,
} from "./claim";

function ev(kind: EvidenceKind, confirmed = true): ClaimEvidence {
  return { kind, confirmed, confirmedAt: confirmed ? "2026-08-01" : null, reference: "ref-1" };
}

function claim(status: ClaimStatus): Claim {
  return {
    id: claimId("c-1"),
    organizationId: organizationId("org-1"),
    claimantUserId: userId("u-1"),
    status,
    evidence: [],
    createdAt: "2026-08-01",
    decidedAt: null,
    decidedByUserId: null,
    rejectionReason: null,
  };
}

describe("fuerza de la evidencia", () => {
  it("separa controlar un canal de conocer un dato", () => {
    // La distinción de la que depende todo el flujo.
    expect(FUERZA_POR_EVIDENCIA.EMAIL_CODE).toBe("CONTROLA_EL_CANAL");
    expect(FUERZA_POR_EVIDENCIA.PHONE_CODE).toBe("CONTROLA_EL_CANAL");
    expect(FUERZA_POR_EVIDENCIA.DOMAIN_TOKEN).toBe("CONTROLA_EL_CANAL");
    expect(FUERZA_POR_EVIDENCIA.TAX_ID).toBe("CONOCE_EL_DATO");
    expect(FUERZA_POR_EVIDENCIA.LICENSE).toBe("CONOCE_EL_DATO");
    expect(FUERZA_POR_EVIDENCIA.DOCUMENT).toBe("CONOCE_EL_DATO");
  });

  it("toda evidencia declarada tiene fuerza asignada", () => {
    for (const k of EVIDENCE_KINDS) {
      expect(FUERZA_POR_EVIDENCIA[k]).toBeDefined();
    }
  });
});

describe("decisión automática", () => {
  it("verifica cuando se probó control de un canal", () => {
    expect(decidirClaim([ev("EMAIL_CODE")]).siguiente).toBe("VERIFIED_AUTOMATIC");
    expect(decidirClaim([ev("PHONE_CODE")]).siguiente).toBe("VERIFIED_AUTOMATIC");
    expect(decidirClaim([ev("DOMAIN_TOKEN")]).siguiente).toBe("VERIFIED_AUTOMATIC");
  });

  it("nunca aprueba sola: lo más lejos que llega es verificar", () => {
    // La aprobación es un acto registrado aparte.
    for (const k of EVIDENCE_KINDS) {
      expect(decidirClaim([ev(k)]).siguiente).not.toBe("APPROVED");
    }
  });

  it("conocer el CUIT o la matrícula no alcanza", () => {
    // Un CUIT figura en cualquier factura; saberlo no prueba ser su titular.
    const d = decidirClaim([ev("TAX_ID"), ev("LICENSE")]);
    expect(d.siguiente).toBe("NEEDS_REVIEW");
    expect(d.motivo).toMatch(/conocer datos/);
  });

  it("un documento subido va siempre a revisión humana", () => {
    expect(decidirClaim([ev("DOCUMENT")]).siguiente).toBe("NEEDS_REVIEW");
  });

  it("una evidencia sin confirmar no cuenta", () => {
    // "Dijo que su email es X" no es "recibió el código en X".
    const d = decidirClaim([ev("EMAIL_CODE", false)]);
    expect(d.siguiente).toBe("NEEDS_REVIEW");
    expect(d.motivo).toMatch(/ninguna evidencia confirmada/);
  });

  it("sin evidencia va a revisión, nunca se verifica", () => {
    expect(decidirClaim([]).siguiente).toBe("NEEDS_REVIEW");
  });

  it("una organización con dueño no se reclama automáticamente", () => {
    // Quitarle el control a alguien es siempre decisión humana, por fuerte que
    // sea la evidencia.
    const d = decidirClaim([ev("EMAIL_CODE"), ev("DOMAIN_TOKEN")], true);
    expect(d.siguiente).toBe("NEEDS_REVIEW");
    expect(d.motivo).toMatch(/ya tiene dueño/);
  });

  it("es determinista: la misma evidencia da la misma decisión", () => {
    const e = [ev("EMAIL_CODE"), ev("TAX_ID")];
    expect(decidirClaim(e)).toEqual(decidirClaim(e));
  });

  it("siempre explica el motivo", () => {
    for (const k of EVIDENCE_KINDS) {
      expect(decidirClaim([ev(k)]).motivo.length).toBeGreaterThan(0);
    }
  });
});

describe("máquina de estados", () => {
  it("sólo APPROVED otorga control", () => {
    for (const s of CLAIM_STATUSES) {
      expect(otorgaControl(s)).toBe(s === "APPROVED");
    }
  });

  it("los tres finales son terminales", () => {
    for (const s of ["APPROVED", "REJECTED", "CANCELLED"] as const) {
      expect(esClaimTerminal(s)).toBe(true);
      for (const destino of CLAIM_STATUSES) {
        expect(puedeTransicionarClaim(s, destino)).toBe(false);
      }
    }
  });

  it("deny by default sobre la matriz completa", () => {
    for (const desde of CLAIM_STATUSES) {
      for (const hacia of CLAIM_STATUSES) {
        expect(puedeTransicionarClaim(desde, hacia)).toBe(TRANSICIONES_CLAIM[desde].includes(hacia));
      }
    }
  });

  it("no se puede aprobar directamente desde PENDING", () => {
    // Siempre pasa por verificación o por revisión.
    expect(puedeTransicionarClaim("PENDING", "APPROVED")).toBe(false);
  });

  it("una verificación automática puede mandarse igual a revisión", () => {
    expect(puedeTransicionarClaim("VERIFIED_AUTOMATIC", "NEEDS_REVIEW")).toBe(true);
  });
});

describe("aprobación", () => {
  it("lo verificado automáticamente puede aprobarse sin persona", () => {
    expect(puedeAprobarse(claim("VERIFIED_AUTOMATIC"), false)).toBe(true);
  });

  it("lo que está en revisión exige una persona", () => {
    expect(puedeAprobarse(claim("NEEDS_REVIEW"), false)).toBe(false);
    expect(puedeAprobarse(claim("NEEDS_REVIEW"), true)).toBe(true);
  });

  it("no se aprueba desde un estado que no lo permite", () => {
    for (const s of ["PENDING", "REJECTED", "CANCELLED", "APPROVED"] as const) {
      expect(puedeAprobarse(claim(s), true)).toBe(false);
    }
  });
});
