import { describe, expect, it } from "vitest";
import { Cronometro, MAXIMO_DE_MARCAS } from "./timings";

describe("nunca rompe una request para medirla", () => {
  it("descarta nombres inválidos sin lanzar", () => {
    const c = new Cronometro();
    for (const nombre of ["", "Mayúsculas", "con espacio", "con-guion", "1empieza_con_numero", "x".repeat(41)]) {
      expect(() => c.registrar(nombre, 10)).not.toThrow();
    }
    expect(c.resumen().timings).toEqual({});
    expect(c.resumen().descartadas).toBe(6);
  });

  it("descarta duraciones imposibles", () => {
    const c = new Cronometro();
    c.registrar("db", Number.NaN);
    c.registrar("db", -5);
    c.registrar("db", Number.POSITIVE_INFINITY);
    expect(c.resumen().timings).toEqual({});
    expect(c.resumen().descartadas).toBe(3);
  });

  it("mide igual cuando la operación falla", async () => {
    // Una consulta que tarda cinco segundos y después revienta es justo la que
    // hay que ver; medir sólo los éxitos la haría invisible.
    const c = new Cronometro();
    await expect(
      c.medir("db", async () => {
        throw new Error("cayó la base");
      }),
    ).rejects.toThrow("cayó la base");
    expect(Object.keys(c.resumen().timings)).toEqual(["db_ms"]);
  });

  it("la versión síncrona también mide ante una excepción", () => {
    const c = new Cronometro();
    expect(() =>
      c.medirSync("parseo", () => {
        throw new Error("x");
      }),
    ).toThrow();
    expect(Object.keys(c.resumen().timings)).toEqual(["parseo_ms"]);
  });
});

describe("tope de marcas", () => {
  it("no deja crecer el log sin límite", () => {
    // Un bucle que abre una marca por fila crearía 257.073 entradas.
    const c = new Cronometro();
    for (let i = 0; i < MAXIMO_DE_MARCAS + 10; i++) c.registrar(`marca_${i}`, 1);
    expect(Object.keys(c.resumen().timings)).toHaveLength(MAXIMO_DE_MARCAS);
    expect(c.resumen().descartadas).toBe(10);
  });

  it("sigue acumulando en marcas ya existentes tras llegar al tope", () => {
    const c = new Cronometro();
    for (let i = 0; i < MAXIMO_DE_MARCAS; i++) c.registrar(`marca_${i}`, 1);
    c.registrar("marca_0", 5);
    expect(c.resumen().timings.marca_0_ms).toBe(6);
    expect(c.resumen().descartadas).toBe(0);
  });
});

describe("acumulación", () => {
  it("suma en vez de reemplazar", () => {
    // Si una request hace ocho consultas, interesa el total en base, no la
    // última.
    const c = new Cronometro();
    c.registrar("db", 10);
    c.registrar("db", 15);
    expect(c.resumen().timings.db_ms).toBe(25);
  });

  it("distingue marcas con nombres distintos", () => {
    const c = new Cronometro();
    c.registrar("db", 10);
    c.registrar("gate", 5);
    expect(c.resumen().timings).toEqual({ db_ms: 10, gate_ms: 5 });
  });

  it("ordena las claves para que la línea de log sea comparable", () => {
    const c = new Cronometro();
    c.registrar("zeta", 1);
    c.registrar("alfa", 1);
    expect(Object.keys(c.resumen().timings)).toEqual(["alfa_ms", "zeta_ms"]);
  });

  it("redondea a milisegundos enteros", () => {
    const c = new Cronometro();
    c.registrar("db", 10.6);
    expect(c.resumen().timings.db_ms).toBe(11);
  });
});

describe("uso normal", () => {
  it("mide una operación asíncrona y devuelve su valor", async () => {
    const c = new Cronometro();
    const valor = await c.medir("db", async () => 42);
    expect(valor).toBe(42);
    expect(c.resumen().timings).toHaveProperty("db_ms");
  });

  it("un cronómetro sin usar no ensucia el log", () => {
    const c = new Cronometro();
    expect(c.tieneDatos()).toBe(false);
    expect(c.resumen()).toEqual({ timings: {}, descartadas: 0 });
  });

  it("informa que tiene datos apenas se registra algo", () => {
    const c = new Cronometro();
    c.registrar("db", 1);
    expect(c.tieneDatos()).toBe(true);
  });

  it("un descarte también cuenta como dato: es señal de mal uso", () => {
    const c = new Cronometro();
    c.registrar("NOMBRE MALO", 1);
    expect(c.tieneDatos()).toBe(true);
  });
});

describe("nombres, no valores", () => {
  it("el formato admitido no deja meter un valor en el nombre", () => {
    // `db_query_rosario_250000` pasaría el formato, pero un nombre con
    // mayúsculas, espacios o signos —como los que trae un valor real— no.
    const c = new Cronometro();
    c.registrar("db_query?city=Rosario", 1);
    c.registrar("precio=250000", 1);
    expect(c.resumen().timings).toEqual({});
    expect(c.resumen().descartadas).toBe(2);
  });
});
