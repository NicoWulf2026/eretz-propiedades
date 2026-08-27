import { describe, expect, it } from "vitest";
import type { ModerationSignal } from "./moderation";
import {
  GATE_CLASSIFICATIONS,
  GATE_VISIBLES,
  type EntradaDeGate,
  clasificarParaGate,
  difiereDelActual,
  gateEsVisible,
} from "./quality-gate-inputs";

const señal = (code: string): ModerationSignal => ({
  code,
  severity: "HIGH",
  evidence: "x",
  explanation: "y",
});

function entrada(o: Partial<EntradaDeGate> = {}): EntradaDeGate {
  return {
    propertyId: "123",
    moderation: "ALLOW",
    band: "ALTA",
    overall: 0.9,
    signals: [],
    sourceAvailable: true,
    ...o,
  };
}

describe("compatibilidad con el Gate actual", () => {
  it("conserva las cinco clasificaciones", () => {
    expect(GATE_CLASSIFICATIONS).toHaveLength(5);
    expect(GATE_CLASSIFICATIONS).toContain("PUBLICABLE_COMPLETE");
    expect(GATE_CLASSIFICATIONS).toContain("SOURCE_UNAVAILABLE");
  });

  it("conserva exactamente qué es visible", () => {
    // Cambiarlo alteraría qué se ve en el sitio.
    expect([...GATE_VISIBLES]).toEqual(["PUBLICABLE_COMPLETE", "PUBLICABLE_INCOMPLETE"]);
    for (const c of GATE_CLASSIFICATIONS) {
      expect(gateEsVisible(c)).toBe(GATE_VISIBLES.includes(c));
    }
  });
});

describe("traducción", () => {
  it("una fuente caída no vuelve mala a la propiedad", () => {
    // Habla de nuestra capacidad de verla, no de la publicación.
    const r = clasificarParaGate(entrada({ sourceAvailable: false, moderation: "ALLOW" }));
    expect(r.classification).toBe("SOURCE_UNAVAILABLE");
    expect(r.reasonCodes).toEqual(["FUENTE_NO_DISPONIBLE"]);
  });

  it("la fuente caída manda incluso sobre un rechazo", () => {
    const r = clasificarParaGate(entrada({ sourceAvailable: false, moderation: "REJECT" }));
    expect(r.classification).toBe("SOURCE_UNAVAILABLE");
  });

  it("un rechazo se traduce a INVALID y no se ve", () => {
    const r = clasificarParaGate(entrada({ moderation: "REJECT", signals: [señal("DUPLICADO_CONFIRMADO")] }));
    expect(r.classification).toBe("INVALID");
    expect(r.visible).toBe(false);
  });

  it("una revisión se traduce a REVIEW_REQUIRED y tampoco se ve", () => {
    expect(clasificarParaGate(entrada({ moderation: "REVIEW" })).classification).toBe("REVIEW_REQUIRED");
  });

  it("la banda sólo distingue completa de incompleta, y las dos se ven", () => {
    const alta = clasificarParaGate(entrada({ band: "ALTA" }));
    const baja = clasificarParaGate(entrada({ band: "BAJA" }));
    expect(alta.classification).toBe("PUBLICABLE_COMPLETE");
    expect(baja.classification).toBe("PUBLICABLE_INCOMPLETE");
    expect(alta.visible).toBe(true);
    expect(baja.visible).toBe(true);
  });

  it("una banda baja nunca oculta por sí sola", () => {
    // Sería sacar del catálogo publicaciones reales por tener pocas fotos.
    for (const band of ["ALTA", "MEDIA", "BAJA"] as const) {
      expect(clasificarParaGate(entrada({ band })).visible).toBe(true);
    }
  });
});

describe("reason codes", () => {
  it("acompañan la clasificación, que es lo que hoy falta", () => {
    // Hoy el Gate dice INVALID sin decir por qué, y no hay respuesta cuando una
    // inmobiliaria pregunta por qué no se ve su propiedad.
    const r = clasificarParaGate(
      entrada({ moderation: "REVIEW", signals: [señal("CUBIERTA_MAYOR_QUE_TOTAL"), señal("SIN_CONTACTO")] }),
    );
    expect(r.reasonCodes).toEqual(["CUBIERTA_MAYOR_QUE_TOTAL", "SIN_CONTACTO"]);
  });

  it("preserva el id de la propiedad", () => {
    expect(clasificarParaGate(entrada({ propertyId: "999" })).propertyId).toBe("999");
  });
});

describe("comparación OLD vs NEW", () => {
  it("detecta una diferencia con la clasificación vigente", () => {
    // Antes de reemplazar la generación del manifiesto hay que explicar cada
    // diferencia, no confiar en que el modelo nuevo es mejor.
    expect(difiereDelActual("INVALID", "PUBLICABLE_COMPLETE")).toBe(true);
    expect(difiereDelActual("INVALID", "INVALID")).toBe(false);
  });
});

describe("determinismo", () => {
  it("la misma entrada da la misma clasificación", () => {
    const e = entrada({ moderation: "REVIEW", signals: [señal("A")] });
    expect(clasificarParaGate(e)).toEqual(clasificarParaGate(e));
  });
});
