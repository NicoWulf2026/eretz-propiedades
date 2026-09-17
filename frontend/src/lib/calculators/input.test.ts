import { describe, expect, it } from "vitest";
import {
  esEntradaNumericaParcial,
  formatearDinero,
  formatearPorcentaje,
  formatearSuperficie,
  fraccionDesdePorcentaje,
  parsearNumero,
  porcentajeDesdeFraccion,
  problemaDeValor,
} from "./input";

describe("vacío no es cero", () => {
  it("un campo sin completar devuelve null", () => {
    // Con 0 la calculadora daría un resultado equivocado con aire de válido en
    // lugar de decir que falta un dato.
    for (const vacio of ["", "   ", "-", "."]) {
      expect(parsearNumero(vacio)).toBeNull();
    }
    expect(parsearNumero("0")).toBe(0);
  });

  it("nunca devuelve NaN ni Infinity", () => {
    // Son los dos valores que atraviesan los cálculos sin fallar y salen del
    // otro lado como resultado.
    for (const malo of ["abc", "1e999", "Infinity", "NaN", "1,2,3"]) {
      const r = parsearNumero(malo);
      expect(r === null || Number.isFinite(r)).toBe(true);
    }
    expect(parsearNumero("Infinity")).toBeNull();
    expect(parsearNumero("NaN")).toBeNull();
  });

  it("acepta coma decimal, que es como se escribe en castellano", () => {
    expect(parsearNumero("1,5")).toBe(1.5);
    expect(parsearNumero("1.5")).toBe(1.5);
  });

  it("acepta negativos donde el campo los permita", () => {
    expect(parsearNumero("-5")).toBe(-5);
  });
});

describe("qué se puede seguir escribiendo", () => {
  it("deja escribir un número a medias", () => {
    for (const parcial of ["", "1", "1.", "1,", "-", "-1", "0.0"]) {
      expect(esEntradaNumericaParcial(parcial)).toBe(true);
    }
  });

  it("no deja escribir lo que nunca será un número", () => {
    for (const malo of ["abc", "1a", "1..2", "1-2", "$5"]) {
      expect(esEntradaNumericaParcial(malo)).toBe(false);
    }
  });
});

describe("la conversión de porcentaje", () => {
  it("convierte lo que escribe una persona en lo que espera el dominio", () => {
    // `finance.ts` recibe fracciones: 0,08 para un 8%. Si esto falla, la cuota
    // sale por un factor de cien con toda la apariencia de estar bien.
    expect(fraccionDesdePorcentaje(8)).toBeCloseTo(0.08, 10);
    expect(fraccionDesdePorcentaje(0)).toBe(0);
    expect(fraccionDesdePorcentaje(100)).toBe(1);
  });

  it("propaga la ausencia en vez de convertirla en cero", () => {
    expect(fraccionDesdePorcentaje(null)).toBeNull();
  });

  it("cierra el círculo con la conversión inversa", () => {
    expect(porcentajeDesdeFraccion(fraccionDesdePorcentaje(6.5) as number)).toBeCloseTo(6.5, 10);
  });
});

describe("validación de rango", () => {
  it("un campo vacío no es un campo con error", () => {
    // Marcarlo en rojo apenas se abre la pantalla es hostil.
    expect(problemaDeValor(null, { min: 0 })).toBeNull();
  });

  it("rechaza negativos donde no corresponden", () => {
    expect(problemaDeValor(-1, { min: 0 })).toBe("No puede ser negativo");
  });

  it("rechaza porcentajes absurdos", () => {
    expect(problemaDeValor(500, { min: 0, max: 100 })).toMatch(/100 o menos/);
    expect(problemaDeValor(8, { min: 0, max: 100 })).toBeNull();
  });

  it("exige enteros donde corresponde", () => {
    expect(problemaDeValor(12.5, { entero: true })).toMatch(/entero/);
    expect(problemaDeValor(12, { entero: true })).toBeNull();
  });

  it("acepta lo que está dentro de rango", () => {
    expect(problemaDeValor(0, { min: 0, max: 12 })).toBeNull();
    expect(problemaDeValor(12, { min: 0, max: 12 })).toBeNull();
  });
});

describe("formateo", () => {
  it("muestra centavos sólo cuando existen y aportan", () => {
    // Una cuota de USD 599,55 pierde información como 600.
    expect(formatearDinero(599.55, "USD")).toBe("USD 599,55");
    // Un importe exacto no gana nada con un ",00" que sugiere una precisión
    // que no tiene.
    expect(formatearDinero(7_300, "USD")).toBe("USD 7.300");
    expect(formatearDinero(2_000, "USD")).toBe("USD 2.000");
    // Y por encima de diez mil los centavos son ruido.
    expect(formatearDinero(215_838.42, "USD")).toContain("215.838");
    expect(formatearDinero(215_838.42, "USD")).not.toContain(",42");
  });

  it("respeta la moneda elegida sin convertir", () => {
    expect(formatearDinero(1000, "ARS")).toContain("ARS");
    expect(formatearDinero(1000, "USD")).toContain("USD");
  });

  it("formatea porcentajes desde la fracción", () => {
    expect(formatearPorcentaje(0.06)).toBe("6,0%");
    expect(formatearPorcentaje(0.048)).toBe("4,8%");
  });

  it("muestra un porcentaje negativo como negativo", () => {
    // Una rentabilidad negativa es un resultado válido y hay que verlo.
    expect(formatearPorcentaje(-0.02)).toContain("-2,0%");
  });

  it("formatea superficies con unidad", () => {
    expect(formatearSuperficie(70)).toBe("70 m²");
  });

  it("maneja el cero sin caso especial", () => {
    expect(formatearDinero(0, "USD")).toBe("USD 0");
    expect(formatearPorcentaje(0)).toBe("0,0%");
  });
});
