import { describe, expect, it } from "vitest";
import {
  type Resultado,
  capacidadDeCompra,
  cashFlowMensual,
  costosDeOperacion,
  cuotaHipotecaria,
  precioPorM2,
  relacionCuotaIngreso,
  rentabilidadBruta,
  rentabilidadNeta,
  resumenCredito,
} from "./finance";

/** Extrae el valor de un resultado que debe haber salido bien. */
function valor<T>(r: Resultado<T>): T {
  if (!r.ok) throw new Error(`esperaba ok, vino: ${r.motivo}`);
  return r.valor;
}

describe("precio por m²", () => {
  it("divide precio por superficie", () => {
    expect(valor(precioPorM2(100_000, 50))).toBe(2_000);
  });

  it("no inventa un resultado cuando falta el dato", () => {
    // Nunca 0 en lugar de "no sé": un 0 se muestra como si fuera un precio.
    expect(precioPorM2(null, 50).ok).toBe(false);
    expect(precioPorM2(100_000, null).ok).toBe(false);
    expect(precioPorM2(100_000, 0).ok).toBe(false);
  });

  it("explica por qué no pudo", () => {
    const r = precioPorM2(null, 50);
    if (r.ok) expect.unreachable("no debería haber podido");
    else expect(r.motivo).toMatch(/precio/);
  });
});

describe("cuota hipotecaria", () => {
  it("coincide con el valor conocido del sistema francés", () => {
    // USD 100.000 al 6% anual a 30 años son USD 599,55 mensuales. Es el
    // ejemplo canónico del cálculo, y sirve de ancla contra un error de signo
    // o de conversión de tasa.
    const c = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 360 }));
    expect(c).toBeCloseTo(599.55, 2);
  });

  it("otro punto de control independiente", () => {
    // USD 200.000 al 4,5% a 20 años (240 meses) = USD 1.265,30.
    const c = valor(cuotaHipotecaria({ capital: 200_000, tasaAnual: 0.045, meses: 240 }));
    expect(c).toBeCloseTo(1265.3, 1);
  });

  it("con tasa cero reparte el capital en cuotas iguales", () => {
    // La fórmula se indefine en i=0: se trata aparte.
    expect(valor(cuotaHipotecaria({ capital: 120_000, tasaAnual: 0, meses: 120 }))).toBe(1_000);
  });

  it("a mayor plazo, menor cuota", () => {
    const corto = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 120 }));
    const largo = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 360 }));
    expect(largo).toBeLessThan(corto);
  });

  it("a mayor tasa, mayor cuota", () => {
    const baja = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.03, meses: 240 }));
    const alta = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.09, meses: 240 }));
    expect(alta).toBeGreaterThan(baja);
  });

  it("rechaza una tasa escrita como porcentaje", () => {
    // Escribir 8 en vez de 0,08 daría una cuota absurda con apariencia válida.
    const r = cuotaHipotecaria({ capital: 100_000, tasaAnual: 8, meses: 240 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toMatch(/fracción/);
  });

  it("rechaza plazos no enteros o nulos", () => {
    expect(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 0 }).ok).toBe(false);
    expect(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 12.5 }).ok).toBe(false);
    expect(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: -12 }).ok).toBe(false);
  });

  it("rechaza tasa negativa y capital no positivo", () => {
    expect(cuotaHipotecaria({ capital: 100_000, tasaAnual: -0.01, meses: 240 }).ok).toBe(false);
    expect(cuotaHipotecaria({ capital: 0, tasaAnual: 0.06, meses: 240 }).ok).toBe(false);
  });
});

describe("resumen del crédito", () => {
  it("los intereses son lo pagado menos el capital", () => {
    const r = valor(resumenCredito({ capital: 100_000, tasaAnual: 0.06, meses: 360 }));
    expect(r.totalPagado).toBeCloseTo(r.cuota * 360, 6);
    expect(r.interesesTotales).toBeCloseTo(r.totalPagado - 100_000, 6);
    // A 30 años al 6% se pagan más intereses que capital.
    expect(r.interesesTotales).toBeGreaterThan(100_000);
  });

  it("sin intereses no hay intereses", () => {
    const r = valor(resumenCredito({ capital: 120_000, tasaAnual: 0, meses: 120 }));
    expect(r.interesesTotales).toBeCloseTo(0, 6);
  });
});

describe("capacidad de compra", () => {
  it("es la inversa exacta de la cuota", () => {
    // La propiedad que más importa: si no cierra el círculo, una de las dos
    // está mal y las dos parecen razonables por separado.
    const cuota = valor(cuotaHipotecaria({ capital: 100_000, tasaAnual: 0.06, meses: 360 }));
    const capital = valor(capacidadDeCompra({ cuotaMaxima: cuota, tasaAnual: 0.06, meses: 360 }));
    expect(capital).toBeCloseTo(100_000, 4);
  });

  it("cierra el círculo también sin intereses", () => {
    const cuota = valor(cuotaHipotecaria({ capital: 60_000, tasaAnual: 0, meses: 120 }));
    expect(valor(capacidadDeCompra({ cuotaMaxima: cuota, tasaAnual: 0, meses: 120 }))).toBeCloseTo(60_000, 6);
  });

  it("aplica las mismas validaciones que la cuota", () => {
    expect(capacidadDeCompra({ cuotaMaxima: 1_000, tasaAnual: 8, meses: 240 }).ok).toBe(false);
    expect(capacidadDeCompra({ cuotaMaxima: 0, tasaAnual: 0.06, meses: 240 }).ok).toBe(false);
  });
});

describe("costos de una operación", () => {
  it("suma porcentajes y montos fijos", () => {
    const d = valor(
      costosDeOperacion(100_000, {
        comisionFraccion: 0.03,
        sellosFraccion: 0.018,
        escrituraFraccion: 0.02,
        montoFijo: 500,
      }),
    );
    // toBeCloseTo y no toBe: 0,018 × 100.000 da 1799,9999999999998 en coma
    // flotante. El módulo NO redondea a propósito —redondear moneda es cosa de
    // la presentación, y hacerlo acá arrastraría el error a cada suma—.
    expect(d.comision).toBeCloseTo(3_000, 6);
    expect(d.sellos).toBeCloseTo(1_800, 6);
    expect(d.escritura).toBeCloseTo(2_000, 6);
    expect(d.fijos).toBe(500);
    expect(d.total).toBeCloseTo(7_300, 6);
    expect(d.totalConPrecio).toBeCloseTo(107_300, 6);
  });

  it("sin conceptos, no hay costos", () => {
    // No hay porcentajes por defecto escondidos.
    const d = valor(costosDeOperacion(100_000));
    expect(d.total).toBe(0);
    expect(d.totalConPrecio).toBe(100_000);
  });

  it("rechaza un porcentaje escrito como entero", () => {
    // Poner 3 en vez de 0,03 daría una comisión de 300.000 sobre 100.000.
    const r = costosDeOperacion(100_000, { comisionFraccion: 3 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toMatch(/comisión/);
  });

  it("rechaza fracciones negativas", () => {
    expect(costosDeOperacion(100_000, { sellosFraccion: -0.01 }).ok).toBe(false);
    expect(costosDeOperacion(100_000, { montoFijo: -1 }).ok).toBe(false);
  });

  it("nombra el concepto que está mal", () => {
    const r = costosDeOperacion(100_000, { sellosFraccion: 2 });
    if (r.ok) expect.unreachable("no debería haber podido");
    else expect(r.motivo).toMatch(/sellado/);
  });
});

describe("rentabilidad", () => {
  it("la bruta es el alquiler anual sobre el precio", () => {
    // 500 mensuales sobre 100.000 = 6% anual.
    expect(valor(rentabilidadBruta(500, 100_000))).toBeCloseTo(0.06, 10);
  });

  it("la neta descuenta gastos y vacancia", () => {
    // 12 meses a 500 = 6.000; menos 100 mensuales de expensas = 4.800;
    // sobre 100.000 = 4,8%.
    const n = valor(
      rentabilidadNeta({ alquilerMensual: 500, precio: 100_000, gastosMensuales: 100 }),
    );
    expect(n).toBeCloseTo(0.048, 10);
  });

  it("la vacancia baja la renta y los gastos siguen corriendo", () => {
    // Un mes vacío: se cobran 11 meses pero se pagan 12 de expensas.
    const n = valor(
      rentabilidadNeta({
        alquilerMensual: 500,
        precio: 100_000,
        gastosMensuales: 100,
        mesesVacanciaPorAnio: 1,
      }),
    );
    expect(n).toBeCloseTo((500 * 11 - 100 * 12) / 100_000, 10);
    expect(n).toBeLessThan(0.048);
  });

  it("la neta siempre es menor que la bruta cuando hay gastos", () => {
    const bruta = valor(rentabilidadBruta(500, 100_000));
    const neta = valor(
      rentabilidadNeta({ alquilerMensual: 500, precio: 100_000, gastosMensuales: 50, costosDeCompra: 7_000 }),
    );
    expect(neta).toBeLessThan(bruta);
  });

  it("divide por la inversión total cuando hay costos de compra", () => {
    const n = valor(
      rentabilidadNeta({ alquilerMensual: 500, precio: 100_000, costosDeCompra: 10_000 }),
    );
    expect(n).toBeCloseTo(6_000 / 110_000, 10);
  });

  it("puede dar negativa, y eso es un resultado válido", () => {
    const n = valor(
      rentabilidadNeta({ alquilerMensual: 100, precio: 100_000, gastosMensuales: 300 }),
    );
    expect(n).toBeLessThan(0);
  });

  it("rechaza una vacancia imposible", () => {
    expect(
      rentabilidadNeta({ alquilerMensual: 500, precio: 100_000, mesesVacanciaPorAnio: 13 }).ok,
    ).toBe(false);
    expect(
      rentabilidadNeta({ alquilerMensual: 500, precio: 100_000, mesesVacanciaPorAnio: -1 }).ok,
    ).toBe(false);
  });
});

describe("flujo de caja", () => {
  it("resta la cuota del crédito al ingreso neto", () => {
    const cf = valor(
      cashFlowMensual({
        alquilerMensual: 800,
        precio: 100_000,
        gastosMensuales: 100,
        cuotaMensual: 600,
      }),
    );
    expect(cf).toBeCloseTo(800 - 100 - 600, 10);
  });

  it("es negativo cuando la cuota supera el alquiler, y lo muestra", () => {
    // Es justamente el resultado que alguien necesita ver antes de comprar.
    const cf = valor(
      cashFlowMensual({ alquilerMensual: 500, precio: 100_000, cuotaMensual: 900 }),
    );
    expect(cf).toBeLessThan(0);
    expect(cf).toBeCloseTo(-400, 10);
  });

  it("sin crédito, el flujo es el ingreso neto", () => {
    const cf = valor(cashFlowMensual({ alquilerMensual: 500, precio: 100_000, gastosMensuales: 100 }));
    expect(cf).toBeCloseTo(400, 10);
  });
});

describe("relación cuota/ingreso", () => {
  it("devuelve la fracción sin juzgarla", () => {
    // Cada banco tiene su límite y cambia: no se fija un máximo acá.
    expect(valor(relacionCuotaIngreso(600, 2_000))).toBeCloseTo(0.3, 10);
  });

  it("exige los dos datos", () => {
    expect(relacionCuotaIngreso(600, null).ok).toBe(false);
    expect(relacionCuotaIngreso(null, 2_000).ok).toBe(false);
    expect(relacionCuotaIngreso(600, 0).ok).toBe(false);
  });
});

describe("ninguna tasa está escrita en el módulo", () => {
  it("todo cálculo con tasa la exige como parámetro", () => {
    // Si alguien agregara un default, este test no lo vería; lo que sí se
    // comprueba es que sin tasa no se puede calcular nada.
    // @ts-expect-error falta la tasa a propósito
    expect(() => cuotaHipotecaria({ capital: 100_000, meses: 240 })).not.toThrow();
    // @ts-expect-error falta la tasa a propósito
    expect(cuotaHipotecaria({ capital: 100_000, meses: 240 }).ok).toBe(false);
  });
});
