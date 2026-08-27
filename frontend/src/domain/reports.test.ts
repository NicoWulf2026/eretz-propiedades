import { describe, expect, it } from "vitest";
import { listingId, reportId, userId } from "./ids";
import {
  MOTIVOS_PRIORITARIOS,
  NIVEL_ANTIABUSO,
  REPORT_STATUSES,
  TRANSICIONES_REPORTE,
  TransicionDeReporteInvalida,
  type ReportCase,
  type ReportReason,
  type ReportStatus,
  esPrioritario,
  esReporteTerminal,
  estaAbierto,
  ordenarCola,
  problemasDeExpediente,
  puedeTransicionarReporte,
  transicionarReporte,
} from "./reports";

function caso(o: Partial<ReportCase> = {}): ReportCase {
  return {
    id: reportId("r-1"),
    listingId: listingId("l-1"),
    organizationId: null,
    reason: "PRECIO_INCORRECTO",
    status: "RECEIVED",
    reporterUserId: null,
    description: "El precio está desactualizado",
    evidence: [],
    decision: null,
    audit: [{ at: "2026-08-01", actorUserId: null, action: "CREATED", from: null, to: "RECEIVED", note: null }],
    createdAt: "2026-08-01",
    updatedAt: "2026-08-01",
    ...o,
  };
}

describe("el antiabuso se documenta como lo que es", () => {
  it("declara el nivel real de protección", () => {
    // En serverless el límite real es por instancia viva, no global: es un
    // badén, no un control.
    expect(NIVEL_ANTIABUSO).toBe("BASIC_LOCAL_MITIGATION");
  });
});

describe("prioridad", () => {
  it("prioriza lo que perjudica a una persona concreta ahora", () => {
    expect(esPrioritario("DATOS_PERSONALES")).toBe(true);
    expect(esPrioritario("ES_MIA_Y_NO_AUTORICE")).toBe(true);
    expect(esPrioritario("CONTENIDO_INAPROPIADO")).toBe(true);
  });

  it("un precio desactualizado importa, pero no le pasa a nadie en particular", () => {
    for (const r of ["PRECIO_INCORRECTO", "DUPLICADA", "YA_NO_DISPONIBLE", "OTRO"] as ReportReason[]) {
      expect(esPrioritario(r)).toBe(false);
    }
    expect(MOTIVOS_PRIORITARIOS).toHaveLength(3);
  });
});

describe("máquina de estados", () => {
  it("deny by default sobre la matriz completa", () => {
    for (const desde of REPORT_STATUSES) {
      for (const hacia of REPORT_STATUSES) {
        expect(puedeTransicionarReporte(desde, hacia)).toBe(
          TRANSICIONES_REPORTE[desde].includes(hacia),
        );
      }
    }
  });

  it("separa aceptar de resolver", () => {
    // Entre los dos hay trabajo real: colapsarlos haría imposible saber
    // cuántos se aceptaron y todavía no se arreglaron.
    expect(puedeTransicionarReporte("ACCEPTED", "RESOLVED")).toBe(true);
    expect(puedeTransicionarReporte("TRIAGED", "RESOLVED")).toBe(false);
    expect(puedeTransicionarReporte("RECEIVED", "RESOLVED")).toBe(false);
  });

  it("un rechazo puede reabrirse", () => {
    // Quien reportó puede aportar algo que cambie la decisión; obligarlo a
    // abrir otro expediente perdería el hilo.
    expect(puedeTransicionarReporte("REJECTED", "TRIAGED")).toBe(true);
    expect(esReporteTerminal("REJECTED")).toBe(false);
  });

  it("resuelto es el único terminal", () => {
    expect(esReporteTerminal("RESOLVED")).toBe(true);
    for (const s of REPORT_STATUSES.filter((x) => x !== "RESOLVED")) {
      expect(esReporteTerminal(s)).toBe(false);
    }
  });

  it("pedir información devuelve al triage, no salta a la decisión", () => {
    expect(puedeTransicionarReporte("NEEDS_INFO", "TRIAGED")).toBe(true);
    expect(puedeTransicionarReporte("NEEDS_INFO", "ACCEPTED")).toBe(false);
  });
});

describe("transición con auditoría", () => {
  it("deja rastro de cada cambio", () => {
    const c = transicionarReporte(caso(), "TRIAGED", userId("u-1"), "2026-08-02", "revisado");
    expect(c.status).toBe("TRIAGED");
    expect(c.audit).toHaveLength(2);
    expect(c.audit[1]).toMatchObject({ from: "RECEIVED", to: "TRIAGED", actorUserId: "u-1", note: "revisado" });
  });

  it("no muta el expediente original", () => {
    // Un expediente mutado en el lugar puede quedar a medias si algo falla, y
    // el historial es justo lo que no puede quedar a medias.
    const original = caso();
    const copia = structuredClone(original);
    transicionarReporte(original, "TRIAGED", null, "2026-08-02");
    expect(original).toEqual(copia);
  });

  it("actualiza la fecha de modificación", () => {
    const c = transicionarReporte(caso(), "TRIAGED", null, "2026-08-05");
    expect(c.updatedAt).toBe("2026-08-05");
  });

  it("falla con un error que dice qué se intentó", () => {
    try {
      transicionarReporte(caso(), "RESOLVED", null, "2026-08-02");
      expect.unreachable("debería haber fallado");
    } catch (e) {
      expect(e).toBeInstanceOf(TransicionDeReporteInvalida);
      expect((e as TransicionDeReporteInvalida).desde).toBe("RECEIVED");
    }
  });

  it("nunca borra entradas de auditoría", () => {
    let c = caso();
    for (const s of ["TRIAGED", "ACCEPTED", "RESOLVED"] as ReportStatus[]) {
      c = transicionarReporte(c, s, null, "2026-08-02");
    }
    expect(c.audit).toHaveLength(4);
    expect(c.audit[0].action).toBe("CREATED");
  });
});

describe("coherencia del expediente", () => {
  it("acepta uno bien formado", () => {
    expect(problemasDeExpediente(caso())).toEqual([]);
  });

  it("exige decisión registrada al aceptar o rechazar", () => {
    for (const status of ["ACCEPTED", "REJECTED"] as const) {
      expect(problemasDeExpediente(caso({ status }))[0]).toMatch(/decisión registrada/);
    }
  });

  it("sólo se resuelve lo aceptado", () => {
    const c = caso({
      status: "RESOLVED",
      decision: {
        status: "REJECTED",
        rationale: "no corresponde",
        decidedByUserId: userId("u-1"),
        decidedAt: "2026-08-02",
      },
    });
    expect(problemasDeExpediente(c).some((p) => /sólo se resuelve/.test(p))).toBe(true);
  });

  it("todo expediente arranca con auditoría", () => {
    expect(problemasDeExpediente(caso({ audit: [] }))).toContain(
      "todo expediente arranca con al menos una entrada de auditoría",
    );
  });

  it("un reporte tiene que apuntar a algo", () => {
    expect(problemasDeExpediente(caso({ listingId: null, organizationId: null }))).toContain(
      "un reporte tiene que apuntar a algo",
    );
  });

  it("acepta un reporte anónimo", () => {
    // Es válido y frecuente: no hay cuentas.
    expect(problemasDeExpediente(caso({ reporterUserId: null }))).toEqual([]);
  });
});

describe("cola de atención", () => {
  it("primero los prioritarios", () => {
    const cola = ordenarCola([
      caso({ id: reportId("a"), reason: "PRECIO_INCORRECTO", createdAt: "2026-01-01" }),
      caso({ id: reportId("b"), reason: "DATOS_PERSONALES", createdAt: "2026-08-01" }),
    ]);
    expect(cola.map((c) => c.id)).toEqual(["b", "a"]);
  });

  it("dentro de la misma prioridad, los más viejos", () => {
    // Sin esta regla, un expediente sin prioridad queda al fondo para siempre.
    const cola = ordenarCola([
      caso({ id: reportId("nuevo"), createdAt: "2026-08-01" }),
      caso({ id: reportId("viejo"), createdAt: "2026-01-01" }),
    ]);
    expect(cola.map((c) => c.id)).toEqual(["viejo", "nuevo"]);
  });

  it("es estable y determinista", () => {
    const casos = [caso({ id: reportId("b") }), caso({ id: reportId("a") })];
    expect(ordenarCola(casos).map((c) => c.id)).toEqual(["a", "b"]);
    expect(ordenarCola(casos)).toEqual(ordenarCola([...casos].reverse()));
  });

  it("no muta la entrada", () => {
    const casos = [caso({ id: reportId("b") }), caso({ id: reportId("a") })];
    ordenarCola(casos);
    expect(casos[0].id).toBe("b");
  });
});

describe("expedientes abiertos", () => {
  it("todo lo que no está resuelto sigue esperando algo", () => {
    for (const s of REPORT_STATUSES) {
      expect(estaAbierto(caso({ status: s }))).toBe(s !== "RESOLVED");
    }
  });
});
