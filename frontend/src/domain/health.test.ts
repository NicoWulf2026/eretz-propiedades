import { describe, expect, it } from "vitest";
import { HEALTH_STATUSES, type Dependencia, estadoPublico, evaluarEstado, permiteUso } from "./health";

const dep = (nombre: string, critica: boolean, disponible: boolean): Dependencia => ({
  nombre,
  critica,
  disponible,
  detalle: disponible ? null : "no responde",
});

describe("degradado es un estado, no un error suave", () => {
  it("todo disponible es sano", () => {
    const e = evaluarEstado([dep("base", true, true), dep("reportes", false, true)]);
    expect(e.status).toBe("HEALTHY");
    expect(e.afectadas).toEqual([]);
  });

  it("sin base no hay producto", () => {
    const e = evaluarEstado([dep("base", true, false), dep("reportes", false, true)]);
    expect(e.status).toBe("UNAVAILABLE");
    expect(e.resumen).toMatch(/sin base/);
  });

  it("sin el writer de reportes todo lo demás anda", () => {
    const e = evaluarEstado([dep("base", true, true), dep("reportes", false, false)]);
    expect(e.status).toBe("DEGRADED");
    expect(e.afectadas).toEqual(["reportes"]);
    expect(permiteUso(e.status)).toBe(true);
  });

  it("una crítica caída manda sobre las no críticas", () => {
    const e = evaluarEstado([dep("base", true, false), dep("reportes", false, false)]);
    expect(e.status).toBe("UNAVAILABLE");
    expect(e.afectadas).toEqual(["base", "reportes"]);
  });

  it("sólo UNAVAILABLE impide usar el sitio", () => {
    for (const s of HEALTH_STATUSES) {
      expect(permiteUso(s)).toBe(s !== "UNAVAILABLE");
    }
  });
});

describe("una comprobación que no corrió no es salud perfecta", () => {
  it("sin dependencias devuelve UNAVAILABLE, no HEALTHY", () => {
    // Reportar salud perfecta ahí es la forma de que un monitoreo roto parezca
    // un sistema sano.
    const e = evaluarEstado([]);
    expect(e.status).toBe("UNAVAILABLE");
    expect(e.resumen).toMatch(/no se pudo evaluar/);
  });
});

describe("la versión pública no dice de más", () => {
  it("expone el estado y nada más", () => {
    // Un /health que enumera dependencias le dice a cualquiera qué usa el
    // sistema y cuándo está débil.
    const e = evaluarEstado([dep("base", true, false), dep("blob", false, false)]);
    const publico = estadoPublico(e);
    expect(Object.keys(publico)).toEqual(["status"]);
    expect(JSON.stringify(publico)).not.toContain("base");
    expect(JSON.stringify(publico)).not.toContain("blob");
  });
});

describe("determinismo", () => {
  it("ordena las afectadas y no depende del orden de entrada", () => {
    const a = evaluarEstado([dep("z", false, false), dep("a", false, false), dep("base", true, true)]);
    const b = evaluarEstado([dep("a", false, false), dep("base", true, true), dep("z", false, false)]);
    expect(a).toEqual(b);
    expect(a.afectadas).toEqual(["a", "z"]);
  });
});
